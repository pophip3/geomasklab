"""Install the wheel and exercise its CLI outside the source checkout."""
import argparse
import hashlib
import json
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
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
        for module in ('launcher', 'agent_service', 'sam_service'):
            help_text = run('-I', '-m', 'model_services.' + module, '--help')
            assert 'usage:' in help_text
        run('-I', '-c', 'import model_services,pathlib,json; root=pathlib.Path(model_services.__file__).parent; assert json.loads((root/"model-lock.json").read_text())["schema"]=="geomasklab-model-lock/1.0"; assert (root/"profile.example.json").is_file(); assert (root/"requirements-agent.txt").is_file(); assert (root/"requirements-sam.txt").is_file()')
        checks.append('Installed optional-model CLI and fixed profile/identity resources without ML dependencies')
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
        run('-I','-c','import zipfile; z=zipfile.ZipFile("assessment.zip"); text=z.read("report.md").decode(); assert "geomasklab evaluate" in text and "--aligned" in text and "python reference_evaluation.py" not in text')
        checks.append('Reference packet creation and independent replay')
        cli('segment','image.png','--output','baseline.png')
        assert (work/'baseline.png.provider.json').is_file()
        checks.append('Local reproducible RGB provider')
        cli('provenance','evidence.zip','--output','provenance.json')
        assert json.loads(cli('verify-provenance','evidence.zip','provenance.json'))['verified']
        checks.append('PROV-JSON export and source-bound replay without extra dependencies')
        run('-I','-c','import json; json.dump({"type":"Polygon","coordinates":[[[0,0],[4,0],[4,4],[0,4],[0,0]]]},open("zones.geojson","w"))')
        cli('zonal','evidence.zip','zones.geojson','--output','zones.zip')
        zones=json.loads(cli('verify-zonal','zones.zip'))
        assert zones['zones'][0]['foreground_pixels']==9
        assert zones['zones'][0]['selected_region_pixels']==16
        checks.append('Pillow-only polygon-domain packet and numerical replay')
        run('-I','-c','from PIL import Image; m=Image.new("L",(7,5)); m.paste(255,(0,0,3,5)); m.save("valid.png")')
        cli('create','--image','image.png','--mask','mask.png','--target','tree','--source','Installed fixture',
            '--valid-mask','valid.png','--valid-source','Explicit left-side fixture','--aligned','--output','valid.zip')
        valid=json.loads(cli('verify','valid.zip'))
        assert valid['pixel_area']==6 and valid['validity_measurements']['valid_region_pixels']==15
        empty=json.loads(cli('recalc','valid.zip','--scope','right','--output','empty-valid.zip'))
        assert empty['validity_measurements']['valid_region_pixels']==0 and empty['validity_measurements']['coverage_of_valid_region'] is None
        cli('evaluate','valid.zip','mask.png','--source','Installed reference fixture','--target','tree','--aligned','--output','valid-assessment.zip')
        assert json.loads(cli('verify-assessment','valid-assessment.zip'))['verified']
        checks.append('Installed validity-aware evidence, empty-domain handling and reference replay')
        cli('compare','evidence.zip','valid.zip','--domain-policy','intersection','--output','comparison.zip')
        comparison=json.loads(cli('verify-comparison','comparison.zip'))['comparison']
        assert comparison['change_kind']=='Analysis_Conditions_Only' and comparison['shared_foreground_pixels']==6
        assert comparison['changed_pixels']==0 and comparison['foreground_change_accounting']['saved_total_delta_pixels']==-6
        cli('inspect','valid.zip','--min-area-pixels','2','--boundary-filter','all','--output','components.zip')
        inspected=json.loads(cli('verify-components','components.zip'))
        assert inspected['verified']
        run('-I','-c','import json,zipfile; r=json.loads(zipfile.ZipFile("components.zip").read("inspection.json")); assert r["foreground_pixels"]==6 and r["selected_component_count"]==1 and r["components"][0]["touches_invalid_boundary"]')
        checks.append('Installed fair-comparison accounting and non-mutating boundary inspection packets')
        run('-I','-c','import json; sample={"id":"fixture","image":"image.png","mask":"mask.png","target":"tree","source":"Installed independent pixel fixture","aligned":True,"valid_mask":"valid.png","valid_source":"Explicit installed fixture"}; json.dump({"schema":"geomasklab-batch-manifest/1.0","samples":[sample]},open("batch.json","w"))')
        batch=json.loads(cli('batch','batch.json','--output','batch-results'))
        assert batch['completed_count']==1 and batch['aggregate']['macro_mean_coverage']==.4
        cli('batch','batch.json','--output','batch-results','--resume')
        cli('export-batch','batch-results','--output','batch.zip')
        replayed=json.loads(cli('verify-batch','batch.zip'));assert replayed['verified'] and replayed['samples'][0]['foreground_pixels']==6
        checks.append('Installed explicit-manifest batch, verified exact-identity resume and offline packet replay')
        for name in ('manifest','manifest-v2','analysis','validity','result','statistics','geospatial','zonal','signature','comparison','comparison-packet','components','batch'):
            schema=json.loads(cli('schema',name));assert schema['$schema'].endswith('2020-12/schema')
        checks.append('Packaged JSON Schema resources')
        scripts=python.parent/('geomasklab.exe' if os.name=='nt' else 'geomasklab')
        version=subprocess.run([str(scripts),'--version'],cwd=work,env=env,capture_output=True,
            text=True,check=True,timeout=15).stdout.strip()
        assert version==identity['version']
        checks.append('Installed console entry point')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        process = subprocess.Popen([str(python), '-I', '-m', 'workbench.launcher', '--port', str(port)],
                                   cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Installed workbench exited before readiness')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=1) as response:
                        status = json.load(response)
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Installed workbench did not start')
            assert status['version'] == identity['version']
            for resource in ('index.html', 'presentation.js', 'presentation.css', 'help.html',
                             'assets/urban.png', 'assets/airport.jpg', 'assets/naip-preview.png',
                             'assets/naip-preview-mask.png', 'assets/naip-preview-provenance.json'):
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/' + resource, timeout=2) as response:
                    raw = response.read()
                assert raw, resource
                if resource == 'index.html':
                    assert b'presentation.js' in raw and b'presentation.css' in raw
            assert (work / 'experiments').is_dir(), 'Installed sessions must use a writable working directory'
            ui_script = python.parent / ('geomasklab-ui.exe' if os.name == 'nt' else 'geomasklab-ui')
            help_result = subprocess.run([str(ui_script), '--help'], cwd=work, env=env,
                                         capture_output=True, text=True, check=True, timeout=15)
            assert '--data-dir' in help_result.stdout
            checks.append('Complete installed browser assets, matching API version, writable storage and UI console entry point')
        finally:
            process.terminate()
            process.communicate(timeout=10)
    report={'passed':True,'version':identity['version'],'wheel':wheel.name,
        'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
        'installed_core_path':identity['path'],'checks':checks,
        'runtime_dependencies':base,'execution':'Outside checkout, isolated imports, installed local browser server and offline CLI; no model service',
        'platform':sys.platform,'python':sys.version.split()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
