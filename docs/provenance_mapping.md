# PROV-JSON evidence mapping

```sh
geomasklab provenance evidence.zip --output provenance.json
geomasklab verify-provenance evidence.zip provenance.json
```

Export requires successful core replay. The document maps exact file hashes,
the explicit domain and both available pixel denominators to entities; recorded
measurement and current export to separate activities; and GeoMaskLab to a
software agent. `used`, `wasGeneratedBy` and `wasDerivedFrom` describe their
relationships. The complete source ZIP has its own SHA-256 identity.

Caller-supplied source, model/alignment assertions and original prediction
metadata form a separate unauthenticated entity. An immediate derived-parent
identity is recorded as **not embedded**. Missing historical activities and
ancestor packages are not fabricated. A timestamp is retained as `gml:recordedAt`
without claiming an authenticated event time.

This uses the [PROV-JSON Member Submission serialization](https://www.w3.org/submissions/prov-json/)
of the PROV data model. PROV-JSON's document status is distinct from the W3C PROV
Recommendations; no W3C certification is claimed. GeoMaskLab's extension namespace
is `urn:geomasklab:provenance:`. Hash/file, domain and assertion properties use
that namespace while relation types use `http://www.w3.org/ns/prov#`.

The export has been checked against the specification's provided Draft 4 Schema
and independently parsed/round-tripped using the `prov` Python library. The
parser is an optional interoperability test dependency (`.[interop]`), not a core
runtime requirement. `verify-provenance` independently rebuilds the expected
mapping from the source bundle and rejects any difference.

Share both the evidence ZIP and this JSON file. The JSON supplies interoperable
metadata; the ZIP retains the bytes necessary for deterministic pixel replay.
PROV serialization alone neither verifies a segmentation model nor authenticates
an author. A full RO-Crate profile and signatures are deferred.
