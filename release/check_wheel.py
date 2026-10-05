"""Install the wheel and exercise its CLI outside the source checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel-dir',type=Path,required=True)
    parser.add_argument('--python',help='Existing minimal interpreter containing Pillow and pip.')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    wheels=list(args.wheel_dir.resolve().glob('geomasklab-*.whl'))
    if len(wheels)!=1:raise ValueError('Expected exactly one GeoMaskLab wheel in the selected directory.')
    wheel=wheels[0]
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
    env['PYTHONUTF8']='1'
    checks=[]
    with tempfile.TemporaryDirectory(prefix='geomasklab-installed-wheel-') as folder:
        work=Path(folder)
        python=Path(args.python).resolve() if args.python else work/'env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        def run(*argv):
            process=subprocess.run([str(python),*argv],cwd=work,env=env,capture_output=True,
                text=True,encoding='utf-8',check=True,timeout=90)
            return process.stdout
        if not args.python:
            venv.EnvBuilder(with_pip=True).create(work/'env')
            run('-m','pip','install','Pillow>=10,<13')
        run('-m','pip','install','--no-index','--no-deps','--force-reinstall',str(wheel))
        identity=json.loads(run('-I','-c',
            'import geomasklab,json,importlib.metadata as m; print(json.dumps({"path":geomasklab.__file__,"version":geomasklab.__version__,"requirements":m.requires("geomasklab")}))'))
        if 'site-packages' not in identity['path'].replace('\\','/'):
            raise ValueError('Core was not imported from installed site-packages.')
        base=[r for r in identity['requirements'] if ';' not in r]
        if len(base)!=1 or not base[0].lower().startswith('pillow'):
            raise ValueError('Headless runtime must require only Pillow.')
        checks.append('Installed core import and Pillow-only dependencies')
        run('-I','-c','from PIL import Image; a=Image.new("RGB",(7,5),(40,180,40)); a.save("image.png"); m=Image.new("L",(7,5)); m.paste(255,(1,1,5,4)); m.save("mask.png")')
        def cli(*argv):return run('-I','-m','geomasklab',*argv)
        cli('create','--image','image.png','--mask','mask.png','--target','tree','--source','Hand-counted fixture',
            '--aligned','--output','evidence.zip')
        whole=json.loads(cli('verify','evidence.zip'))
        assert whole['pixel_area']==12
        scoped=json.loads(cli('recalc','evidence.zip','--scope','right','--output','right.zip'))
        assert scoped['pixel_area']==6
        cli('report','right.zip','--output','report.html')
        text=(work/'report.html').read_text(encoding='utf-8')
        assert 'Selected-region denominator' in text and '<html lang="en">' in text
        checks.append('Create, verify, derive and English standalone report')
        cli('evaluate','evidence.zip','mask.png','--source','Procedural reference, not a real accuracy study',
            '--target','tree','--aligned','--output','assessment.zip')
        json.loads(cli('verify-assessment','assessment.zip'))
        checks.append('Reference packet creation and independent replay')
        cli('segment','image.png','--output','baseline.png')
        assert (work/'baseline.png.provider.json').is_file()
        checks.append('Local reproducible RGB provider')
        cli('provenance','evidence.zip','--output','provenance.json')
        assert json.loads(cli('verify-provenance','evidence.zip','provenance.json'))['verified']
        checks.append('PROV-JSON export and source-bound replay without extra dependencies')
        for name in ('manifest','result','statistics','geospatial'):
            schema=json.loads(cli('schema',name));assert schema['$schema'].endswith('2020-12/schema')
        checks.append('Packaged JSON Schema resources')
        scripts=python.parent/('geomasklab.exe' if os.name=='nt' else 'geomasklab')
        version=subprocess.run([str(scripts),'--version'],cwd=work,env=env,capture_output=True,
            text=True,check=True,timeout=15).stdout.strip()
        assert version==identity['version']
        checks.append('Installed console entry point')
    report={'passed':True,'version':identity['version'],'wheel':wheel.name,
        'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
        'installed_core_path':identity['path'],'checks':checks,
        'runtime_dependencies':base,'execution':'Outside checkout, isolated Python import, no model or browser server',
        'platform':sys.platform,'python':sys.version.split()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
