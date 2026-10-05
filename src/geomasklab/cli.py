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
    create.add_argument('--target',required=True,help='Positive semantic label; 1-64 ASCII letters/digits/underscores/hyphens.')
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
    provenance=sub.add_parser('provenance',help='Map verified evidence to PROV-JSON.')
    provenance.add_argument('bundle',type=Path);provenance.add_argument('--output',type=Path,required=True)
    provcheck=sub.add_parser('verify-provenance',help='Check a PROV-JSON mapping against its source evidence.')
    provcheck.add_argument('bundle',type=Path);provcheck.add_argument('document',type=Path)
    geo=sub.add_parser('geospatial',help='Assess a pixel result with its matching GeoTIFF (optional geo extra).')
    geo.add_argument('bundle',type=Path);geo.add_argument('raster',type=Path)
    geo.add_argument('--method',choices=['nominal','geodesic'],default='nominal')
    geo.add_argument('--output',type=Path,required=True)
    geocheck=sub.add_parser('verify-geospatial',help='Replay an optional GeoTIFF area-assessment packet.')
    geocheck.add_argument('packet',type=Path)
    render=sub.add_parser('render-raster',help='Render explicit GeoTIFF RGB bands/window with recorded scaling (optional geo extra).')
    render.add_argument('raster',type=Path);render.add_argument('--bands',type=int,nargs=3,required=True)
    render.add_argument('--window',type=int,nargs=4,metavar=('COLUMN','ROW','WIDTH','HEIGHT'))
    render.add_argument('--value-range',type=float,nargs=2,metavar=('LOW','HIGH'))
    render.add_argument('--output',type=Path,required=True)
    zones=sub.add_parser('zonal',help='Measure Polygon/MultiPolygon zones and preserve a replayable packet.')
    zones.add_argument('bundle',type=Path);zones.add_argument('geometry',type=Path)
    zones.add_argument('--coordinates',choices=['pixel','wgs84'],default='pixel')
    zones.add_argument('--raster',type=Path);zones.add_argument('--output',type=Path,required=True)
    zonecheck=sub.add_parser('verify-zonal',help='Replay polygon domains and their measurements.')
    zonecheck.add_argument('packet',type=Path)
    keygen=sub.add_parser('keygen',help='Create an optional local Ed25519 key pair; protect the private PEM.')
    keygen.add_argument('--private-key',type=Path,required=True);keygen.add_argument('--public-key',type=Path,required=True)
    sign=sub.add_parser('sign',help='Sign exact artifact bytes with a local Ed25519 private key.')
    sign.add_argument('artifact',type=Path);sign.add_argument('--private-key',type=Path,required=True);sign.add_argument('--output',type=Path,required=True)
    sigcheck=sub.add_parser('verify-signature',help='Verify a detached signature using a separately trusted public key.')
    sigcheck.add_argument('artifact',type=Path);sigcheck.add_argument('signature',type=Path);sigcheck.add_argument('--trusted-key',type=Path,required=True)
    report=sub.add_parser('report',help='Render verified evidence as a standalone English HTML report.')
    report.add_argument('bundle',type=Path);report.add_argument('--output',type=Path,required=True)
    segment=sub.add_parser('segment',help='Run a local color baseline or an explicit external-command adapter.')
    segment.add_argument('image',type=Path);segment.add_argument('--output',type=Path,required=True)
    segment.add_argument('--provider',choices=['exg','command'],default='exg')
    segment.add_argument('--threshold',type=float)
    segment.add_argument('--argv-json',type=Path,help='JSON executable argument array containing {image} and {output}.')
    segment.add_argument('--timeout',type=float,default=300)
    schema=sub.add_parser('schema',help='Print a packaged JSON Schema.')
    schema.add_argument('kind',choices=['manifest','result','statistics','geospatial','zonal','signature'],default='manifest',nargs='?')
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
        elif args.command=='provenance':
            from .provenance import provenance_document
            write(args.output,json.dumps(provenance_document(args.bundle.read_bytes()),indent=2).encode('utf-8'))
            out={'output':str(args.output),'source_verification':'passed'}
        elif args.command=='verify-provenance':
            from .provenance import verify_provenance
            out=verify_provenance(args.bundle.read_bytes(),json.loads(args.document.read_text(encoding='utf-8')))
        elif args.command=='geospatial':
            from .geospatial import geospatial_packet,verify_geospatial_packet
            raw=geospatial_packet(args.bundle.read_bytes(),args.raster.read_bytes(),method=args.method)
            out=verify_geospatial_packet(raw);write(args.output,raw);out['output']=str(args.output)
        elif args.command=='verify-geospatial':
            from .geospatial import verify_geospatial_packet
            out=verify_geospatial_packet(args.packet.read_bytes())
        elif args.command=='render-raster':
            from .raster_input import render_raster
            image,raster,out=render_raster(args.raster,bands=args.bands,window=args.window,value_range=args.value_range)
            write(args.output/'image.png',image);write(args.output/'source.tif',raster)
            write(args.output/'rendering.json',json.dumps(out,indent=2).encode())
            out={'output':str(args.output),**out}
        elif args.command=='zonal':
            from .zonal import zonal_packet,verify_zonal_packet
            raw=zonal_packet(args.bundle.read_bytes(),args.geometry.read_bytes(),coordinates=args.coordinates,
                raster=args.raster.read_bytes() if args.raster else None)
            out=verify_zonal_packet(raw);write(args.output,raw);out['output']=str(args.output)
        elif args.command=='verify-zonal':
            from .zonal import verify_zonal_packet
            out=verify_zonal_packet(args.packet.read_bytes())
        elif args.command=='keygen':
            from .signing import generate_keys
            if args.private_key.resolve()==args.public_key.resolve():raise ValueError('Private and public key paths must differ.')
            if args.private_key.exists() or args.public_key.exists():raise ValueError('Key generation will not overwrite existing files.')
            private,public=generate_keys()
            args.private_key.parent.mkdir(parents=True,exist_ok=True)
            import os
            descriptor=os.open(args.private_key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'wb') as output:output.write(private)
            args.public_key.parent.mkdir(parents=True,exist_ok=True)
            with args.public_key.open('xb') as output:output.write(public)
            out={'public_key':str(args.public_key),'private_key':str(args.private_key),'notice':'Protect the unencrypted private PEM. Exchange and trust the public key through a separate channel.'}
        elif args.command=='sign':
            from .signing import sign_payload
            out=sign_payload(args.artifact.read_bytes(),args.private_key.read_bytes())
            write(args.output,json.dumps(out,indent=2).encode());out={'output':str(args.output),'artifact_sha256':out['artifact_sha256']}
        elif args.command=='verify-signature':
            from .signing import verify_signature
            out=verify_signature(args.artifact.read_bytes(),json.loads(args.signature.read_text(encoding='utf-8')),args.trusted_key.read_bytes())
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
