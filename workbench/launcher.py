"""Launch the complete installed browser workbench without writing into its package."""
import argparse
import os
from pathlib import Path
from http.server import ThreadingHTTPServer


def main(argv=None):
    parser = argparse.ArgumentParser(description='Start the GeoMaskLab browser workbench locally.')
    parser.add_argument('--port', type=int, default=4180)
    parser.add_argument('--data-dir', type=Path, default=Path.cwd() / 'experiments',
                        help='Writable experiment directory (default: ./experiments).')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    os.environ['GEO_DATA_DIR'] = str(args.data_dir.resolve())
    from workbench import server
    from geomasklab import __version__
    try:
        httpd = ThreadingHTTPServer(('127.0.0.1', args.port), server.Handler)
    except OSError as exc:
        parser.exit(1, f'Cannot open local port {args.port}: {exc}. Try --port 4182\n')
    print(f'GeoMaskLab {__version__}: http://127.0.0.1:{args.port}\n'
          f'Experiments: {server.DATA}\nOpen this URL in your browser. Ctrl+C stops the server.', flush=True)
    print('Offline examples need no model weights or inference service.', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nGeoMaskLab stopped.', flush=True)
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
