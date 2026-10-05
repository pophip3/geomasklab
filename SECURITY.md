# Local deployment and reporting

GeoMaskLab binds to `127.0.0.1` by default and is intended for trusted local
research use. It provides no multi-user authentication, Internet-facing access
control or production service-hardening guarantee. Do not expose this research
server publicly as a shared hosted application without a separately reviewed
deployment design.

Live mode sends images to configured external services; `.env` credentials stay
on the Python server and must not be published. A checksum manifest checks
consistency, not author identity. Self-reported review labels are not authenticated
identities. Evidence can contain uploaded images and user-entered text; inspect
it before sharing.

ZIP entries are verified without extraction. Upload size, pixel count, binary
mask values and dimensions are checked, but untrusted image-processing libraries
must still be maintained. Use supported interpreter/dependency versions and
review their upstream security updates.

For non-sensitive problems use the repository issue tracker. Do not post
credentials, private images or exploit details in a public issue. If available,
use the repository's private vulnerability-reporting channel for sensitive
reports. No private disclosure email or reporting feature is claimed until the
maintainers have configured it.
