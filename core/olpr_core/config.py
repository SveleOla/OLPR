"""OLPR-kjernen — paths, innstillinger og fil-I/O.

Eneste sted som kjenner til miljøvariabler og filstier. Andre moduler importerer
herfra i stedet for å hardkode paths — gjør kjernen flyttbar (homeserver kan
sette egne stier via OLPR_*-miljøvariabler i steg 4).
"""
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('olpr')

# ── Paths (overstyres via miljøvariabler) ─────────────────────────────────────
BASE_DIR          = os.environ.get("OLPR_BASE",   "/opt/olpr/core")
CONFIG_DIR        = os.environ.get("OLPR_CONFIG", "/opt/olpr/config")
DATA_DIR          = os.environ.get("OLPR_DATA",   "/opt/olpr/data")
SKILT_FILE        = f"{CONFIG_DIR}/kjente_skilt.json"
STATIC_DIR        = f"{BASE_DIR}/static"
TEMPLATE          = f"{BASE_DIR}/templates/index.html"
LOGIN_TEMPLATE    = os.path.join(BASE_DIR, 'templates', 'login.html')
SETTINGS_FILE     = f"{CONFIG_DIR}/settings.json"
UKJENTE_DB        = f"{DATA_DIR}/ukjente.db"
UKJENTE_SNAPSHOTS = f"{DATA_DIR}/snapshots"
LOGG_DB           = f"{DATA_DIR}/logg.db"
MAX_LINES         = 2000

SETTINGS_DEFAULTS = {
    "lpr":    {"confidence_threshold": 0.8, "gpt_enabled": False, "wait_seconds": 30,
               "reset_seconds": 5, "commit_window": 1.5,
               "snapshot_retention_days": 30},
    "web":    {"max_log_lines": 2000, "stats_refresh_sec": 15},
    "system": {"name": "OLPR", "frigate_url": "http://localhost:5000",
               "portainer_url": "http://localhost:9000"},
    "mqtt":   {"result_topic": "lpr/{camera}/resultat",
               "plate_topic":  "lpr/{camera}/skilt"},
    "auth":   {"username": "admin"},
}


# ── Innstillinger ─────────────────────────────────────────────────────────────

def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        result = {k: dict(v) for k, v in SETTINGS_DEFAULTS.items()}
        for section, values in saved.items():
            if section in result and isinstance(values, dict):
                for k, v in values.items():
                    if v is not None:
                        result[section][k] = v
        return result
    except Exception:
        return {k: dict(v) for k, v in SETTINGS_DEFAULTS.items()}


def save_settings_file(data):
    def filter_none(obj):
        if isinstance(obj, dict):
            return {k: filter_none(v) for k, v in obj.items() if v is not None}
        return obj
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(filter_none(data), f, indent=2)


# ── Kjente skilt ──────────────────────────────────────────────────────────────

def load_skilt():
    try:
        with open(SKILT_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_skilt(data):
    with open(SKILT_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Templates ─────────────────────────────────────────────────────────────────

def load_template(replacements):
    with open(TEMPLATE, encoding='utf-8') as f:
        tpl = f.read()
    for key, val in replacements.items():
        tpl = tpl.replace(key, val)
    return tpl
