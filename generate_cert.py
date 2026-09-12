#!/usr/bin/env python3
import ipaddress
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.x509 import SubjectAlternativeName, DNSName, IPAddress
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

# Generate a 2048-bit RSA private key
key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)

# Build subject/issuer
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, u"AU"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Battleship Server"),
    x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
])


# Create the cert, valid for one year
cert = (
    x509.CertificateBuilder()
      .subject_name(subject)
      .issuer_name(issuer)
      .public_key(key.public_key())
      .serial_number(x509.random_serial_number())
      .not_valid_before(datetime.utcnow())
      .not_valid_after(datetime.utcnow() + timedelta(days=365))
      .add_extension(
          SubjectAlternativeName([
            DNSName(u"localhost"),
            IPAddress(ipaddress.IPv4Address("127.0.0.1"))
          ]),
          critical=False
      )
      .sign(key, hashes.SHA256(), default_backend())
)

# Write out server.key
with open("server.key", "wb") as f:
    f.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ))

# Write out server.crt
with open("server.crt", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print("Generated server.crt and server.key ")
