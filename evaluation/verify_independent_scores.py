"""Separate Pillow boolean arithmetic audits NumPy scores and label conversion."""
import argparse,csv,hashlib,io,json,math,zipfile
from pathlib import Path
from PIL import Image,ImageChops

def binary(image):return image.convert('L').point(lambda x:255 if x else 0).convert('1')
def count(image):return image.convert('L').histogram()[255]
def audit(pred,gt,valid,scope,record):
    w,h=pred.size;box={'whole':(0,0,w,h),'right':(w//2,0,w,h),'roi':(w//4,h//4,3*w//4,3*h//4)}[scope]
    p,g,v=[binary(im.crop(box)) for im in (pred,gt,valid)]
    AND=ImageChops.logical_and;NOT=ImageChops.invert
    counts={'tp':count(AND(AND(p,g),v)),'fp':count(AND(AND(p,NOT(g)),v)),
            'fn':count(AND(AND(NOT(p),g),v)),'tn':count(AND(AND(NOT(p),NOT(g)),v))}
    for key,n in counts.items():
        if record[key]!=n:raise ValueError(f'{key} confusion mismatch')
    tp,fp,fn=counts['tp'],counts['fp'],counts['fn'];union=tp+fp+fn;denom=2*tp+fp+fn
    for key,val in [('iou',tp/union if union else None),('dice',2*tp/denom if denom else None)]:
        if (val is None and record[key] is not None) or (val is not None and not math.isclose(val,record[key],rel_tol=1e-12,abs_tol=1e-12)):
            raise ValueError(key+' mismatch')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root
    lock=json.loads((root/'data-lock.json').read_text(encoding='utf-8'))
    if hashlib.sha256((root/'manifest.csv').read_bytes()).hexdigest()!=lock['manifest_sha256']:raise ValueError('Frozen manifest changed')
    rows=list(csv.DictReader((root/'manifest.csv').open(encoding='utf-8')));checked=0;conversions=0;image_hashes=set();files_checked=0
    for row in rows:
        for path_key,hash_key in [('image_path','image_sha256'),('ground_truth_path','ground_truth_sha256'),('valid_path','valid_sha256'),('original_label_path','source_label_sha256')]:
            if hashlib.sha256((root/row[path_key]).read_bytes()).hexdigest()!=row[hash_key]:raise ValueError('Frozen image/annotation file changed')
            files_checked+=1
        gt=Image.open(root/row['ground_truth_path']);valid=Image.open(root/row['valid_path']);original=Image.open(root/row['original_label_path'])
        image=Image.open(root/row['image_path']).convert('RGB');pixel_hash=hashlib.sha256(image.tobytes()).hexdigest()
        if pixel_hash in image_hashes:raise ValueError('Exact image-pixel duplicate')
        image_hashes.add(pixel_hash)
        if row['target']=='building':
            label=original.convert('L');expected=label.point(lambda x:255 if x==2 else 0);expected_valid=label.point(lambda x:255 if x else 0)
        else:
            rgb=original.convert('RGB');r,g,b=rgb.split()
            expected=ImageChops.multiply(ImageChops.multiply(r.point(lambda x:255 if x==0 else 0),g.point(lambda x:255 if x==127 else 0)),b.point(lambda x:255 if x==255 else 0))
            expected_valid=Image.new('L',rgb.size,255)
        if expected.tobytes()!=gt.tobytes() or expected_valid.tobytes()!=valid.tobytes():raise ValueError('Source human annotation conversion mismatch')
        conversions+=1
        folder=root/'runs'/row['image_id'];receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
        if not receipt.get('finished'):raise ValueError('Evaluation is still incomplete')
        for event in receipt['outcomes']:
            if not event.get('success'):continue
            method=event['method'];scope='whole' if method=='fixed_direct' else method
            if method=='fixed_direct':pred=Image.open(folder/(method+'-mask.png'));audit(pred,gt,valid,scope,event['score']);checked+=1
            else:
                with zipfile.ZipFile(folder/(method+'-evidence.zip')) as z:pred=Image.open(io.BytesIO(z.read('mask.png')));audit(pred,gt,valid,scope,event['score']);checked+=1
                if event.get('matched_direct_score'):
                    audit(Image.open(folder/(method+'-matched-direct-mask.png')),gt,valid,scope,event['matched_direct_score']);checked+=1
    result={'verified':True,'frozen_input_file_hashes_checked':files_checked,'human_label_conversions_checked':conversions,'unique_image_pixel_hashes':len(image_hashes),
            'confusion_tables_and_scores_checked':checked,'implementation':'Pillow ImageChops boolean masks; independent of NumPy scoring implementation',
            'human_annotation_accuracy_certified':False}
    (root/'independent-score-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
