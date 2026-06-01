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
python3 -c "
import json
with open('$CONFIG') as f:
    s = json.load(f)
s['auth'] = {'username': 'admin', 'password': 'olpr'}
with open('$CONFIG', 'w') as f:
    json.dump(s, f, indent=2)
print('Passord tilbakestilt til admin/olpr')
"
