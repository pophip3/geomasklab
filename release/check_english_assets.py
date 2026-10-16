"""Recursively check delivery paths and text for CJK ideographs."""
import argparse
import io
import json
from pathlib import Path
import re
import zipfile

HAN = re.compile('[\u3400-\u9fff\uf900-\ufaff]')
TEXT = {'.txt', '.md', '.json', '.csv', '.py', '.js', '.html', '.css', '.yml',
        '.yaml', '.tex', '.xml', '.cff', '.rst', '.log', '.toml'}
ARCHIVES = {'.zip', '.whl', '.docx'}


def inspect_bytes(data, name, findings, counts):
    counts['files'] += 1
    if HAN.search(name):
        findings.append({'path': name, 'issue': 'CJK path'})
    suffix = Path(name).suffix.lower()
    if suffix in ARCHIVES:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            counts['archives'] += 1
            for member in archive.infolist():
                if not member.is_dir():
                    inspect_bytes(archive.read(member), name + '!' + member.filename, findings, counts)
    elif suffix in TEXT:
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            return
        if HAN.search(text):
            findings.append({'path': name, 'issue': 'CJK text'})
    elif suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        if HAN.search(text):
            findings.append({'path': name, 'issue': 'CJK PDF text'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    findings, counts = [], {'files': 0, 'archives': 0}
    if args.artifact.is_dir():
        for path in args.artifact.rglob('*'):
            if path.is_file():
                inspect_bytes(path.read_bytes(), path.relative_to(args.artifact).as_posix(), findings, counts)
    else:
        inspect_bytes(args.artifact.read_bytes(), args.artifact.name, findings, counts)
    result = {'passed': not findings, **counts, 'findings': findings}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    if findings:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
