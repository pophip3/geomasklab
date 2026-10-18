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

Report non-sensitive problems through the repository issue tracker. For a
sensitive report, contact the maintainer using the contact details in the README
to arrange an appropriate exchange. Keep credentials, private images and exploit
details out of public issues.
