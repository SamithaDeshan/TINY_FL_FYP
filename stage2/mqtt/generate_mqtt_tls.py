"""Generate a local MQTT CA, broker certificate, ESP32 CA header, and TLS config."""
import argparse
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "stage2" / "mqtt" / "certs" / "local"
NODE_HEADER = ROOT / "stage2" / "arduino" / "tinyfl_node" / "mqtt_ca.h"


def generate(host: str, force: bool) -> None:
    output_files = [
        OUTPUT / "ca.key",
        OUTPUT / "ca.crt",
        OUTPUT / "broker.key",
        OUTPUT / "broker.crt",
        OUTPUT / "mosquitto_tls.conf",
        NODE_HEADER,
    ]
    if not force and any(path.exists() for path in output_files):
        raise SystemExit("TLS material exists; use --force to replace it (this rotates the CA).")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    NODE_HEADER.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TinyFL Local MQTT CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1825))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    broker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    try:
        address = ipaddress.ip_address(host)
        san = x509.SubjectAlternativeName([x509.IPAddress(address)])
    except ValueError:
        san = x509.SubjectAlternativeName([x509.DNSName(host)])
    broker_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    broker_cert = (
        x509.CertificateBuilder()
        .subject_name(broker_name)
        .issuer_name(ca_cert.subject)
        .public_key(broker_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    ca_key_pem = ca_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    broker_key_pem = broker_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
    broker_pem = broker_cert.public_bytes(serialization.Encoding.PEM)
    (OUTPUT / "ca.key").write_bytes(ca_key_pem)
    (OUTPUT / "ca.crt").write_bytes(ca_pem)
    (OUTPUT / "broker.key").write_bytes(broker_key_pem)
    (OUTPUT / "broker.crt").write_bytes(broker_pem)

    cert_literal = ca_pem.decode("ascii").rstrip()
    NODE_HEADER.write_text(
        "#pragma once\n"
        "static const char MQTT_CA_CERT[] PROGMEM = R\"MQTTCA(\n"
        f"{cert_literal}\n"
        ")MQTTCA\";\n",
        encoding="ascii",
    )
    conf = (
        "# Local TinyFL TLS listener. The existing port 1883 listener is unchanged.\n"
        "listener 8883 0.0.0.0\n"
        "allow_anonymous true\n"
        "tls_version tlsv1.2\n"
        f'certfile {(OUTPUT / "broker.crt").as_posix()}\n'
        f'keyfile {(OUTPUT / "broker.key").as_posix()}\n'
    )
    (OUTPUT / "mosquitto_tls.conf").write_text(conf, encoding="ascii")
    print(f"CA certificate: {OUTPUT / 'ca.crt'}")
    print(f"Broker certificate/key: {OUTPUT / 'broker.crt'} / {OUTPUT / 'broker.key'}")
    print(f"ESP32 trust header: {NODE_HEADER}")
    print(f"TLS broker config: {OUTPUT / 'mosquitto_tls.conf'}")
    print("Listener: 0.0.0.0:8883; broker certificate SAN matches", host)
    print("Private keys are in the ignored local certificate directory; do not share them.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="172.20.10.7", help="IP or DNS name nodes use to reach Mosquitto")
    parser.add_argument("--force", action="store_true", help="replace existing local CA and certificates")
    args = parser.parse_args()
    generate(args.host, args.force)


if __name__ == "__main__":
    main()