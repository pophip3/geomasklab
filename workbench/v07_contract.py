"""Validated GeoScope v0.7 task fields owned by the Harness."""
from __future__ import annotations

import re


QUALITY_MODES = {'fast', 'accurate', 'auto'}
ROI_WORDS = re.compile('\u6846\u9009|\u6846\u5185|\u9009\u533a|\u7814\u7a76\u533a|\u77e9\u5f62|\\broi\\b|selected region', re.I)
BATCH_WORDS = re.compile('\u6279\u91cf|\u6574\u6279|\u8fd9\u4e00\u6279|\u8fd9\u4e9b\u5f71\u50cf|\u6240\u6709\u5f71\u50cf|\\bbatch\\b|these images', re.I)
TARGET_WORDS = {
    'building': '\u5efa\u7b51|\u623f\u5c4b|\\bbuildings?\\b',
    'aircraft': '\u98de\u673a|\\b(?:aircraft|airplanes?|planes?)\\b',
    'road': '\u9053\u8def|\\broads?\\b',
    'water': '\u6c34\u4f53|\\bwater\\b',
    'tree': '\u6811\u6728|\\btrees?\\b',
    'vegetation': '\u690d\u88ab|\\bvegetation\\b',
    'ship': '\u8239\u8236?|\\bships?\\b',
}


def validate_target_intent(query):
    if sum(bool(re.search(pattern, query, re.I)) for pattern in TARGET_WORDS.values()) > 1:
        raise ValueError('Each task supports one target. Segment categories separately and save separate versions.')


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
        raise ValueError('The task requests a selected region, but no valid rectangle ROI is available.')
    if roi is None:
        return None, source
    if not isinstance(roi, dict) or set(roi) != {'xyxy', 'source', 'image_size'}:
        raise ValueError('ROI must include xyxy, source and image_size.')
    xyxy, size = roi['xyxy'], roi['image_size']
    if (not isinstance(xyxy, list) or len(xyxy) != 4 or
        any(type(v) is not int for v in xyxy) or
        not isinstance(size, list) or size != [width, height] or
        not isinstance(roi['source'], str) or roi['source'] not in {'drawn', 'imported'}):
        raise ValueError('Invalid ROI coordinates, source or image dimensions.')
    x1, y1, x2, y2 = xyxy
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError('The ROI is empty or outside the image.')
    return dict(roi), source


def resolve_quality(query, context, selected=None):
    q = query.lower()
    fast = bool(re.search('\u5feb\u901f|\u5feb\u4e00\u70b9|\u5feb\u4e9b|\u901f\u5ea6\u4f18\u5148|\\bfast\\b', q))
    accurate = bool(re.search('\u9ad8\u7cbe\u5ea6|\u7cbe\u7ec6|\u7ec6\u5316|\u5206\u5757|\u5c0f\u76ee\u6807|\u7cbe\u5ea6\u4f18\u5148|\\baccurate\\b|\\btiled refinement\\b', q))
    automatic = bool(re.search('\u81ea\u52a8\u6a21\u5f0f|\u81ea\u52a8\u9009\u62e9|\\bauto\\b', q))
    found = [name for name, present in (('fast', fast), ('accurate', accurate), ('auto', automatic)) if present]
    if len(found) > 1:
        raise ValueError('The task requests multiple execution modes. Select one mode.')
    if selected is not None and (not isinstance(selected, str) or selected not in QUALITY_MODES):
        raise ValueError('Invalid quality_mode; allowed values are fast, accurate and auto.')
    if selected not in (None, 'auto') and found and selected != found[0]:
        raise ValueError('The selected execution mode conflicts with the task text.')
    requested = selected or (found[0] if found else context.get('quality_mode', 'auto'))
    if requested not in QUALITY_MODES:
        raise ValueError('The context contains an invalid quality_mode.')
    effective = ('accurate' if accurate else 'fast') if requested == 'auto' else requested
    source = 'explicit_selection' if selected else 'task_text' if found else 'selected_version_context' if context.get('quality_mode') else 'default'
    return requested, effective, source


def batch_requested(query):
    return bool(BATCH_WORDS.search(query))
