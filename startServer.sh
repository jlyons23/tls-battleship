#!/usr/bin/env bash
# Usage: ./startServer.sh [port]

# Check for cert and key and generate if they’re missing
CERT_FILE="server.crt"
KEY_FILE="server.key"
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
  echo "TLS cert or key missing, generating self-signed cert/key..."
  ./generate_cert.py
  if [ $? -ne 0 ]; then
    echo "Error: certificate generation failed." >&2
    exit 1
  fi
fi

./secure_server.py "$@"