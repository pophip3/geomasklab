"""Optional interoperability adapter: verified masks become predictions, never truth."""
import argparse
import base64
import importlib.util
import json
from importlib.metadata import distribution
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape
from workbench.export_bundle import load_verified_bundle


def official_brush():
    """Load the SDK's self-contained converter without importing its API client."""
    path=distribution('label-studio-sdk').locate_file('label_studio_sdk/converter/brush.py')
    spec=importlib.util.spec_from_file_location('geoscope_official_ls_brush',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def convert_bundle(payload, brush):
    """Encode a checked mask using the official SDK; preserve provenance in metadata."""
    facts,files=load_verified_bundle(payload)
    run=json.loads(files['result.json'])
    label=('non-' if run['task'].get('invert') else '')+run['task']['target']
    with TemporaryDirectory() as temp:
        path=Path(temp)/'mask.png';path.write_bytes(files['mask.png'])
        prediction=brush.image2annotation(str(path),label,'target','image',
                                         model_version='GeoScope:'+run.get('software_version','unrecorded'))
    # Official helper sets origin=manual even for preannotations. Keep our output truthful.
    for region in prediction['result']:region['origin']='prediction'
    prediction.pop('score',None)  # No calibrated confidence available.
    task={'data':{'image':'data:image/png;base64,'+base64.b64encode(files['original.png']).decode()},
          'predictions':[prediction],'annotations':[],
          'meta':{'geoscope_run_id':run['id'],'geoscope_mode':run['mode'],
                  'image_sha256':run['provenance']['image_sha256'],
                  'geoscope_task':run['task'],'geoscope_semantic_review':run.get('semantic_review'),
                  'semantic_accuracy_verified':False}}
    config=f'<View><Image name="image" value="$image"/><BrushLabels name="target" toName="image"><Label value="{escape(label)}"/></BrushLabels></View>'
    return task,config,facts


def main():
    parser=argparse.ArgumentParser(description='Convert verified GeoScope evidence into Label Studio brush preannotations.')
    parser.add_argument('bundle',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try: task,config,_=convert_bundle(args.bundle.read_bytes(),official_brush())
    except Exception as error:parser.exit(1,'Export failed: '+str(error)+'\n')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'tasks.json').write_text(json.dumps([task],ensure_ascii=False),encoding='utf-8')
    (args.output/'label_config.xml').write_text(config,encoding='utf-8')
    print('Wrote tasks.json and label_config.xml. These are predictions, not accepted annotations.')


if __name__=='__main__':main()
