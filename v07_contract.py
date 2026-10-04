"""Validated GeoScope v0.7 task fields owned by the Harness."""
from __future__ import annotations

import re


QUALITY_MODES = {'fast', 'accurate', 'auto'}
ROI_WORDS = re.compile(r'框选|框内|选区|研究区|矩形|\broi\b|selected region', re.I)
BATCH_WORDS = re.compile(r'批量|整批|这一批|这些影像|所有影像|\bbatch\b|these images', re.I)
TARGET_WORDS = {
    'building': r'建筑|房屋|\bbuildings?\b',
    'aircraft': r'飞机|\b(?:aircraft|airplanes?|planes?)\b',
    'road': r'道路|\broads?\b',
    'water': r'水体|\bwater\b',
    'tree': r'植被|树木|\btrees?\b',
    'ship': r'船舶?|\bships?\b',
}


def validate_target_intent(query):
    if sum(bool(re.search(pattern, query, re.I)) for pattern in TARGET_WORDS.values()) > 1:
        raise ValueError('一次任务只支持一个目标类别，请分别提取并保存版本。')


def has_target_intent(query):
    return target_intent(query) is not None


def target_intent(query):
    return next((target for target, pattern in TARGET_WORDS.items()
                 if re.search(pattern, query, re.I)), None)


def resolve_roi(query, context, selected, width, height):
    if selected is None:
        roi = context.get('roi')
        source = 'selected_version_context' if roi else None
    elif selected == {}:
        roi, source = None, 'explicit_clear'
    else:
        roi, source = selected, 'explicit_selection'
    if ROI_WORDS.search(query) and roi is None:
        raise ValueError('任务要求框选区域，但当前影像没有有效的矩形 ROI。')
    if roi is None:
        return None, source
    if not isinstance(roi, dict) or set(roi) != {'xyxy', 'source', 'image_size'}:
        raise ValueError('ROI 必须包含 xyxy、source、image_size')
    xyxy, size = roi['xyxy'], roi['image_size']
    if (not isinstance(xyxy, list) or len(xyxy) != 4 or
        any(type(v) is not int for v in xyxy) or
        not isinstance(size, list) or size != [width, height] or
        not isinstance(roi['source'], str) or roi['source'] not in {'drawn', 'imported'}):
        raise ValueError('ROI 坐标、来源或影像尺寸无效')
    x1, y1, x2, y2 = xyxy
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError('ROI 超出影像边界或为空')
    return dict(roi), source


def resolve_quality(query, context, selected=None):
    q = query.lower()
    fast = bool(re.search(r'快速|快一点|快些|速度优先|\bfast\b', q))
    accurate = bool(re.search(r'高精度|精细|小目标|精度优先|\baccurate\b', q))
    automatic = bool(re.search(r'自动模式|自动选择|\bauto\b', q))
    found = [name for name, present in (('fast', fast), ('accurate', accurate), ('auto', automatic)) if present]
    if len(found) > 1:
        raise ValueError('任务同时要求多个执行模式，请只选择一种')
    if selected is not None and (not isinstance(selected, str) or selected not in QUALITY_MODES):
        raise ValueError('非法 quality_mode；仅支持 fast、accurate、auto')
    if selected not in (None, 'auto') and found and selected != found[0]:
        raise ValueError('执行模式选择与文字任务冲突')
    requested = selected or (found[0] if found else context.get('quality_mode', 'auto'))
    if requested not in QUALITY_MODES:
        raise ValueError('上下文包含非法 quality_mode')
    effective = ('accurate' if accurate else 'fast') if requested == 'auto' else requested
    source = 'explicit_selection' if selected else 'task_text' if found else 'selected_version_context' if context.get('quality_mode') else 'default'
    return requested, effective, source


def batch_requested(query):
    return bool(BATCH_WORDS.search(query))
