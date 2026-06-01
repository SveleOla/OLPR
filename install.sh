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
echo "[1/7] Installerer avhengigheter..."
apt-get update -qq
apt-get install -y -qq \
  git curl wget python3 python3-pip \
  ca-certificates gnupg lsb-release \
  mosquitto-clients ffmpeg

# 2. Docker fra offisiell repo
echo "[2/7] Installerer Docker..."
if ! command -v docker &> /dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
systemctl enable docker
systemctl start docker

# 3. Python-avhengigheter
echo "[3/7] Installerer Python-pakker..."
pip3 install paho-mqtt requests --break-system-packages -q

# 4. Klon repo
echo "[4/7] Kloner OLPR..."
if [ -d "$INSTALL_DIR" ]; then
  echo "  $INSTALL_DIR eksisterer allerede, oppdaterer..."
  cd "$INSTALL_DIR" && git pull
else
  git clone https://github.com/SveleOla/OLPR.git "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# 5. Opprett mapper og konfig
echo "[5/7] Setter opp konfig..."
mkdir -p "$INSTALL_DIR/frigate/storage"
mkdir -p "$INSTALL_DIR/homebridge"
mkdir -p "$INSTALL_DIR/portainer/data"
mkdir -p "$INSTALL_DIR/data/snapshots"

if [ ! -f "$INSTALL_DIR/config/settings.json" ]; then
  cp "$INSTALL_DIR/config/settings.example.json" "$INSTALL_DIR/config/settings.json"
fi

if [ ! -f "$INSTALL_DIR/config/kjente_skilt.json" ]; then
  cp "$INSTALL_DIR/config/kjente_skilt.example.json" "$INSTALL_DIR/config/kjente_skilt.json"
fi

if [ ! -f "$INSTALL_DIR/core/frigate/config.yml" ]; then
  cp "$INSTALL_DIR/core/frigate/config.example.yml" "$INSTALL_DIR/core/frigate/config.yml"
fi

# 6. Start Docker-tjenester (ikke Frigate)
echo "[6/7] Starter Docker-tjenester..."
cd "$INSTALL_DIR"
docker compose up -d

# Vent på Mosquitto
echo "  Venter på Mosquitto..."
sleep 5

# 7. Installer og start systemd-tjenester
echo "[7/7] Installerer systemd-tjenester..."
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
echo ""
echo "  Dashboard: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "  Neste steg:"
echo "  1. Konfigurer kameraer: $INSTALL_DIR/core/frigate/config.yml"
echo "  2. Start Frigate: cd $INSTALL_DIR && docker compose up -d frigate"
echo "======================================"
