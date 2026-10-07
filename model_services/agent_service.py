"""Optional local RemoteAgent endpoint; model code and weights are external.

This adapter implements only the two non-streaming endpoints consumed by the
workbench. It never evaluates a model reply or executes tools. Heavy imports
are deferred so the normal GeoMaskLab installation remains Pillow-only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 18 * 1024 * 1024


def prepare_messages(messages):
    """Validate a single-image OpenAI-style history and decode its image."""
    from PIL import Image
    if not isinstance(messages, list) or not 1 <= len(messages) <= 24:
        raise ValueError('Supply between 1 and 24 messages.')
    normalized, images = [], []
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in ('system', 'user', 'assistant'):
            raise ValueError('Only system, user and assistant messages are supported.')
        content = message.get('content')
        if isinstance(content, str):
            if len(content) > 32000:
                raise ValueError('Text message is too long.')
            normalized.append({'role': message['role'], 'content': content})
            continue
        if not isinstance(content, list) or message['role'] != 'user':
            raise ValueError('Image content is supported only in a user message.')
        blocks = []
        for block in content:
            if not isinstance(block, dict):
                raise ValueError('Invalid content block.')
            if block.get('type') == 'text' and isinstance(block.get('text'), str):
                if len(block['text']) > 32000:
                    raise ValueError('Text message is too long.')
                blocks.append({'type': 'text', 'text': block['text']})
            elif block.get('type') == 'image_url':
                reference = block.get('image_url')
                if not isinstance(reference, dict):
                    raise ValueError('image_url must contain a URL object.')
                url = reference.get('url', '')
                if not isinstance(url, str) or not url.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,')):
                    raise ValueError('Use an embedded PNG/JPEG; remote URLs are not fetched.')
                raw = base64.b64decode(url.split(',', 1)[1], validate=True)
                if len(raw) > 12 * 1024 * 1024:
                    raise ValueError('Embedded image is too large.')
                try:
                    with Image.open(io.BytesIO(raw)) as source:
                        declared = 'PNG' if url.startswith('data:image/png;') else 'JPEG'
                        if source.format != declared:
                            raise ValueError('Image format does not match its PNG/JPEG data URL.')
                        if source.width * source.height > 16_000_000:
                            raise ValueError('Image exceeds the 16 MP service limit.')
                        images.append(source.convert('RGB'))
                except (OSError, Image.DecompressionBombError) as exc:
                    raise ValueError('Embedded bytes must be a readable PNG/JPEG image.') from exc
                blocks.append({'type': 'image'})
            else:
                raise ValueError('Unsupported content block.')
        normalized.append({'role': message['role'], 'content': blocks})
    if len(images) != 1:
        raise ValueError('Exactly one image must be supplied across the conversation.')
    return normalized, images


class TransformersBackend:
    def __init__(self, args):
        import torch
        import transformers
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        self.torch = torch
        root = Path(args.model_dir).resolve()
        if not (root / 'model.safetensors.index.json').is_file():
            raise ValueError('A complete local RemoteAgent safetensors checkpoint is required.')
        index = json.loads((root / 'model.safetensors.index.json').read_text(encoding='utf-8'))
        shards = sorted(set(index['weight_map'].values()))
        for shard in shards:
            if Path(shard).name != shard or not (root / shard).is_file():
                raise ValueError('A checkpoint shard is missing or has an unsafe name.')
        settings = {'torch_dtype': torch.bfloat16, 'local_files_only': True,
                    'low_cpu_mem_usage': True, 'attn_implementation': 'sdpa'}
        if args.device == 'cpu':
            settings['device_map'] = {'': 'cpu'}
        elif args.device == 'cuda':
            if not torch.cuda.is_available():
                raise ValueError('CUDA was requested but is unavailable.')
            settings['device_map'] = {'': 0}
        else:
            if not torch.cuda.is_available():
                raise ValueError('Offload mode requires an available CUDA GPU.')
            Path(args.offload_dir).mkdir(parents=True, exist_ok=True)
            settings.update(device_map='auto', max_memory={0: args.gpu_memory, 'cpu': args.cpu_memory},
                            offload_folder=str(Path(args.offload_dir).resolve()),
                            offload_state_dict=True, offload_buffers=True)
        self.processor = AutoProcessor.from_pretrained(str(root), local_files_only=True,
            use_fast=False, min_pixels=3136, max_pixels=args.max_pixels)
        model, diagnostics = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            str(root), output_loading_info=True, **settings)
        if any(diagnostics.get(key) for key in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')):
            raise ValueError('RemoteAgent checkpoint does not exactly match the model architecture.')
        self.model = model.eval()
        self.max_context = args.max_context
        self.metadata = {'backend': 'transformers', 'transformers': transformers.__version__,
            'torch': torch.__version__, 'dtype': 'bfloat16', 'quantized': False,
            'device_mode': args.device, 'device_map': {k: str(v) for k, v in self.model.hf_device_map.items()},
            'processor_use_fast': False, 'max_image_pixels': args.max_pixels,
            'max_context_tokens': args.max_context,
            'checkpoint_diagnostics': diagnostics,
            'model_index_sha256': hashlib.sha256((root / 'model.safetensors.index.json').read_bytes()).hexdigest(),
            'config_sha256': hashlib.sha256((root / 'config.json').read_bytes()).hexdigest(),
            'checkpoint_tensor_bytes': index.get('metadata', {}).get('total_size'), 'shards': shards}

    def complete(self, messages, max_tokens, temperature):
        normalized, images = prepare_messages(messages)
        text = self.processor.apply_chat_template(normalized, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=images, padding=True, return_tensors='pt')
        length = inputs['input_ids'].shape[1]
        if length + max_tokens > self.max_context:
            raise ValueError('Input and requested output exceed the declared context length.')
        device = self.model.get_input_embeddings().weight.device
        if str(device) == 'meta':
            device = self.torch.device('cuda:0' if self.torch.cuda.is_available() else 'cpu')
        inputs = inputs.to(device)
        with self.torch.inference_mode():
            generated = self.model.generate(**inputs, max_new_tokens=max_tokens,
                do_sample=temperature > 0, **({'temperature': temperature} if temperature > 0 else {}))
        answer = self.processor.batch_decode(generated[:, length:], skip_special_tokens=True,
                                            clean_up_tokenization_spaces=False)[0]
        return answer, {'prompt_tokens': int(length), 'completion_tokens': int(generated.shape[1] - length),
                        'total_tokens': int(generated.shape[1])}


class AgentApplication:
    def __init__(self, model_name='RemoteAgent', backend=None, max_output_tokens=1024):
        self.model_name, self.backend = model_name, backend
        self.max_output_tokens = max_output_tokens
        self.error = None
        self.lock = threading.Lock()

    def chat(self, payload):
        if self.backend is None:
            raise RuntimeError(self.error or 'Model is still loading.')
        if not isinstance(payload, dict) or payload.get('model') != self.model_name:
            raise ValueError('Request model must match the served model name.')
        if payload.get('stream', False):
            raise ValueError('Streaming is not supported by this local adapter.')
        limit = payload.get('max_tokens', 256)
        if type(limit) is not int or not 1 <= limit <= self.max_output_tokens:
            raise ValueError('max_tokens is outside the service output limit.')
        temperature = payload.get('temperature', 0)
        if type(temperature) not in (int, float) or not 0 <= temperature <= 2:
            raise ValueError('temperature must be between 0 and 2.')
        # Validate before queuing, even when a test backend is supplied.
        prepare_messages(payload.get('messages'))
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError('A model request is already running. Retry after it completes.')
        started = time.perf_counter()
        try:
            answer, usage = self.backend.complete(payload['messages'], limit, temperature)
            return {'object': 'chat.completion', 'model': self.model_name,
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': answer},
                             'finish_reason': 'length' if usage['completion_tokens'] >= limit else 'stop'}],
                'usage': usage, 'service_metadata': {**self.backend.metadata,
                    'inference_ms': round((time.perf_counter() - started) * 1000, 2)}}
        finally:
            self.lock.release()


def make_handler(application):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data):
            raw = json.dumps(data).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            ready = application.backend is not None
            if self.path == '/v1/models':
                return self.reply(200 if ready else 503, {'data': [{'id': application.model_name}] if ready else []})
            if self.path in ('/health', '/ready', '/model-info'):
                return self.reply(200 if ready or self.path == '/health' else 503,
                    {'ready': ready, 'error': application.error,
                     'model': application.model_name,
                     'metadata': application.backend.metadata if ready else None})
            self.reply(404, {'error': 'Unknown endpoint.'})

        def do_POST(self):
            if self.path != '/v1/chat/completions':
                return self.reply(404, {'error': 'Unknown endpoint.'})
            try:
                from model_services.http_body import read_json_body
                raw = read_json_body(self, MAX_BODY)
                result = application.chat(json.loads(raw))
                self.reply(200, result)
            except BlockingIOError as exc:
                self.reply(429, {'error': str(exc)})
            except (ValueError, TypeError) as exc:
                self.reply(400, {'error': str(exc)})
            except RuntimeError as exc:
                self.reply(503, {'error': str(exc)})
            except Exception as exc:
                self.reply(500, {'error': type(exc).__name__, 'message': 'Model inference failed; inspect the local service log.'})
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description='Serve local original RemoteAgent weights without external network calls.')
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--model-name', default='RemoteAgent')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--device', choices=('cuda', 'offload', 'cpu'), default='cuda')
    parser.add_argument('--gpu-memory', default='5GiB')
    parser.add_argument('--cpu-memory', default='2GiB')
    parser.add_argument('--offload-dir', type=Path, default=Path('model-runtime/agent-offload'))
    parser.add_argument('--max-pixels', type=int, default=262144)
    parser.add_argument('--max-context', type=int, default=4096)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or not 3136 <= args.max_pixels <= 1048576 or not 256 <= args.max_context <= 32768:
        parser.error('Invalid port, image-pixel budget or context length.')
    application = AgentApplication(args.model_name)
    def load():
        try:
            application.backend = TransformersBackend(args)
            print('RemoteAgent ready: ' + json.dumps(application.backend.metadata), flush=True)
        except Exception as exc:
            application.error = str(exc)
            import traceback
            traceback.print_exc()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(application))
    threading.Thread(target=load, daemon=True).start()
    print(f'RemoteAgent loading; readiness: http://127.0.0.1:{args.port}/ready', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
