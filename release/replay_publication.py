"""Replay unchanged rc4 publication packets with the installed current release.

This checks decoded arithmetic/reports and original input hashes; it does not
test byte identity of newly generated ZIP files on different platforms.
"""
import argparse, hashlib, importlib, io, json, math, platform, subprocess, sys, urllib.request, zipfile
from pathlib import Path
import geomasklab
from PIL import __version__ as pillow_version

BASE=Path(__file__).with_name('publication-replay-baseline.json')
URL='https://github.com/pophip3/geomasklab/releases/download/v1.0.0rc4/GeoMaskLab-rc4-independent-validation.zip'
ARCHIVE_SHA='143e72ffe6f41035c1540613b8e409fe567ddcb4b2454f68798aff4d9b1dce9b'
REGISTRY={'verify':('geomasklab.evidence','verify_bundle'),'verify-comparison':('geomasklab.comparison','verify_comparison_packet'),
          'verify-components':('geomasklab.components','verify_component_packet'),'verify-batch':('geomasklab.batch','verify_batch_packet')}
def digest(b):return hashlib.sha256(b).hexdigest()
def equal(a,b):
    if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return isinstance(b,list) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if type(a) is float:return type(b) is float and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
    return type(a) is type(b) and a==b
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path);ap.add_argument('--output',type=Path,default=Path('publication-replay-output'));args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    raw=args.archive.read_bytes() if args.archive else urllib.request.urlopen(URL,timeout=120).read()
    if args.archive is None:assert digest(raw)==ARCHIVE_SHA,'Public archive changed'
    baseline=json.loads(BASE.read_text());records=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for row in baseline['packets']:
            # The externally stored filename is secondary to its fixed byte identity.
            names=[n for n in z.namelist() if n.endswith('.zip') and digest(z.read(n))==row['sha256']]
            assert names, 'Missing fixed packet: '+row['filename']
            payload=z.read(names[0]);path=args.output/row['filename'];path.write_bytes(payload)
            op=row['original_cli_operation'];mod,fn=REGISTRY[op]
            report=getattr(importlib.import_module(mod),fn)(payload)
            result=subprocess.run([sys.executable,'-I','-m','geomasklab',op,str(path.resolve())],capture_output=True,text=True,encoding='utf-8',check=True,timeout=180)
            cli=json.loads(result.stdout)
            assert equal(row['report'],report) and equal(report,cli),'Replay report changed: '+row['filename']
            assert digest(path.read_bytes())==row['sha256']
            records.append({'filename':row['filename'],'sha256':row['sha256'],'api_verified':report['verified'],'cli_exit_code':result.returncode,'report_matches_fixed_baseline':True})
    record={'platform':platform.platform(),'python':sys.version,'geomasklab':geomasklab.__version__,'Pillow':pillow_version,
            'input_archive_sha256':digest(raw),'packet_count':len(records),'all_passed':len(records)==7,'records':records,
            'comparison':'Exact fields/types/integers; float rel_tol=abs_tol=1e-12','new_export_byte_identity_tested':False}
    (args.output/'summary.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
if __name__=='__main__':main()
