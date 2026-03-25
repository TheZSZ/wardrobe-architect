#!/bin/bash
# Generate self-signed SSL certificates for development/testing
# For production, use Let's Encrypt or your own CA-signed certificates

set -euo pipefail

CERT_DIR="nginx/certs"
DOMAIN="${1:-localhost}"

mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/fullchain.pem" ] && [ -f "$CERT_DIR/privkey.pem" ]; then
    echo "Certificates already exist in $CERT_DIR/"
    echo "To regenerate, remove them first:"
    echo "  rm $CERT_DIR/*.pem"
    exit 0
fi

echo "Generating self-signed certificate for: $DOMAIN"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=$DOMAIN" \
    -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:127.0.0.1"

chmod 644 "$CERT_DIR/fullchain.pem"
chmod 600 "$CERT_DIR/privkey.pem"

echo ""
echo "✓ Certificates generated in $CERT_DIR/"
echo "  - fullchain.pem (certificate)"
echo "  - privkey.pem (private key)"
echo ""
echo "To enable SSL:"
echo "  1. Update docker-compose.yml nginx volume:"
echo "     - ./nginx/nginx-ssl.conf:/etc/nginx/nginx.conf:ro"
echo "  2. Restart: docker compose restart nginx"
echo ""
echo "Note: Self-signed certs will show browser warnings."
echo "For production, use Let's Encrypt or CA-signed certificates."
