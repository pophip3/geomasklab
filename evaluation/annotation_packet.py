"""Ground-truth review packet: publisher labels only; no model output is shown."""
import argparse,csv,json,html
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root
    rows=list(csv.DictReader((root/'manifest.csv').open(encoding='utf-8')));out=root/'annotation-review';out.mkdir(exist_ok=True)
    review=[];font=ImageFont.load_default(size=16)
    for target in ['building','aircraft']:
        group=sorted([r for r in rows if r['target']==target],key=lambda r:(r['stratum'],r['image_id']))
        for page in range(5):
            sheet=Image.new('RGB',(1560,1140),'white');draw=ImageDraw.Draw(sheet)
            draw.text((20,10),f'{target}: source human labels (green), ignored pixels (purple); no model predictions',fill='black',font=font)
            for i,r in enumerate(group[page*6:page*6+6]):
                x=20+(i%3)*520;y=48+(i//3)*540
                im=Image.open(root/r['image_path']).convert('RGB');gt=np.asarray(Image.open(root/r['ground_truth_path']))>0;valid=np.asarray(Image.open(root/r['valid_path']))>0
                rgb=np.array(im);rgb[gt]=(.5*rgb[gt]+.5*np.array([0,255,100])).astype('uint8');rgb[~valid]=np.array([160,0,180])
                preview=Image.fromarray(rgb);preview.thumbnail((500,475));sheet.paste(preview,(x,y))
                draw.text((x,y+480),r['image_id']+' / '+r['stratum'],fill='black',font=font)
                draw.text((x,y+505),f"GT={r['gt_foreground_pixels']} px; valid={r['valid_pixels']} px",fill='black',font=font)
            sheet.save(out/f'{target}-ground-truth-{page+1}.png')
    for r in rows:
        im=Image.open(root/r['image_path']);gt=np.asarray(Image.open(root/r['ground_truth_path']));v=np.asarray(Image.open(root/r['valid_path']))
        assert im.size==(gt.shape[1],gt.shape[0]) and gt.shape==v.shape
        assert set(np.unique(gt)).issubset({0,255}) and set(np.unique(v)).issubset({0,255})
        assert int((gt>0).sum())==int(r['gt_foreground_pixels']) and int((v>0).sum())==int(r['valid_pixels'])
        review.append({'image_id':r['image_id'],'target':r['target'],'dataset':r['dataset'],'stratum':r['stratum'],
                       'source_label_sha256':r['source_label_sha256'],'gt_sha256':r['ground_truth_sha256'],
                       'dimensions_binary_counts_check':'passed','human_label_origin':'Original dataset annotators',
                       'independent_human_reviewer':'','human_review_status':'not performed','review_notes':''})
    with (out/'human_review_sheet.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(review[0]));w.writeheader();w.writerows(review)
    body=''.join(f'<h2>{t}</h2>'+''.join(f'<img src="{t}-ground-truth-{i}.png" style="width:100%;max-width:1560px">' for i in range(1,6)) for t in ['building','aircraft'])
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>人工标注复核包</title><body style="font-family:Arial;max-width:1600px;margin:auto"><h1>GeoScope 独立评测人工标注复核包</h1><p>60 组公开数据原作者的人工像素标注。绿色为目标，紫色为忽略像素。这里只展示真值，不展示模型输出。尺寸、二值范围、像素数量已自动校验；新增人工复核尚未进行，复核表未填写人员姓名或签字。</p>'+body+'</body>',encoding='utf-8')
    print('ANNOTATION_PACKET',len(review),'pairs; 10 sheets; no new human review claimed')
if __name__=='__main__':main()
