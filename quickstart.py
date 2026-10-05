"""Start the local workbench with bundled procedural assets; no model installation."""
import argparse
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer


def main():
    parser=argparse.ArgumentParser(description='Start GeoMaskLab locally; synthetic demo is the default for a new browser.')
    parser.add_argument('--port',type=int,default=4180)
    args=parser.parse_args()
    if not 1<=args.port<=65535: parser.error('port must be between 1 and 65535')
    try:
        from fixtures import write_assets
        import server
    except ModuleNotFoundError as exc:
        if exc.name=='PIL': parser.exit(1,'Pillow is required. Run: python -m pip install -r requirements.txt\n')
        raise
    assets=Path(__file__).parent/'web/assets'
    if not all((assets/name).is_file() for name in ('urban.png','airport.jpg')): write_assets(assets)
    try: httpd=ThreadingHTTPServer(('127.0.0.1',args.port),server.Handler)
    except OSError as exc: parser.exit(1,f'Cannot open local port {args.port}: {exc}. Try --port 4182\n')
    print(f'GeoMaskLab: http://127.0.0.1:{args.port}\nOpen this URL in your browser. Ctrl+C stops the server.',flush=True)
    print('Synthetic examples require no GPU, model weights, accounts or inference service.',flush=True)
    try: httpd.serve_forever()
    except KeyboardInterrupt: print('\nGeoMaskLab stopped.',flush=True)
    finally: httpd.server_close()


if __name__=='__main__': main()
