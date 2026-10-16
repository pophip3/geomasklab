"""Explicit task intent for the offline demonstration and bounded live routing.

This grammar is deterministic convenience logic, not language-model reasoning.
Legacy Chinese input patterns remain supported; all generated responses are English.
"""
import re

TARGET_PATTERNS = {
    'building': '\u5efa\u7b51|\u623f\u5c4b|\u697c|\\bbuildings?\\b',
    'aircraft': '\u98de\u673a|\\b(?:aircraft|airplanes?|planes?)\\b',
    'road': '\u9053\u8def|\u516c\u8def|\\broads?\\b',
    'water': '\u6c34\u4f53|\u6cb3\u6d41|\\bwater(?: bodies| body)?\\b',
    'tree': '\u6811\u6728|\\btrees?\\b',
    'vegetation': '\u690d\u88ab|\\bvegetation\\b',
    'ship': '\u8239|\\bships?\\b',
}
SEGMENT_WORDS = '\u63d0\u53d6|\u5206\u5272|\u6807\u6ce8|\u6807\u8bb0|\u5708\u51fa|\u52fe\u52d2|\u8499\u7248|\u63a9\u819c|\u9762\u79ef|\u5360\u6bd4|\u50cf\u7d20|\\b(?:segment|segmentation|mask|extract|annotate|coverage|pixels?)\\b'
FOLLOWUP_WORDS = '\u6539|\u6362|\u5de6|\u53f3|\u4e0a\u534a|\u4e0b\u534a|\u5168\u90e8|\u5168\u56fe|\u91cd\u65b0|\u91cd\u8dd1|\u7edf\u8ba1|\u6846\u9009|\u9009\u533a|\u7814\u7a76\u533a|\u6a21\u5f0f|\u5feb\u4e00\u70b9|\u5c0f\u76ee\u6807|\u6574\u6279|\u6279\u91cf|\\b(?:switch|change|left|right|top|bottom|whole|entire|rerun|recalculate|statistics|coverage|roi|region|mode|fast|refinement|batch)\\b'
AMBIGUOUS_WORDS = '\u90a3\u4e2a|\u90a3\u7247|\u90a3\u5757|\u8fd9\u5757|\\b(?:that region|that area|this part|that part)\\b'
SCENE_WORDS = '\u573a\u666f|\u4ec0\u4e48\u5730\u65b9|\u4ecb\u7ecd.*\u5f71\u50cf|\u4ec0\u4e48\u7c7b\u578b|\\b(?:scene|describe|caption|what is|what kind)\\b'
EXPORT_COMMAND = re.compile('(?:(?:\u8bf7)?(?:\u5bfc\u51fa|\u4e0b\u8f7d)(?:\u521a\u624d\u7684|\u5f53\u524d|\u8fd9\u4e2a|\u6240\u9009)?(?:\u5b9e\u9a8c\u5305|\u7ed3\u679c)?[\u3002\uff01! ]*|(?:please )?(?:export|download)(?: the)?(?: selected| current| previous| last)?(?: result| evidence| bundle| evidence bundle)?[.! ]*)', re.I)


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
    targets = '(?:\u5efa\u7b51|\u623f\u5c4b|\u697c|\u98de\u673a|\u9053\u8def|\u516c\u8def|\u6c34\u4f53|\u6cb3\u6d41|\u690d\u88ab|\u6811\u6728|\u8239\u8236?|buildings?|aircraft|airplanes?|planes?|roads?|water|trees?|vegetation|ships?)'
    inverse = bool(re.search('\u975e\\s*' + targets + '|' + targets + '\\s*(?:\u4e4b\u5916|\u4ee5\u5916)|\\bnon[ -]' + targets + r'\b|\b(?:complement|outside the mask)\b', q))
    positive = bool(re.search('\u53ea\u8981|\u4ec5\u8981|\u4ec5\u6807\u6ce8|\u53ea\u6807\u6ce8|\u53ea\u63d0\u53d6|\\b(?:only|positive mask|without complement)\\b', q))
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
            'reuse': bool(re.search('\u7edf\u8ba1|\u5360\u6bd4|\u9762\u79ef|\\b(?:coverage|statistics|measure)\\b', q) and not re.search('\u63d0\u53d6|\u5206\u5272|\u6539|\u6362|\\b(?:extract|segment|switch|change)\\b', q) and context.get('target') == target)}
