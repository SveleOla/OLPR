#!/bin/bash
set -e

echo "======================================"
echo "  OLPR - Installasjon"
echo "======================================"

# Sjekk at vi kjører som root
if [ "$EUID" -ne 0 ]; then
  echo "Kjør som root: sudo bash install.sh"
  exit 1
fi

INSTALL_DIR="/opt/olpr"

# 1. Systemoppdatering og avhengigheter
echo "[1/6] Installerer avhengigheter..."
apt-get update -qq
apt-get install -y -qq \
  git curl wget python3 python3-pip \
  docker.io docker-compose-plugin \
  mosquitto-clients ffmpeg

# 2. Aktiver og start Docker
echo "[2/6] Starter Docker..."
systemctl enable docker
systemctl start docker

# 3. Klon repo
echo "[3/6] Kloner OLPR..."
if [ -d "$INSTALL_DIR" ]; then
  echo "  $INSTALL_DIR eksisterer allerede, oppdaterer..."
  cd "$INSTALL_DIR" && git pull
else
  git clone https://github.com/SveleOla/OLPR.git "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# 4. Python-avhengigheter
echo "[4/6] Installerer Python-pakker..."
pip3 install paho-mqtt requests --break-system-packages -q

# 5. Opprett mapper og konfig
echo "[5/6] Setter opp konfig..."
mkdir -p "$INSTALL_DIR/frigate/storage"
mkdir -p "$INSTALL_DIR/homebridge"
mkdir -p "$INSTALL_DIR/portainer/data"
mkdir -p "$INSTALL_DIR/lpr_ukjente/snapshots"

if [ ! -f "$INSTALL_DIR/config/settings.json" ]; then
  cp "$INSTALL_DIR/config/settings.example.json" "$INSTALL_DIR/config/settings.json"
  echo "  Husk å fylle inn config/settings.json!"
fi

if [ ! -f "$INSTALL_DIR/config/kjente_skilt.json" ]; then
  cp "$INSTALL_DIR/config/kjente_skilt.example.json" "$INSTALL_DIR/config/kjente_skilt.json"
fi

if [ ! -f "$INSTALL_DIR/core/frigate/config.yml" ]; then
  cp "$INSTALL_DIR/core/frigate/config.example.yml" "$INSTALL_DIR/core/frigate/config.yml"
  echo "  Husk å konfigurere core/frigate/config.yml!"
fi

# 6. Installer systemd-tjenester
echo "[6/6] Installerer systemd-tjenester..."
for svc in lpr-bridge lpr-web; do
  sed "s|/opt/homeserver|$INSTALL_DIR/core|g" \
    "$INSTALL_DIR/systemd/$svc.service" \
    > "/etc/systemd/system/$svc.service"
done

systemctl daemon-reload
systemctl enable lpr-bridge lpr-web
systemctl start lpr-bridge lpr-web

echo ""
echo "======================================"
echo "  OLPR installert!"
echo "  Dashboard: http://$(hostname -I | awk '{print $1}'):8080"
echo "  Husk å konfigurere:"
echo "  - config/settings.json"
echo "  - core/frigate/config.yml"
echo "======================================"
