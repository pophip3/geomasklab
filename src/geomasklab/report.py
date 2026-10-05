"""Standalone, English HTML views of successfully replayed evidence."""
import base64
import hashlib
import html
import io
import json
from PIL import Image
from .evidence import load_verified_bundle


def build_report(payload):
    """Reject invalid evidence before rendering; escape every metadata value."""
    facts, files = load_verified_bundle(payload)
    result = json.loads(files['result.json'])
    stats = json.loads(files['statistics.json'])
    escape = lambda value: html.escape(str(value), quote=True)
    percent = lambda value: 'Undefined (empty domain)' if value is None else f'{100 * value:.4f}%'
    rows = [
        ('Foreground', f'{stats["pixel_area"]:,} px'),
        ('Whole-image denominator', f'{stats["total_pixels"]:,} px'),
        ('Coverage of whole image', percent(stats['area_ratio'])),
        ('Selected-region denominator', f'{stats["scope_area_pixels"]:,} px'),
        ('Coverage within selected region', percent(stats['scope_area_ratio'])),
        ('Target', result['task']['target']),
        ('Scope / ROI', json.dumps({'side': result['task']['side'], 'roi': result['task'].get('roi')})),
        ('Execution', result.get('execution_kind', result['mode'])),
        ('Review status', result.get('semantic_review', {}).get('state', 'pending')),
    ]
    if 'validity_measurements' in stats:
        v=stats['validity_measurements']
        rows.extend([('Valid whole-image denominator',f'{v["valid_image_pixels"]:,} px'),
                     ('Valid selected-region denominator',f'{v["valid_region_pixels"]:,} px'),
                     ('Coverage of valid whole image',percent(v['coverage_of_valid_image'])),
                     ('Coverage within valid region',percent(v['coverage_of_valid_region'])),
                     ('Excluded region pixels',f'{v["excluded_region_pixels"]:,} px'),
                     ('Validity declaration',json.dumps(result['analysis_config']['validity']))])
    image = Image.open(io.BytesIO(files['original.png'])).convert('RGB')
    mask = Image.open(io.BytesIO(files['mask.png'])).convert('L')
    overlay = Image.composite(Image.blend(image, Image.new('RGB', image.size, (69, 213, 152)), .48), image, mask)
    overlay.thumbnail((1200, 1200))
    output = io.BytesIO(); overlay.save(output, 'PNG')
    picture = base64.b64encode(output.getvalue()).decode('ascii')
    provenance = {'image': result['provenance'], 'external_mask': result.get('external_mask'),
                  'source_prediction': result.get('source_prediction')}
    body = ''.join(f'<tr><th scope="row">{escape(k)}</th><td>{escape(v)}</td></tr>' for k, v in rows)
    identity = hashlib.sha256(payload).hexdigest()
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>GeoMaskLab evidence report</title><style>
body{{margin:0;background:#f2f6f8;color:#18323d;font:16px/1.6 system-ui,sans-serif}}
main{{max-width:960px;margin:32px auto;padding:28px;background:white;border:1px solid #d6e3e9;border-radius:16px}}
.eyebrow{{color:#197665;font-weight:700}}h1{{line-height:1.2}}img{{width:100%;height:auto;border-radius:12px}}
table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{border-bottom:1px solid #d6e3e9;padding:10px;text-align:left}}
pre,code{{overflow-wrap:anywhere;white-space:pre-wrap}}.note{{padding:16px;background:#eef7f4;border-radius:10px}}
@media(max-width:640px){{main{{margin:12px;padding:16px}}th,td{{padding:6px}}}}
</style></head><body><main><p class="eyebrow">GEOMASKLAB / REPLAYED EVIDENCE</p>
<h1>Every measurement has a scope</h1><p>Verification passed: source-mask consistency and deterministic pixel arithmetic.</p>
<img alt="Verified selected-mask overlay on the supplied image" src="data:image/png;base64,{picture}">
<table><caption>Pixel measurements and explicit denominators</caption>{body}</table>
<p class="note">Replay checks internal consistency. Target accuracy, alignment and source identity require separate evidence.
This report uses pixel units. Candidate components are not validated object counts.</p>
<h2>Provenance</h2><pre>{escape(json.dumps(provenance, indent=2, ensure_ascii=False))}</pre>
<h2>Portable identity</h2><p>Bundle SHA-256: <code>{identity}</code></p>
<p>Result: {escape(facts.get('run_id', result['id']))} · Software version: {escape(result.get('software_version', 'unrecorded'))}</p>
<p>Recompute with <code>geomasklab verify bundle.zip</code>.</p></main></body></html>'''
