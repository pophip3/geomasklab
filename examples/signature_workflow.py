"""Exercise detached signatures with temporary demonstration keys.

These keys represent a local test, not a publisher's production identity.
"""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from geomasklab.signing import generate_keys,sign_payload,verify_signature


def main():
    payload=b'GeoMaskLab exact-byte signature demonstration'
    private,public=generate_keys();signed=sign_payload(payload,private)
    assert verify_signature(payload,signed,public)['verified']
    attacker_private,attacker_public=generate_keys()
    altered=b'Consistent replacement from a different signer'
    try:verify_signature(altered,sign_payload(altered,attacker_private),public)
    except ValueError:replacement_rejected=True
    else:raise ValueError('A replacement under an untrusted key was accepted.')
    # Ephemeral local keys are never published as a trust anchor or retained.
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder)/'signature.json').write_text(json.dumps(signed),encoding='utf-8')
    print(json.dumps({'trusted_signature_verified':True,'untrusted_replacement_rejected':replacement_rejected,
                      'keys_retained':False,'production_identity_claimed':False},indent=2))


if __name__=='__main__':main()
