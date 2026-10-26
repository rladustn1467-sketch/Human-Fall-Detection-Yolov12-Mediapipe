"""Local HTTPS for development and tests only: a private development CA and a server certificate for localhost.

Real deployments use a public certificate (Let's Encrypt through the reverse proxy, see deploy/https/README.md);
this is only so the server, the PC detector and the Android debug build can be tested over HTTPS on this computer
without turning certificate checks off anywhere. Nothing trusts this CA unless it is given explicitly
(SSL_CERT_FILE for Python, the Android *debug* build's network security config for localhost).

Files are written OUTSIDE the project (never committed):
  %LOCALAPPDATA%\\FallDetection\\dev-tls\\ca.pem        development CA certificate (public, may be trusted in tests)
  %LOCALAPPDATA%\\FallDetection\\dev-tls\\ca.key        its private key (only used to sign the server certificate)
  %LOCALAPPDATA%\\FallDetection\\dev-tls\\server.pem    server certificate for localhost / 127.0.0.1
  %LOCALAPPDATA%\\FallDetection\\dev-tls\\server.key    server private key (given to uvicorn --ssl-keyfile)
Private keys are never printed.

Run with the server venv (needs cryptography):
  server\\venv\\Scripts\\python.exe tools\\dev_tls.py            create (keeps existing files)
  server\\venv\\Scripts\\python.exe tools\\dev_tls.py --renew    create new files
"""
import datetime
import ipaddress
import os
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

DEFAULT_HOSTS = ("localhost", "127.0.0.1")


def default_dir():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "FallDetection" / "dev-tls"


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Fall Detection (development only)"),
                      x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def make_ca(cn="Fall Detection Dev CA", days=825):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(_name(cn)).issuer_name(_name(cn))
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=days))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                         crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    return key, cert


def make_server_cert(ca_key, ca_cert, hosts=DEFAULT_HOSTS, days=397):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    names = []
    for h in hosts:
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            names.append(x509.DNSName(h))
    cert = (x509.CertificateBuilder()
            .subject_name(_name(hosts[0])).issuer_name(ca_cert.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return key, cert


def _pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def _pem_cert(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def write(out_dir, hosts=DEFAULT_HOSTS, renew=False):
    """Create the dev CA and server certificate in out_dir (kept if they exist). Returns the paths."""
    out = Path(out_dir)
    paths = {k: out / f for k, f in (("ca", "ca.pem"), ("ca_key", "ca.key"), ("cert", "server.pem"), ("key", "server.key"))}
    if not renew and all(p.exists() for p in paths.values()):
        return paths
    out.mkdir(parents=True, exist_ok=True)
    ca_key, ca = make_ca()
    key, cert = make_server_cert(ca_key, ca, hosts)
    paths["ca"].write_bytes(_pem_cert(ca))
    paths["ca_key"].write_bytes(_pem_key(ca_key))
    paths["cert"].write_bytes(_pem_cert(cert))
    paths["key"].write_bytes(_pem_key(key))
    return paths


def fingerprint(pem_path):
    cert = x509.load_pem_x509_certificate(Path(pem_path).read_bytes())
    return cert.fingerprint(hashes.SHA256()).hex(":")[:23] + "…"


if __name__ == "__main__":
    p = write(default_dir(), renew="--renew" in sys.argv)
    print("개발용 HTTPS 파일 (프로젝트 밖, 개발·시험 전용):")
    for k in ("ca", "cert", "key"):
        print(f"  {k:5}: {p[k]}")
    print(f"  CA 지문(SHA-256 앞부분): {fingerprint(p['ca'])}")
    print("  개인 키 내용은 출력하지 않아요.")
