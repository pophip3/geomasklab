"""Small independently implemented compatibility protocol, with no code execution.

The text T_call wire format is compatible with RemoteAgent endpoints. This module
does not implement RemoteAgent training, its general tool registry, or agent loop.
"""
from dataclasses import dataclass, field
from pathlib import Path
import ast
import base64
import json
import re


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class Decision:
    status: str
    raw_response: str
    text: str = ''
    tool_call: ToolCall | None = None
    history: list = field(default_factory=list)


def parse_decision(raw, image_path, allowed_tools):
    """Accept one literal call or one answer block; never evaluate model code."""
    body = re.sub(r'^\s*<think>.*?</think>\s*', '', raw, flags=re.S | re.I).strip()
    answer = re.fullmatch(r'<answer>(.*?)</answer>', body, flags=re.S | re.I)
    source = answer.group(1).strip() if answer else body
    xml = re.fullmatch(r'<T_call\s+(\w+)\s*\((.*?)\)>\s*</T_call>', source, flags=re.S | re.I)
    if xml:
        source = 'T_call(' + xml.group(1) + ', ' + xml.group(2) + ')'
    elif re.fullmatch(r'<T_call>\s*\(.*\)\s*</T_call>', source, flags=re.S | re.I):
        source = 'T_call' + re.sub(r'</?T_call>', '', source, flags=re.I).strip()
    elif re.fullmatch(r'<T_call\(.*\)>', source, flags=re.S):
        source = source[1:-1]
    if len(source) > 16384:
        return Decision('unparsed', raw)
    if source.startswith('T_call'):
        try:
            expr = ast.parse(source, mode='eval').body
            if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Name):
                raise ValueError('call required')
            if expr.func.id != 'T_call' or expr.keywords or len(expr.args) != 3:
                raise ValueError('exact positional signature required')
            if len(list(ast.walk(expr))) > 50 or not isinstance(expr.args[0], ast.Name):
                raise ValueError('invalid tool name')
            name = expr.args[0].id
            # Only string and a flat list of strings are protocol literals.
            if not isinstance(expr.args[1], ast.Constant) or not isinstance(expr.args[1].value, str):
                raise ValueError('image string required')
            arg = expr.args[2]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                value = arg.value
            elif isinstance(arg, ast.List) and all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in arg.elts):
                value = [x.value for x in arg.elts]
            else:
                raise ValueError('literal string or flat string list required')
            if name not in allowed_tools:
                return Decision('rejected_tool', raw, text='Tool is unavailable in this turn.')
            field_name = 'prompt' if name == 'referring_expression_segmentation' else 'classes'
            call = ToolCall(name, {'image_path': str(Path(image_path).resolve()), field_name: value})
            return Decision('tool_call', raw, tool_call=call)
        except (SyntaxError, ValueError, TypeError, RecursionError):
            return Decision('unparsed', raw)
    # A tool-like expression inside an answer cannot become an apparent success.
    if answer and 'T_call' not in source:
        return Decision('completed', raw, text=source)
    return Decision('unparsed', raw, text='Unrecognized planner response.')


class PlannerProtocol:
    def __init__(self, *, model_name, allowed_tools, max_tokens):
        self.model_name, self.allowed_tools, self.max_tokens = model_name, set(allowed_tools), max_tokens

    def _messages(self, query, image_path, context):
        image = Path(image_path)
        if not image.is_file():
            raise ValueError('Bound image is unavailable.')
        payload = {'query': query, 'context': context or {}, 'image_path': str(image.resolve())}
        encoded = base64.b64encode(image.read_bytes()).decode('ascii')
        return [{'role': 'system', 'content': self._runtime_system_prompt()},
                {'role': 'user', 'content': [
                    {'type': 'text', 'text': json.dumps(payload, ensure_ascii=False)},
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}}]}]

    def plan(self, query, image_path, *, context=None):
        raw = self._run_llm(self._messages(query, image_path, context))
        result = parse_decision(raw, image_path, self.allowed_tools)
        result.history.append({'round': 1, 'response': raw, 'status': result.status})
        return result

    def continue_with_tool_result(self, query, image_path, decision, tool_result, *, context=None):
        if decision.status != 'tool_call':
            raise ValueError('No pending tool request.')
        def bounded(value):
            if isinstance(value, dict):
                return {key: bounded(child) for key, child in value.items() if key.lower() not in {'image','mask','overlay'}}
            if isinstance(value, list):
                return [bounded(child) for child in value]
            return '[large artifact omitted]' if isinstance(value, str) and len(value) > 2048 else value
        messages = self._messages(query, image_path, context)
        messages += [{'role': 'assistant', 'content': decision.raw_response},
                     {'role': 'user', 'content': '[Execution Result]\n' + json.dumps(bounded(tool_result), ensure_ascii=False) +
                      '\nReturn one <answer> block based on these recorded results. Do not invent measurements or call more tools.'}]
        raw = self._run_llm(messages)
        # Feedback is a reporting turn; no subsequent action is authorized here.
        result = parse_decision(raw, image_path, set())
        result.history = list(decision.history) + [{'round': 2, 'response': raw, 'status': result.status}]
        return result
