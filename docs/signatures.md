# Detached signatures and external trust

SHA-256 and numerical replay detect inconsistency. An optional Ed25519 signature
also detects replacement of signed artifact bytes when the recipient already
trusts the signer's public key. Key ownership, human identity and authorization
to trust it remain separate decisions.

```sh
python -m pip install ".[signing]"
geomasklab keygen --private-key local.private.pem --public-key public.pem
geomasklab sign evidence.zip --private-key local.private.pem --output evidence.signature.json
geomasklab verify-signature evidence.zip evidence.signature.json --trusted-key trusted-public.pem
geomasklab verify evidence.zip
```

For a zonal or geospatial packet, sign its exact ZIP bytes and run the corresponding
numerical verifier after signature verification. Signing is an exact-byte operation;
it does not itself inspect or certify the artifact's scientific contents.

## Trust procedure

1. The producer protects the unencrypted private PEM locally. Key generation
   refuses to overwrite existing paths and requests owner-only POSIX permissions.
   Windows uses the destination folder's access controls. Never commit private keys.
2. The recipient obtains the public PEM and its fingerprint through an independently
   trusted channel. A key delivered only inside an untrusted artifact is insufficient.
3. `verify-signature` requires that separately supplied key. A different attacker key
   fails even when the attacker rebuilds a completely self-consistent evidence packet.
4. Verify numerical replay separately. A valid signature does not turn a mislabeled
   mask, false coordinate assertion or an inappropriate area model into valid science.

The signature covers a canonical, domain-separated document containing schema,
software version, algorithm, exact artifact SHA-256, byte length and public-key
fingerprint. The detached JSON cannot authorize its own public key. The fingerprint
is SHA-256 of the raw Ed25519 public key. There is no signing-time, revocation service,
institutional identity certificate or automatic trust-on-first-use mechanism.

For an external hash register, retain the same versioned artifact SHA-256 in a
separately trusted repository release, institutional record or archival deposit.
The [release metadata procedure](../release/README.md) describes archival preparation.
A local manifest alone is not an external register; no registration or DOI is claimed
until an actual externally visible record exists.

Implementation reference: [Cryptography Ed25519 API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
