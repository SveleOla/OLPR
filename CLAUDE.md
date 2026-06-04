# OLPR - Kontekst for Claude

## Hva er OLPR?
OLPR (Ola LPR) er et kommersielt produkt for automatisk skiltgjenkjenning.
Målgruppe: parkeringsplasser, bommer, skogsveger og lignende.
Bygget på Frigate NVR med Google Coral TPU støtte.

## Installasjon
Ren Debian 13, kjør:
wget -qO- https://raw.githubusercontent.com/SveleOla/OLPR/main/install.sh | bash

## Filstruktur på server
/opt/olpr/
  core/           - Python-scripts, static JS/CSS, templates, frigate config
  config/         - settings.json, kjente_skilt.json (kundespesifikk, ikke i git)
  data/           - SQLite-databaser, snapshots
  frigate/        - Frigate opptak og storage
  systemd/        - systemd service-filer

## Komponenter
- lpr_bridge.py   - Frigate LPR events -> MQTT publisering
- lpr_web.py      - Dashboard webserver port 8080
- Frigate         - NVR i Docker, kamera-strømmer og LPR
- Mosquitto       - MQTT-broker i Docker
- Portainer       - Docker-administrasjon i Docker

## Paths (env-vars)
- OLPR_BASE=/opt/olpr/core
- OLPR_CONFIG=/opt/olpr/config
- OLPR_DATA=/opt/olpr/data

## MQTT
Topics bruker systemnavn som prefiks: {system}/{camera}/resultat og {system}/{camera}/skilt
Systemnavn settes i Innstillinger -> System -> System-navn

## Databaser
- data/logg.db    - alle LPR-deteksjoner (tidspunkt, plate, camera)
- data/ukjente.db - ukjente kjøretøy med snapshots og GPT-kilde

## Frigate config
Genereres automatisk fra kamera-innstillinger i dashboard.
Detektor og hwaccel konfigurerbart fra Innstillinger -> Frigate.

## Autentisering
Brukernavn/passord i settings.json under "auth".
Reset: olpr-reset-password (kjores i terminal pa serveren)

## Kjente issues
- H.265 substream krever Intel 6th gen+ for VAAPI-dekoding
- Haswell (4th gen) stoetter ikke HEVC via VAAPI - bruk main stream
- network_mode: host pa alle Docker-containere
- EOF-heredocs feiler med triple quotes - bruk PYEOF
- Bash tolker ! i double quotes - bruk single quotes eller Python

## Git
Repo: https://github.com/SveleOla/OLPR (privat)
Workflow: git add . -> git commit -m "beskrivelse" -> git push

## Testserver
olpr-test2: 192.168.1.39
