"""Installed entry points for deterministic evidence workflows."""
import argparse
import io
from importlib.resources import files
import json
from pathlib import Path
import sys
import zipfile
from ._version import VERSION
from .api import create_evidence, recalculate_evidence
from .evidence import verify_bundle, load_verified_bundle
from .reference import evaluate_reference, evaluation_packet, verify_reference_packet


def write(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)


def main(argv=None):
    parser=argparse.ArgumentParser(prog='geomasklab',description='Replayable scoped-mask measurements and evidence.')
    parser.add_argument('--version',action='version',version=VERSION)
    sub=parser.add_subparsers(dest='command',required=True)
    verify=sub.add_parser('verify',help='Check evidence integrity and replay pixel measurements.')
    verify.add_argument('bundle',type=Path)
    verify.add_argument('--schema',action='store_true',help='Also validate metadata using the optional schema extra.')
    recalc=sub.add_parser('recalc',help='Derive another spatial scope without model inference.')
    recalc.add_argument('bundle',type=Path);recalc.add_argument('--output',type=Path,required=True)
    recalc.add_argument('--scope',choices=['all','left','right','top','bottom'],default='all')
    recalc.add_argument('--roi',type=int,nargs=4,metavar=('X1','Y1','X2','Y2'))
    create=sub.add_parser('create',help='Create evidence from an aligned external binary mask.')
    create.add_argument('--image',type=Path,required=True);create.add_argument('--mask',type=Path,required=True)
    create.add_argument('--target',choices=['building','aircraft','road','water','tree','ship'],required=True)
    create.add_argument('--source',required=True);create.add_argument('--output',type=Path,required=True)
    create.add_argument('--provider-info',type=Path,help='Optional provider sidecar whose mask hash must match.')
    create.add_argument('--aligned',action='store_true',required=True,help='Assert alignment with the normalized displayed image.')
    assess=sub.add_parser('evaluate',help='Assess a saved result against supplied positive-target labels.')
    assess.add_argument('bundle',type=Path);assess.add_argument('reference',type=Path)
    assess.add_argument('--source',required=True);assess.add_argument('--target',required=True)
    assess.add_argument('--aligned',action='store_true',required=True)
    assess.add_argument('--independent',action='store_true');assess.add_argument('--output',type=Path,required=True)
    packet=sub.add_parser('verify-assessment',help='Replay scores and check a reference-assessment packet.')
    packet.add_argument('packet',type=Path)
    report=sub.add_parser('report',help='Render verified evidence as a standalone English HTML report.')
    report.add_argument('bundle',type=Path);report.add_argument('--output',type=Path,required=True)
    segment=sub.add_parser('segment',help='Run a local color baseline or an explicit external-command adapter.')
    segment.add_argument('image',type=Path);segment.add_argument('--output',type=Path,required=True)
    segment.add_argument('--provider',choices=['exg','command'],default='exg')
    segment.add_argument('--threshold',type=float)
    segment.add_argument('--argv-json',type=Path,help='JSON executable argument array containing {image} and {output}.')
    segment.add_argument('--timeout',type=float,default=300)
    schema=sub.add_parser('schema',help='Print a packaged JSON Schema.')
    schema.add_argument('kind',choices=['manifest','result','statistics'],default='manifest',nargs='?')
    args=parser.parse_args(argv)
    try:
        if args.command=='verify':
            raw=args.bundle.read_bytes();out,contents=load_verified_bundle(raw)
            if args.schema:
                from .schema import validate_metadata
                with zipfile.ZipFile(io.BytesIO(raw)) as z:manifest=json.loads(z.read('manifest.json'))
                validate_metadata(contents,manifest);out['metadata_schema_validated']=True
        elif args.command=='recalc':
            raw=args.bundle.read_bytes();facts,_=load_verified_bundle(raw)
            roi={'xyxy':args.roi,'source':'imported','image_size':[facts['width'],facts['height']]} if args.roi else None
            raw=recalculate_evidence(raw,scope=args.scope,roi=roi);write(args.output,raw)
            out={'output':str(args.output),**verify_bundle(raw)}
        elif args.command=='create':
            info=json.loads(args.provider_info.read_text(encoding='utf-8')) if args.provider_info else None
            raw=create_evidence(args.image.read_bytes(),args.mask.read_bytes(),target=args.target,source=args.source,aligned=args.aligned,provider_info=info)
            write(args.output,raw);out={'output':str(args.output),**verify_bundle(raw)}
        elif args.command=='evaluate':
            from .api import timestamp
            raw,ref=args.bundle.read_bytes(),args.reference.read_bytes()
            record,difference=evaluate_reference(raw,ref,source=args.source,target=args.target,
                independent=args.independent,created_at=timestamp())
            write(args.output,evaluation_packet(record,difference,raw,ref))
            out={'output':str(args.output),'counts':record['counts'],'metrics':record['metrics']}
        elif args.command=='verify-assessment':out=verify_reference_packet(args.packet.read_bytes())
        elif args.command=='report':
            from .report import build_report
            write(args.output,build_report(args.bundle.read_bytes()).encode('utf-8'))
            out={'output':str(args.output),'verification':'passed'}
        elif args.command=='segment':
            from .providers import ExcessGreenProvider,CommandProvider
            if args.provider=='command':
                if not args.argv_json:raise ValueError('The command provider requires --argv-json.')
                if args.threshold is not None:raise ValueError('--threshold is only available for the exg provider.')
                provider=CommandProvider(json.loads(args.argv_json.read_text(encoding='utf-8')),args.timeout)
            else:
                if args.argv_json:raise ValueError('--argv-json is only available for the command provider.')
                provider=ExcessGreenProvider(args.threshold)
            product=provider.produce(args.image.read_bytes())
            write(args.output,product.mask)
            write(Path(str(args.output)+'.provider.json'),json.dumps(product.metadata,indent=2).encode('utf-8'))
            out={'output':str(args.output),'provider':product.metadata}
        else:
            print(files('geomasklab').joinpath('schemas',args.kind+'-1.0.schema.json').read_text(encoding='utf-8'))
            return 0
        print(json.dumps(out,indent=2));return 0
    except (ValueError,KeyError,TypeError,OSError,zipfile.BadZipFile) as error:
        print('Operation failed: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
