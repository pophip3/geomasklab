"""Bound request reads, including draining unsupported chunked bodies safely."""


def read_json_body(handler, maximum):
    handler.connection.settimeout(30)
    transfer = handler.headers.get('Transfer-Encoding')
    if transfer:
        if transfer.strip().lower() != 'chunked':
            raise ValueError('Unsupported Transfer-Encoding; use Content-Length.')
        # Finish a size-bounded chunked upload before rejecting it. An immediate
        # close can interrupt the client's upload and hide our HTTP error.
        remaining = maximum
        while True:
            line = handler.rfile.readline(128)
            if not line.endswith(b'\r\n') or len(line) >= 128:
                raise ValueError('Invalid chunk header.')
            try:
                token = line[:-2].split(b';', 1)[0]
                if not token or any(char not in b'0123456789abcdefABCDEF' for char in token):
                    raise ValueError
                size = int(token, 16)
            except ValueError:
                raise ValueError('Invalid chunk size.') from None
            if size > remaining:
                raise ValueError('Unsupported request size.')
            if size == 0:
                trailer_budget = 8192
                while trailer_budget > 0:
                    trailer = handler.rfile.readline(min(trailer_budget + 1, 1024))
                    trailer_budget -= len(trailer)
                    if trailer == b'\r\n':
                        raise ValueError('Chunked requests are unsupported; use Content-Length.')
                    if not trailer or not trailer.endswith(b'\r\n'):
                        break
                raise ValueError('Invalid chunk trailer.')
            chunk = handler.rfile.read(size + 2)
            if len(chunk) != size + 2 or not chunk.endswith(b'\r\n'):
                raise ValueError('Incomplete chunked request body.')
            remaining -= size
    raw_length = handler.headers.get('Content-Length', '')
    if not raw_length.isascii() or not raw_length.isdigit() or not 0 < int(raw_length) <= maximum:
        raise ValueError('Missing or excessive request Content-Length.')
    raw = handler.rfile.read(int(raw_length))
    if len(raw) != int(raw_length):
        raise ValueError('Incomplete request body.')
    if handler.headers.get_content_type() != 'application/json':
        raise ValueError('Use Content-Type application/json.')
    return raw
