"""Optional detached Ed25519 signatures with caller-supplied trusted public keys.

Signature validity binds exact bytes to possession of a private key. Human
identity and permission to trust that key require an external trust decision.
An embedded or attacker-supplied key is never accepted as its own trust anchor.
"""
import base64
import hashlib
import json
from ._version import VERSION

SCHEMA='geomasklab-detached-signature/1.0'
DOMAIN=b'GeoMaskLab detached evidence signature v1\x00'


def dependencies():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as error:
        raise ValueError('Signing requires the optional signing extra: pip install ".[signing]".') from error
    return serialization,Ed25519PrivateKey,Ed25519PublicKey,InvalidSignature


def generate_keys():
    """Return unencrypted private/public PEM bytes; the caller must protect the private file."""
    serialization,private_type,_,_=dependencies();private=private_type.generate()
    return (private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),
            private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))


def _public_identity(key,serialization):
    return hashlib.sha256(key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).hexdigest()


def _message(record):
    return DOMAIN+json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def sign_payload(payload,private_pem):
    """Sign exact artifact bytes; this does not validate its scientific contents."""
    serialization,private_type,_,_=dependencies()
    try:key=serialization.load_pem_private_key(private_pem,password=None)
    except (ValueError,TypeError) as error:raise ValueError('Use an unencrypted Ed25519 private PEM key.') from error
    if not isinstance(key,private_type):raise ValueError('The private key must be Ed25519.')
    record={'schema':SCHEMA,'software_version':VERSION,'algorithm':'Ed25519','artifact_sha256':hashlib.sha256(payload).hexdigest(),
            'artifact_bytes':len(payload),'public_key_sha256':_public_identity(key.public_key(),serialization)}
    return {**record,'signature_base64':base64.b64encode(key.sign(_message(record))).decode('ascii')}


def verify_signature(payload,document,trusted_public_pem):
    """Require a separately trusted key; reject self-consistent replacement payloads."""
    serialization,_,public_type,invalid=dependencies()
    required={'schema','software_version','algorithm','artifact_sha256','artifact_bytes','public_key_sha256','signature_base64'}
    if not isinstance(document,dict) or set(document)!=required or document.get('schema')!=SCHEMA or document.get('algorithm')!='Ed25519':
        raise ValueError('Unsupported detached signature document.')
    if (type(document['artifact_bytes']) is not int or document['artifact_bytes']!=len(payload) or
            document['artifact_sha256']!=hashlib.sha256(payload).hexdigest() or not isinstance(document['software_version'],str)):
        raise ValueError('Signed artifact identity does not match these bytes.')
    try:key=serialization.load_pem_public_key(trusted_public_pem)
    except (ValueError,TypeError) as error:raise ValueError('Use a separately trusted Ed25519 public PEM key.') from error
    if not isinstance(key,public_type):raise ValueError('The trusted public key must be Ed25519.')
    if document['public_key_sha256']!=_public_identity(key,serialization):
        raise ValueError('Signer key does not match the separately trusted public key.')
    record={k:v for k,v in document.items() if k!='signature_base64'}
    try:
        signature=base64.b64decode(document['signature_base64'],validate=True)
        key.verify(signature,_message(record))
    except (invalid,ValueError,TypeError) as error:raise ValueError('Detached signature verification failed.') from error
    return {'verified':True,'artifact_sha256':document['artifact_sha256'],'trusted_public_key_sha256':document['public_key_sha256'],
            'scope':'Exact-byte signature under the supplied trusted key; human identity and scientific accuracy are external assertions.'}
