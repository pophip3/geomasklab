"""Optional JSON Schema validation, with packaged references and no network fetch."""
from importlib.resources import files
import json


def validate_metadata(bundle_files, manifest):
    """Validate shapes separately from mandatory deterministic pixel checks."""
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError as error:
        raise ValueError('Install the optional schema extra: pip install ".[schema]" or your-wheel.whl[schema].') from error
    schemas={name:json.loads(files('geomasklab').joinpath('schemas',name+'-1.0.schema.json').read_text(encoding='utf-8'))
             for name in ('manifest','result','statistics')}
    registry=Registry().with_resources([(schema['$id'],Resource.from_contents(schema)) for schema in schemas.values()])
    objects={'manifest':manifest,'result':json.loads(bundle_files['result.json']),
             'statistics':json.loads(bundle_files['statistics.json'])}
    for name,schema in schemas.items():
        validator=Draft202012Validator(schema,registry=registry)
        error=next(validator.iter_errors(objects[name]),None)
        if error is not None:
            path='/'.join(str(p) for p in error.absolute_path)
            raise ValueError(f'{name} schema validation failed at {path or "root"}: {error.message}')
