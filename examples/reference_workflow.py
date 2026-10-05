"""Reproduce external-mask import and reference evaluation without model services.

All data are procedural diagrams. Scores validate software arithmetic only.
"""
import argparse
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from workbench import server
from workbench.export_bundle import build_bundle, load_verified_bundle
from workbench.reference_evaluation import evaluate_reference, evaluation_packet, verify_reference_packet


def encoded(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('workflow-output/reference-example'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    size=(480,320);image=Image.new('RGB',size,'#354f5c');draw=ImageDraw.Draw(image)
    draw.rectangle((0,158,479,183),fill='#263b49')
    ref=Image.new('L',size);pred=Image.new('L',size)
    boxes=[(40,50,140,130),(250,45,360,115),(100,210,160,300)]
    for box in boxes:
        ref.paste(255,box);draw.rectangle((box[0],box[1],box[2]-1,box[3]-1),fill='#a5b9c0',outline='#d2e2e4',width=2)
    pred.paste(255,boxes[0]);pred.paste(255,(250,45,350,115));pred.paste(255,(380,225,430,275))
    raw_image,raw_pred,raw_ref=map(encoded,(image,pred,ref))
    for name,raw in (('image.png',raw_image),('prediction.png',raw_pred),('reference.png',raw_ref)):
        (args.output/name).write_bytes(raw)
    with tempfile.TemporaryDirectory(prefix='geomasklab-reference-example-') as directory, \
         patch.object(server,'DATA',Path(directory)),patch.object(server,'SESSIONS',{}), \
         patch.object(server,'post_json',side_effect=AssertionError('Offline example must not infer')):
        session=server.SESSIONS[server.new_session(uploaded=base64.b64encode(raw_image).decode(),name='Procedural reference assessment')['id']]
        run=server.import_mask(session,{'mask':base64.b64encode(raw_pred).decode(),'target':'building','aligned':True,
            'source':'Procedural imperfect prediction: one missing rectangle, one clipped edge and one false positive.'})
        bundle=build_bundle(server.DATA/session['id']/'original.png',server.DATA/session['id']/run['id'])
        load_verified_bundle(bundle)
        record,diff=evaluate_reference(bundle,raw_ref,source='Exact procedural rectangle labels; not EO observations or independent neural validation.',
            target='building',independent=False,created_at=server.now())
        expected={'tp':15000,'fp':2500,'fn':6100,'tn':130000}
        if record['counts']!=expected:raise AssertionError('Hand-counted pixel confusion does not match.')
        if record['metrics']['iou']!=15000/23600:raise AssertionError('IoU denominator does not match.')
        packet=evaluation_packet(record,diff,bundle,raw_ref)
        verify_reference_packet(packet)
        (args.output/'prediction.zip').write_bytes(bundle);(args.output/'evaluation.zip').write_bytes(packet)
        (args.output/'difference.png').write_bytes(diff)
        (args.output/'evaluation.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
        before=len(session['runs'])
        server.assess_reference(session,{'run_id':run['id'],'reference':base64.b64encode(raw_ref).decode(),
            'source':record['reference']['source'],'target':'building','independent':False,'aligned':True})
        if len(session['runs'])!=before:raise AssertionError('Evaluation changed prediction history.')
    print(json.dumps({'passed':True,'counts':expected,'metrics':record['metrics'],
                      'model_calls':0,'data':'Procedural diagrams; software behavior check only.'},indent=2))


if __name__=='__main__':main()
