"""HTTP planner adapter; the workbench owns execution and all image assets."""
from __future__ import annotations

import os
from pathlib import Path
import re
import hashlib
from planner_protocol import PlannerProtocol

from service_transport import request_json

ALLOWED_TOOLS = {'referring_expression_segmentation', 'semantic_segmentation'}
LABELS = {
    'building': ('building', 'buildings', '建筑', '房屋'),
    'aircraft': ('aircraft', 'airplane', 'airplanes', 'plane', 'planes', '飞机'),
    'road': ('road', 'roads', '道路'),
    'water': ('water', 'water body', 'water bodies', '水体'),
    'tree': ('tree', 'trees', 'vegetation', 'trees and vegetation', '植被', '树木'),
    'ship': ('ship', 'ships', '船舶'),
}
PROMPTS = {'building':'all buildings', 'aircraft':'all planes', 'road':'all roads',
           'water':'water bodies', 'tree':'trees and vegetation', 'ship':'all ships'}
CLASSES = {'building':'building', 'aircraft':'aircraft', 'road':'road',
           'water':'water', 'tree':'tree', 'ship':'ship'}
SIDES = {'all', 'left', 'right', 'top', 'bottom'}


class Clarification(ValueError):
    """A task outside the explicit workbench contract, not a service failure."""


def resolve_scope(query, context, selected=None):
    """Explicit, logged pixel-scope grammar; not an LLM reasoning capability."""
    q = query.lower()
    if re.search(r'靠近|附近|之间|东侧|西侧|南侧|北侧|平方米|公顷|米以内|最大|最小|除外|除了|不要.*[左右上下]|不含|左上|左下|右上|右下|\b(near|between|except|largest|smallest|north|south|east|west)\b', q):
        raise Clarification('当前只支持全图或单个像素半幅。复杂关系、排除条件和地理面积需要另行明确，尚未执行。')
    found = {side for side, pattern in {
        'left': r'左|\bleft\b', 'right': r'右|\bright\b',
        'top': r'上半|上方|顶部|\b(top|upper)\b',
        'bottom': r'下半|下方|底部|\b(bottom|lower)\b',
        'all': r'全图|全部|整幅|\bwhole image\b|\bentire image\b',
    }.items() if re.search(pattern, q)}
    if len(found) > 1:
        raise Clarification('一次实验请选择一个范围：全图、左半幅、右半幅、上半幅或下半幅。')
    if selected is not None:
        if selected not in SIDES:
            raise ValueError('不支持的像素范围')
        if found and selected not in found:
            raise Clarification('所选范围与文字指令不一致，请确认后重试。')
        return selected, 'explicit_scope_selection'
    if found:
        return found.pop(), 'harness_pixel_scope_rule'
    return context.get('side', 'all'), 'selected_version_context' if context.get('side') else 'whole_image_default'


