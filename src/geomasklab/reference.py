"""Pixel assessment against an explicitly supplied reference, not a prediction."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from PIL import Image, ImageChops, ImageOps
from .evidence import load_verified_bundle
from .masks import binary_png, source_text
from .contract import VERSION
from .comparison import selected_region


def evaluate_reference(bundle, reference, *, source, target, independent, created_at):
    """Verify prediction evidence, then score only its declared spatial domain.

    Reference positives denote the semantic target even for complement results.
    Source independence/alignment are user assertions, never authenticated facts.
    All zero denominators are undefined, including the all-negative IoU/Dice.
    """
    source = source_text(source)
    if type(independent) is not bool:
        raise ValueError('State whether the reference was prepared independently of this prediction.')
    facts, files = load_verified_bundle(bundle)
    result = json.loads(files['result.json'])
    task = result['task']
    if target != task['target']:
        raise ValueError('The reference target must match the selected result target.')
    ref = binary_png(reference, (facts['width'], facts['height']))
    with Image.open(io.BytesIO(files['mask.png'])) as im:
        pred = im.copy()
    with Image.open(io.BytesIO(files['original.png'])) as im:
        original = im.convert('RGB')
    domain = selected_region(pred.size, task)
    # Convert positive-target labels to the same meaning as the saved output.
    scoped_ref = ImageChops.multiply(ImageOps.invert(ref) if task.get('invert') else ref, domain)
    tp = ImageChops.multiply(pred, scoped_ref)
    fp = ImageChops.subtract(pred, tp)
    fn = ImageChops.subtract(scoped_ref, tp)
    n = domain.histogram()[255]
    counts = {name: image.histogram()[255] for name, image in (('tp', tp), ('fp', fp), ('fn', fn))}
    counts['tn'] = n - sum(counts.values())
    t, f, m, tn = (counts[k] for k in ('tp', 'fp', 'fn', 'tn'))
    ratio = lambda a, b: a / b if b else None
    metrics = {'iou': ratio(t, t + f + m), 'dice': ratio(2*t, 2*t + f + m),
               'precision': ratio(t, t + f), 'recall': ratio(t, t + m),
               'specificity': ratio(tn, tn + f), 'pixel_accuracy': ratio(t + tn, n)}
    visual = original.copy()
    for mask, color in ((tp, '#45c5a1'), (fp, '#f0ad4e'), (fn, '#d47bde')):
        visual = Image.composite(Image.blend(original, Image.new('RGB', pred.size, color), .75), visual, mask)
    output = io.BytesIO(); visual.save(output, 'PNG')
    record = {'schema': 'geomasklab-reference-evaluation/1.0', 'software_version': VERSION,
              'created_at': created_at, 'run_id': result['id'], 'version': result['version'],
              'target': target, 'invert': task.get('invert', False),
              'scope': task['side'], 'roi': task.get('roi'), 'evaluated_pixels': n,
              'prediction_origin': {'mode':result['mode'], 'execution_kind':result.get('execution_kind','segmentation'),
                                    'perception':result['provenance']['perception'],
                                    'external_source':result.get('external_mask',{}).get('source')},
              'counts': counts, 'metrics': metrics, 'inference_performed': False,
              'reference': {'source': source, 'independent_user_assertion': independent,
                            'alignment_user_assertion': True, 'origin_authenticated': False,
                            'meaning': 'Foreground denotes the positive semantic target; complemented for complement-result scoring.'},
              'identities': {'prediction_bundle_sha256': hashlib.sha256(bundle).hexdigest(),
                             'image_sha256': hashlib.sha256(files['original.png']).hexdigest(),
                             'prediction_mask_sha256': hashlib.sha256(files['mask.png']).hexdigest(),
                             'reference_upload_sha256': hashlib.sha256(reference).hexdigest()},
              'legend': {'true_positive': '#45c5a1', 'false_positive': '#f0ad4e', 'false_negative': '#d47bde'},
              'interpretation': 'Pixel agreement against the supplied reference inside the saved result scope. '
                  'Reference quality, independence, alignment and representativeness require external validation. '
                  'One image does not establish general model accuracy; undefined ratios are null.'}
    return record, output.getvalue()


def metrics_csv(record):
    """Serialize numeric fields only, leaving undefined ratios blank."""
    table = io.StringIO(newline=''); writer = csv.writer(table)
    writer.writerow(['run_id', 'target', 'complement', 'evaluated_pixels', 'tp', 'fp', 'fn', 'tn', *record['metrics']])
    writer.writerow([record['run_id'], record['target'], record['invert'], record['evaluated_pixels'],
                     *[record['counts'][k] for k in ('tp', 'fp', 'fn', 'tn')],
                     *[v if v is not None else '' for v in record['metrics'].values()]])
    return table.getvalue().encode('utf-8-sig')


def evaluation_packet(record, difference, bundle, reference):
    """Keep all inputs and a hash manifest so another reader can recompute scores."""
    report = '\n'.join(['# GeoMaskLab reference evaluation', '', record['interpretation'], '',
                         f"- Reference source (user supplied): {record['reference']['source']}",
                         f"- Independence asserted by user: {record['reference']['independent_user_assertion']}",
                         f"- Evaluated domain: {record['evaluated_pixels']} pixels; scope: {record['scope']}",
                         '- Metrics use ratios from 0 to 1. Empty denominators are undefined.',
                         '- Color legend: mint = true positive; amber = false positive; magenta = false negative.',
                         '- Recompute: python reference_evaluation.py prediction.zip reference.png --source "Reference description" --target '+record['target']+
                         (' --independent' if record['reference']['independent_user_assertion'] else '')+' --output recomputed.zip', ''])
    files = {'evaluation.json': json.dumps(record, indent=2).encode(),
             'metrics.csv': metrics_csv(record), 'difference.png': difference,
             'prediction.zip': bundle, 'reference.png': reference, 'report.md': report.encode()}
    manifest = {'schema': 'geomasklab-reference-packet/1.0',
                'checksums': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in files.items()},
                'verification_scope': 'File consistency and reproducible arithmetic; not authenticated reference provenance.'}
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in files.items(): z.writestr(name, raw)
        z.writestr('manifest.json', json.dumps(manifest, indent=2))
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path, nargs='?'); parser.add_argument('reference', type=Path, nargs='?')
    parser.add_argument('--source'); parser.add_argument('--target')
    parser.add_argument('--independent', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-packet', type=Path)
    args = parser.parse_args()
    from datetime import datetime, timezone
    try:
        if args.verify_packet:
            if any((args.bundle,args.reference,args.source,args.target,args.output,args.independent)):
                parser.error('Packet verification cannot be combined with evaluation inputs.')
            print(json.dumps(verify_reference_packet(args.verify_packet.read_bytes()),indent=2))
            return
        if not all((args.bundle,args.reference,args.source,args.target,args.output)):
            parser.error('Evaluation requires prediction evidence, reference, --source, --target and --output.')
        bundle, reference = args.bundle.read_bytes(), args.reference.read_bytes()
        record, difference = evaluate_reference(bundle, reference, source=args.source, target=args.target,
                                                independent=args.independent, created_at=datetime.now(timezone.utc).isoformat())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(evaluation_packet(record, difference, bundle, reference))
        print(json.dumps({'output': str(args.output), 'counts': record['counts'], 'metrics': record['metrics']}, indent=2))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, 'Evaluation failed: '+str(error)+'\n')


def verify_reference_packet(payload):
    """Check packet membership/hashes and replay scoring, without extracting files."""
    limit=192*1024*1024
    required={'prediction.zip','reference.png','evaluation.json','metrics.csv','difference.png','report.md'}
    if len(payload)>limit:raise ValueError('Assessment packet exceeds the size limit.')
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        if len(names)!=7 or set(names)!=required|{'manifest.json'} or sum(i.file_size for i in infos)>limit:
            raise ValueError('Invalid assessment packet membership or expanded size.')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('schema')!='geomasklab-reference-packet/1.0' or set(manifest.get('checksums',{}))!=required:
            raise ValueError('Invalid assessment manifest.')
        files={name:z.read(name) for name in required}
    for name,raw in files.items():
        if manifest['checksums'][name]!={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}:
            raise ValueError('Assessment checksum mismatch: '+name)
    recorded=json.loads(files['evaluation.json'])
    reference=recorded['reference']
    recomputed,difference=evaluate_reference(files['prediction.zip'],files['reference.png'],
        source=reference['source'],target=recorded['target'],independent=reference['independent_user_assertion'],
        created_at=recorded['created_at'])
    # The software used to verify an older packet can have a newer version.
    recomputed['software_version']=recorded.get('software_version')
    if recomputed!=recorded:
        raise ValueError('Recorded reference assessment disagrees with recomputed pixels or provenance.')
    if files['metrics.csv']!=metrics_csv(recomputed):
        raise ValueError('Assessment CSV disagrees with recomputed metrics.')
    with Image.open(io.BytesIO(files['difference.png'])) as a, Image.open(io.BytesIO(difference)) as b:
        if a.mode!=b.mode or a.size!=b.size or a.tobytes()!=b.tobytes():
            raise ValueError('Assessment error image disagrees with recomputed pixels.')
    return {'verified':True,'files_checked':6,'evaluated_pixels':recomputed['evaluated_pixels'],
            'counts':recomputed['counts'],'metrics':recomputed['metrics'],'origin_authenticated':False,
            'independent_reference_verified':False}
