# OLPR — Open LPR

Automatisk skiltgjenkjenning for smarthus og næringsbygg.

## Funksjonalitet

- Automatisk skiltgjenkjenning via Frigate NVR og Google Coral TPU
- GPT-4o fallback for vanskelige skilt
- Web-dashboard med logg, galleri og statistikk
- MQTT-publisering til valgfritt smarthussystem
- HomeKit-integrasjon via Homebridge

## Krav

- Debian 12/13 (headless)
- Intel CPU med VAAPI (12th gen eller nyere anbefalt)
- Google Coral USB eller M.2 TPU
- Minimum 8GB RAM
- Minimum 64GB SSD

## Installasjon

```bash
curl -s https://raw.githubusercontent.com/SveleOla/OLPR/main/install.sh | bash
```

## Konfigurasjon

Etter installasjon, rediger disse filene:

- `/opt/olpr/config/settings.json` — systeminnstillinger
- `/opt/olpr/core/frigate/config.yml` — kameraoppsett
- `/opt/olpr/config/kjente_skilt.json` — kjente kjøretøy

## Dashboard

Tilgjengelig på `http://<server-ip>:8080`

## MQTT Topics

Standard topics (konfigurerbart i settings.json):

| Topic | Verdi | Beskrivelse |
|-------|-------|-------------|
| `lpr/{camera}/resultat` | Navn / ukjent | Navn på kjent bil |
| `lpr/{camera}/skilt` | AB12345 | Skiltnummer |