class WorkbenchAgent(PlannerProtocol):
    """Independent restricted protocol adapter, without bundled upstream software."""
    def __init__(self, task_route='dense'):
        self.base = os.environ.get('GEO_AGENT_BASE_URL', '').rstrip('/')
        model = os.environ.get('GEO_AGENT_MODEL', '')
        if not self.base or not model:
            raise ValueError('RemoteAgent 服务未配置，请填写实际服务地址和模型名称。')
        if task_route not in ('dense', 'internal'):
            raise ValueError('未知的 RemoteAgent 任务路由')
        self.task_route = task_route
        allowed_tools = ALLOWED_TOOLS if task_route == 'dense' else set()
        token_limit = 1024 if task_route == 'internal' else 512
        super().__init__(model_name=model, allowed_tools=allowed_tools, max_tokens=token_limit)

    def _runtime_system_prompt(self):
        if self.task_route == 'internal':
            return (
                'You are RemoteAgent in the GeoScope workbench. This turn is INTERNAL VISUAL UNDERSTANDING ONLY; '
                'only these deployed tools are available: none. Inspect the supplied image and answer the user '
                'inside exactly one <answer>...</answer> block. Scene description, captioning, visual question '
                'answering, classification, counting, and comparison are internal tasks. Do not output T_call. '
                'Answer concisely in the user\'s language.'
            )
        return (
            'You are RemoteAgent in the GeoScope workbench. This turn needs a pixel mask. '
            'Only these deployed tools are available: referring_expression_segmentation and semantic_segmentation. '
            'For a supported extraction request, output exactly ONE plain T_call(...) and nothing else: '
            'no <think>, <answer>, XML wrapper, markdown, explanation, or second call. '
            'Exact signatures: T_call(referring_expression_segmentation, "image_path", "whole-image English prompt") '
            'or T_call(semantic_segmentation, "image_path", ["one English class"]). '
            'Copy image_path from the user message. Valid targets are building, aircraft, road, water, tree, ship. '
            'For any airplane, aircraft, plane, or 飞机 extraction, use '
            'T_call(referring_expression_segmentation, "image_path", "all planes") '
            'or T_call(semantic_segmentation, "image_path", ["aircraft"]). '
            'For buildings, use "all buildings" or ["building"]. '
            '"只提取左边的建筑" is a valid building request: call whole-image building segmentation. '
            'The tool always segments the WHOLE image. ROI coordinates, quality mode, and batch membership '
            'are Harness-owned context; never add them to tool arguments or issue multiple calls. '
            'Do not put left, right, top, bottom, region, area, '
            'ratio, or other spatial conditions in tool arguments. The Harness applies those conditions afterward. '
            'For a follow-up, inherit the previous target from context unless the user changes it. '
            'If context.invert is true, request the positive target mask; the Harness inverts it. '
            'Do not guess a target from the image or substitute a supported target. '
            '"所有物体的轮廓" / "contours of all objects" has no single supported target; ask for clarification. '
            'For unsupported targets, multiple categories, or ambiguous targets, output a concise '
            '<answer>clarification needed</answer>. Never claim a mask or measurement before tool execution.'
        )

    def _run_llm(self, messages):
        response = request_json(self.base + '/chat/completions', {
            'model': self.model_name, 'messages': messages, 'max_tokens': self.max_tokens,
            'temperature': 0,
        }, headers={'Authorization': 'Bearer ' + os.environ.get('GEO_AGENT_API_KEY', 'EMPTY')})
        try:
            message = response['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError):
            raise ValueError('认知服务未返回有效的文本响应') from None
        if not isinstance(message, str) or not message.strip():
            raise ValueError('认知服务返回空响应')
        return message.strip()


def decision_record(decision):
    raw = decision.raw_response or ''
    def sanitize(value):
        if isinstance(value, dict):
            return {key: sanitize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        if not isinstance(value, str):
            return value
        value = re.sub(r'<think>[\s\S]*?</think>', '<think>[推理过程不写入实验记录]</think>',
                       value, flags=re.IGNORECASE)
        value = re.sub(r'(?i)\b(?:https?://)[^\s"\'<>]+', '[服务地址已隐去]', value)
        value = re.sub(r'\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?::\d+)?\b',
                       '[内网地址已隐去]', value)
        value = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]+', 'Bearer [已隐去]', value)
        return value.strip()
    visible = sanitize(raw)
    history = sanitize(decision.history)
    return {'status': decision.status, 'raw_response': visible,
            'raw_response_sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest() if raw else None,
            'text': sanitize(decision.text or ''), 'history': history,
            'tool_call': None if decision.tool_call is None else {
                'name': decision.tool_call.name, 'arguments': sanitize(decision.tool_call.arguments)}}


def target_from_label(label, side):
    if not isinstance(label, str):
        raise Clarification('模型没有提供有效的目标类别。')
    label = label.strip().lower()
    # Only this exact simple suffix may be normalized; arbitrary relations are rejected.
    match = re.fullmatch(r'(.+?) (?:on|in) the (left|right|top|bottom)(?: (?:half|side))?', label)
    if match:
        if match.group(2) != side:
            raise Clarification('模型返回的空间范围与本次任务范围不一致，请确认后重试。')
        label = match.group(1)
    label = re.sub(r'^(?:all (?:the )?|the )', '', label)
    for target, aliases in LABELS.items():
        if label in aliases:
            return target
    raise Clarification('本版仅支持六类目标的全图分割及像素半幅筛选；模型给出了其他类别或额外条件，请简化指令。')


def segmentation_plan(decision, image_path, side, scope_source, invert=False, expected_target=None):
    call = decision.tool_call
    if decision.status != 'tool_call' or call is None or call.name not in ALLOWED_TOOLS:
        raise ValueError('认知核心没有返回允许执行的分割工具')
    args = call.arguments
    if Path(args.get('image_path', '')).resolve() != Path(image_path).resolve():
        raise ValueError('工具影像与当前实验不一致')
    if call.name == 'referring_expression_segmentation':
        if set(args) != {'image_path', 'prompt'}:
            raise ValueError('指代分割参数不符合约定')
        target = target_from_label(args['prompt'], side)
        request = {'task': 'referring_seg', 'text': PROMPTS[target]}
        mask_field = None
    else:
        classes = args.get('classes')
        if set(args) != {'image_path', 'classes'} or not isinstance(classes, list) or len(classes) != 1:
            raise Clarification('每次实验只支持一个目标类别，请分别提取并保存版本。')
        target = target_from_label(classes[0], side)
        request = {'task': 'semantic_seg', 'classes': [CLASSES[target]]}
        mask_field = CLASSES[target]
    if expected_target is not None and target != expected_target:
        raise Clarification('RemoteAgent 工具目标与本次任务目标不一致，未执行分割。')
    return {'action': 'segment', 'target': target, 'side': side, 'invert': bool(invert), 'scope_source': scope_source,
            'tool_name': call.name, 'service_request': request, 'mask_field': mask_field,
            'planner_protocol': 'remoteagent', 'scope_rule': '整图目标分割后按像素半幅裁切；由 Harness 执行'}


class AgentTurn:
    def __init__(self, query, image_path, context, side, scope_source, task_route='dense', invert=False,
                 roi=None, quality_mode='auto', batch_id=None):
        self.agent = WorkbenchAgent(task_route=task_route)
        self.query, self.image_path = query, image_path
        self.context = {**context, 'side': side, 'scope_source': scope_source,
                        'scope_rule': 'whole-image segmentation then deterministic pixel-half clipping',
                        'task_route': task_route, 'invert': bool(invert), 'roi': roi,
                        'quality_mode': quality_mode, 'batch_id': batch_id}
        self.decision = self.agent.plan(query, image_path, context=self.context)

    def feedback(self, result):
        return self.agent.continue_with_tool_result(self.query, self.image_path, self.decision,
                                                   result, context=self.context)
