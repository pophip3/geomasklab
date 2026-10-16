"""Run the fixed 65-scene water V5 assessment from checkpoint and RGB rasters."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEIGHT_SHA256 = 'ef86d7d5c4e1b9c30762f72a5435b59efe2da917e5a04a9b2364bf977a85596e'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def starts(length):
    if length <= 512:
        return [0]
    values = list(range(0, length - 512 + 1, 256))
    if values[-1] != length - 512:
        values.append(length - 512)
    return values


def predict(model, refiner, image, torch, np, device):
    rgb = np.asarray(image.convert('RGB'))
    accumulated = np.zeros((image.height, image.width), dtype=np.float32)
    weights = np.zeros_like(accumulated)
    window = np.maximum(np.outer(np.hanning(512), np.hanning(512)), 0.05).astype(np.float32)
    with torch.inference_mode():
        for top in starts(image.height):
            for left in starts(image.width):
                crop = rgb[top:top + 512, left:left + 512]
                height, width = crop.shape[:2]
                if height < 512 or width < 512:
                    crop = np.pad(crop, ((0, 512-height), (0, 512-width), (0, 0)), mode='edge')
                pixels = torch.from_numpy(crop.copy()).permute(2, 0, 1).float().div(255).unsqueeze(0).to(device)
                probability = 0
                for rotation in range(4):
                    logits = model(torch.rot90(pixels, rotation, (-2, -1))).float()
                    p = logits.softmax(dim=1)[:, 6:7]
                    p = torch.nn.functional.interpolate(p, size=(512, 512), mode='bilinear', align_corners=False)
                    probability = probability + torch.rot90(p, -rotation, (-2, -1)) / 4
                p = probability[0, 0, :height, :width].cpu().numpy()
                weighted = window[:height, :width]
                accumulated[top:top+height, left:left+width] += p * weighted
                weights[top:top+height, left:left+width] += weighted
    return refiner.refine(image, accumulated / weights >= 0.5)


def run(args):
    import numpy as np
    import torch
    import segmentation_models_pytorch as smp
    from safetensors.torch import load_file
    from PIL import Image
    from refinement import WaterBoundaryRefiner
    torch.set_num_threads(2)
    if digest(args.weights) != WEIGHT_SHA256:
        raise ValueError('V5 checkpoint SHA-256 mismatch.')
    scenes = json.loads((HERE / 'scene_manifest.json').read_text(encoding='utf-8'))['scenes']
    expected = json.loads((HERE / 'expected_results.json').read_text(encoding='utf-8'))
    model = smp.Unet(classes=9, activation=None, encoder_weights=None,
                     encoder_name='efficientnet-b4', decoder_attention_type='scse')
    model.load_state_dict(load_file(str(args.weights)), strict=True)
    model.to(args.device).eval()
    refiner = WaterBoundaryRefiner(args.sam_checkpoint, args.device)
    args.output.mkdir(parents=True, exist_ok=True)
    index = {}
    for path in args.data_root.rglob('*.tif'):
        if path.parent.name in ('images', 'labels'):
            index.setdefault((path.parent.name, path.name), []).append(path)
    records = []
    for number, item in enumerate(scenes, 1):
        paths = {}
        for kind, field in (('images', 'image'), ('labels', 'label')):
            candidates = index.get((kind, item[field]), [])
            paths[field] = next((p for p in candidates if digest(p) == item[field + '_sha256']), None)
            if paths[field] is None:
                raise ValueError('Missing or changed source raster: ' + item['region'] + '/' + kind + '/' + item[field])
        with Image.open(paths['image']) as source:
            mask = predict(model, refiner, source.convert('RGB'), torch, np, args.device)
        with Image.open(paths['label']) as source:
            labels = np.asarray(source)
        truth, valid = labels == 6, labels > 0
        counts = {'tp': int((mask & truth & valid).sum()),
                  'fp': int((mask & ~truth & valid).sum()), 'fn': int((~mask & truth & valid).sum())}
        row = {'region': item['region'], 'image': item['image'], **counts}
        reference = expected['scenes'][number - 1]
        row['matches_recorded_counts'] = all(counts[key] == reference[key] for key in counts)
        Image.fromarray((mask * 255).astype(np.uint8)).save(args.output / (Path(item['image']).stem + '-mask.png'))
        records.append(row)
        print(f'Scene {number}/65: {item["image"]}; counts match: {row["matches_recorded_counts"]}', flush=True)
    total = {key: sum(row[key] for row in records) for key in ('tp', 'fp', 'fn')}
    tp, fp, fn = (total[key] for key in ('tp', 'fp', 'fn'))
    metrics = {'iou': tp/(tp+fp+fn), 'dice': 2*tp/(2*tp+fp+fn),
               'precision': tp/(tp+fp), 'recall': tp/(tp+fn)}
    result = {'weights_sha256': WEIGHT_SHA256, 'scene_count': len(records), 'device': args.device,
              'inference_performed': True, 'rotations_per_tile': 4, 'sam_refinement_performed': True,
              'sam_checkpoint_sha256': refiner.metadata['refiner_checkpoint_sha256'],
              'all_scene_counts_match': all(row['matches_recorded_counts'] for row in records),
              **total, **metrics, 'scenes': records}
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'scenes'}, indent=2), flush=True)
    if not result['all_scene_counts_match']:
        raise ValueError('Inference completed; one or more scene counts differ from the archived run. See results.json.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--sam-checkpoint', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('output/water-v5'))
    parser.add_argument('--device', default='cuda:0')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
