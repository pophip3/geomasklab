"""Explicit task intent for the offline demonstration and bounded live routing.

This grammar is deterministic convenience logic, not language-model reasoning.
Legacy Chinese input patterns remain supported; all generated responses are English.
"""
import re

TARGET_PATTERNS = {
    'building': r'建筑|房屋|楼|\bbuildings?\b',
    'aircraft': r'飞机|\b(?:aircraft|airplanes?|planes?)\b',
    'road': r'道路|公路|\broads?\b',
    'water': r'水体|河流|\bwater(?: bodies| body)?\b',
    'tree': r'植被|树木|\b(?:trees?|vegetation)\b',
    'ship': r'船|\bships?\b',
}
SEGMENT_WORDS = r'提取|分割|标注|标记|圈出|勾勒|蒙版|掩膜|面积|占比|像素|\b(?:segment|segmentation|mask|extract|annotate|coverage|pixels?)\b'
FOLLOWUP_WORDS = r'改|换|左|右|上半|下半|全部|全图|重新|重跑|统计|框选|选区|研究区|模式|快一点|小目标|整批|批量|\b(?:switch|change|left|right|top|bottom|whole|entire|rerun|recalculate|statistics|coverage|roi|region|mode|fast|refinement|batch)\b'
AMBIGUOUS_WORDS = r'那个|那片|那块|这块|\b(?:that region|that area|this part|that part)\b'
SCENE_WORDS = r'场景|什么地方|介绍.*影像|什么类型|\b(?:scene|describe|caption|what is|what kind)\b'
EXPORT_COMMAND = re.compile(r'(?:(?:请)?(?:导出|下载)(?:刚才的|当前|这个|所选)?(?:实验包|结果)?[。！! ]*|(?:please )?(?:export|download)(?: the)?(?: selected| current| previous| last)?(?: result| evidence| bundle| evidence bundle)?[.! ]*)', re.I)


def ambiguous_query(query):
    """Recognize unresolved demonstrative references before inference."""
    return bool(re.search(AMBIGUOUS_WORDS, query, re.I))


def is_export_command(query):
    """Accept a standalone export request, never a mixed inference instruction."""
    return bool(EXPORT_COMMAND.fullmatch(query.strip()))


def requires_dense_result(query, context=None):
    """Route mask/coverage requests and supported selected-result follow-ups."""
    return bool(re.search(SEGMENT_WORDS, query, re.I) or
                ((context or {}).get('target') and re.search(FOLLOWUP_WORDS, query, re.I)))


def resolve_invert(query, context=None):
    """Resolve explicit complement/positive intent, otherwise retain the parent."""
    q = query.lower()
    targets = r'(?:建筑|房屋|楼|飞机|道路|公路|水体|河流|植被|树木|船舶?|buildings?|aircraft|airplanes?|planes?|roads?|water|trees?|vegetation|ships?)'
    inverse = bool(re.search(r'非\s*' + targets + '|' + targets + r'\s*(?:之外|以外)|\bnon[ -]' + targets + r'\b|\b(?:complement|outside the mask)\b', q))
    positive = bool(re.search(r'只要|仅要|仅标注|只标注|只提取|\b(?:only|positive mask|without complement)\b', q))
    if inverse:
        return True
    if positive:
        return False
    return bool((context or {}).get('invert'))


def parse_demo_task(query, context):
    """Select a documented procedural-demo action without inventing a target."""
    q = query.strip().lower()
    if ambiguous_query(q):
        return {'action': 'clarify', 'question': 'Specify the semantic target and spatial scope, or select an existing result to supply context.'}
    if is_export_command(q):
        return {'action': 'export'}
    if re.search(SCENE_WORDS, q) and not re.search(SEGMENT_WORDS, q):
        return {'action': 'scene'}
    target = next((key for key, pattern in TARGET_PATTERNS.items() if re.search(pattern, q)), None)
    inherited = target is None
    target = target or context.get('target')
    if not target or not (re.search(SEGMENT_WORDS + '|' + FOLLOWUP_WORDS, q) or any(re.search(p, q) for p in TARGET_PATTERNS.values())):
        return {'action': 'clarify', 'question': 'Specify one target and scope, for example: Extract buildings in the right half and calculate coverage.'}
    return {'action': 'segment', 'target': target, 'side': context.get('side', 'all'),
            'invert': resolve_invert(query, context), 'inherited_target': inherited,
            'reuse': bool(re.search(r'统计|占比|面积|\b(?:coverage|statistics|measure)\b', q) and not re.search(r'提取|分割|改|换|\b(?:extract|segment|switch|change)\b', q) and context.get('target') == target)}
