#!/bin/bash
echo "OLPR - Tilbakestill passord"
echo "=========================="
echo "Dette vil sette brukernavn og passord tilbake til admin/olpr"
read -p "Er du sikker? (ja/nei): " confirm
if [ "$confirm" != "ja" ]; then
  echo "Avbrutt."
  exit 0
fi

CONFIG="/opt/olpr/config/settings.json"
python3 - "$CONFIG" << 'EOF'
import hashlib
import json
import secrets
import sys

config = sys.argv[1]
salt = secrets.token_hex(16)
dk = hashlib.pbkdf2_hmac('sha256', b'olpr', bytes.fromhex(salt), 200_000)
with open(config) as f:
    s = json.load(f)
s['auth'] = {'username': 'admin', 'password_hash': f"{salt}${dk.hex()}"}
with open(config, 'w') as f:
    json.dump(s, f, indent=2)
print('Passord tilbakestilt til admin/olpr')
EOF
