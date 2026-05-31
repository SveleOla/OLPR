#!/usr/bin/env python3
"""Frigate LPR -> Loxone bridge med GPT-4o fallback. Multi-kamera støtte."""
import base64
import json
import logging
import os
import re
import signal
import sqlite3
import sys
import threading
from datetime import datetime

import paho.mqtt.client as mqtt
import requests

MQTT_HOST      = "127.0.0.1"
MQTT_PORT      = 1883
WAIT_SECONDS   = 10
RESET_SECONDS  = 5
PLATE_REGEX    = re.compile(r'[A-Z]{2}[0-9]{4,5}')
LOG_FILE       = "/opt/homeserver/lpr_log.txt"
SKILT_FILE     = "/opt/homeserver/kjente_skilt.json"
SNAPSHOT_DIR   = "/opt/homeserver/lpr_ukjente/snapshots"
DB_FILE        = "/opt/homeserver/lpr_ukjente/ukjente.db"
FRIGATE_API    = "http://127.0.0.1:5000"
OPENAI_API_KEY = ""
GPT_MODEL      = "gpt-4o"

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("lpr")


# ── Settings ──────────────────────────────────────────────────────────────────

def _load_settings():
    try:
        with open("/opt/homeserver/settings.json") as f:
            return json.load(f).get('lpr', {})
    except Exception:
        return {}

def _load_settings_full():
    try:
        with open("/opt/homeserver/settings.json") as f:
            return json.load(f)
    except Exception:
        return {}

def load_lpr_cameras():
    try:
        with open("/opt/homeserver/settings.json") as f:
            cameras = json.load(f).get('cameras', [])
        lpr_cams = [c['name'] for c in cameras if c.get('lpr')]
        return lpr_cams if lpr_cams else ['oppkjorsel']
    except Exception:
        return ['oppkjorsel']

_s             = _load_settings()
WAIT_SECONDS   = _s.get('wait_seconds', WAIT_SECONDS)
RESET_SECONDS  = _s.get('reset_seconds', RESET_SECONDS)
COMMIT_WINDOW  = _s.get('commit_window', 1.5)
SNAPSHOT_DELAY = _s.get('snapshot_delay', 1.0)
KONF_TERSKEL   = _s.get('confidence_threshold', 0.8)
GPT_ENABLED    = _s.get('gpt_enabled', True)
PRUNE_DAYS     = _s.get('snapshot_retention_days', 30)
OPENAI_API_KEY = _s.get('openai_api_key', OPENAI_API_KEY)
GPT_MODEL      = _s.get('gpt_model', GPT_MODEL)
MQTT_HOST      = _s.get('mqtt_host', MQTT_HOST)
MQTT_PORT      = int(_s.get('mqtt_port', MQTT_PORT))
LPR_CAMERAS    = load_lpr_cameras()


# ── Per-kamera state ──────────────────────────────────────────────────────────

state_lock = threading.Lock()
cache_lock = threading.Lock()

cam_pending_timer    = {c: None for c in LPR_CAMERAS}
cam_pending_event_id = {c: None for c in LPR_CAMERAS}
cam_lpr_collection   = {c: {} for c in LPR_CAMERAS}
cam_lpr_frames       = {c: {} for c in LPR_CAMERAS}
cam_event_frames     = {c: {} for c in LPR_CAMERAS}
cam_snapshot_cache   = {c: {} for c in LPR_CAMERAS}
_last_resultat       = {}  # camera -> (value, timestamp)


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ukjente (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            tidspunkt TEXT NOT NULL,
            plate     TEXT NOT NULL,
            event_id  TEXT,
            snapshot  TEXT,
            kilde     TEXT
        )
    """)
    for col in ['kilde', 'frigate_plate', 'camera']:
        try:
            conn.execute(f"ALTER TABLE ukjente ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()
    log.info("Database klar")


def lagre_i_db(plate, event_id, tidspunkt, snapshot_path, kilde, frigate_plate=None, camera=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "INSERT INTO ukjente (tidspunkt, plate, event_id, snapshot, kilde, frigate_plate, camera) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tidspunkt, plate, event_id, snapshot_path, kilde, frigate_plate, camera)
        )
        conn.commit()
        conn.close()
        log.info(f"Lagret i database: {plate} ({kilde})")
    except Exception as e:
        log.warning(f"Database-skriving feilet: {e}")


# ── Snapshot ──────────────────────────────────────────────────────────────────

def hent_snapshot(event_id, tidspunkt, prefiks=""):
    try:
        url = f"{FRIGATE_API}/api/events/{event_id}/snapshot.jpg"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            ts = tidspunkt.replace(':', '-').replace(' ', '_')
            filnavn = f"{ts}_{prefiks}.jpg" if prefiks else f"{ts}.jpg"
            path = os.path.join(SNAPSHOT_DIR, filnavn)
            with open(path, 'wb') as f:
                f.write(r.content)
            log.info(f"Snapshot lagret: {path}")
            return path
        log.warning(f"Snapshot HTTP {r.status_code}")
    except Exception as e:
        log.warning(f"Snapshot-henting feilet: {e}")
    return None


def prefetch_snapshot(event_id, camera):
    tidspunkt = now()
    path = hent_snapshot(event_id, tidspunkt, prefiks="gpt")
    if path:
        with cache_lock:
            cam_snapshot_cache[camera][event_id] = path
        log.info(f"Snapshot cached for event {event_id}")
    else:
        log.warning(f"Prefetch feilet for event {event_id}")


# ── GPT-4o Vision ─────────────────────────────────────────────────────────────

LOGG_DB = "/opt/homeserver/lpr_ukjente/logg.db"

def logg_til_db(tidspunkt, plate, camera):
    try:
        conn = sqlite3.connect(LOGG_DB)
        conn.execute(
            "INSERT INTO logg (tidspunkt, plate, camera) VALUES (?, ?, ?)",
            (tidspunkt, plate, camera)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"Logg-skriving feilet: {e}")
def gpt_les_skilt(snapshot_path):
    try:
        with open(snapshot_path, 'rb') as f:
            bilde_b64 = base64.b64encode(f.read()).decode('utf-8')
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {OPENAI_API_KEY}"}
        payload = {
            "model": GPT_MODEL, "max_tokens": 20,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{bilde_b64}", "detail": "high"}},
                {"type": "text", "text": (
                    "Read the Norwegian license plate visible in this image. "
                    "Norwegian plates have 2 capital letters followed by 4 or 5 digits "
                    "(e.g. AB12345 for cars, AB1234 for motorcycles). "
                    "Examine the image carefully and reply with ONLY the plate number."
                )}
            ]}]
        }
        r = requests.post("https://api.openai.com/v1/chat/completions",
                          headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            tekst = r.json()['choices'][0]['message']['content'].strip()
            log.info(f"GPT svarte: {tekst}")
            match = PLATE_REGEX.search(tekst)
            if match:
                return match.group()
        else:
            log.warning(f"GPT API feilet: HTTP {r.status_code}")
    except Exception as e:
        log.warning(f"GPT-kall feilet: {e}")
    return None




def camera_gpt_enabled(camera):
    """Per-kamera gpt_enabled. Faller tilbake til global GPT_ENABLED."""
    try:
        with open("/opt/homeserver/settings.json") as f:
            d = json.load(f)
        cam = next((c for c in d.get('cameras', []) if c['name'] == camera), None)
        if cam and 'gpt_enabled' in cam:
            return bool(cam['gpt_enabled'])
    except Exception:
        pass
    return GPT_ENABLED


def camera_gpt_verify(camera):
    """Per-kamera gpt_verify – alltid kjør GPT i tillegg til Frigate."""
    try:
        with open("/opt/homeserver/settings.json") as f:
            cameras = json.load(f).get('cameras', [])
        cam = next((c for c in cameras if c['name'] == camera), None)
        return bool(cam.get('gpt_verify', False)) if cam else False
    except Exception:
        return False


def gpt_fallback(client, event_id, camera, frigate_plate=None):
    er_verifisering = frigate_plate is not None
    tidspunkt = now()
    log.info(f"GPT-{'verifisering' if er_verifisering else 'fallback'} for {event_id} ({camera})"
             + (f" (Frigate: {frigate_plate})" if er_verifisering else ""))

    snapshot_path = hent_snapshot(event_id, tidspunkt, prefiks="gpt")
    if not snapshot_path:
        try:
            _r2 = requests.get(f"http://127.0.0.1:1984/api/frame.jpeg?src={camera}", timeout=3)
            if _r2.status_code == 200 and len(_r2.content) > 1000:
                ts2 = tidspunkt.replace(':', '-').replace(' ', '_')
                snapshot_path = os.path.join(SNAPSHOT_DIR, f"{ts2}_gpt.jpg")
                with open(snapshot_path, 'wb') as f:
                    f.write(_r2.content)
                log.info(f"GPT live frame lagret: {snapshot_path}")
            else:
                snapshot_path = None
        except Exception:
            snapshot_path = None
        if not snapshot_path:
            with cache_lock:
                snapshot_path = cam_snapshot_cache.get(camera, {}).pop(event_id, None)

    plate = gpt_les_skilt(snapshot_path) if snapshot_path else None

    if plate:
        log.info(f"GPT leste skilt: {plate}")
        kilde = "gpt_verifisert" if er_verifisering else "gpt_fallback"
        logg_til_db(tidspunkt, plate, camera)
        kjente = load_kjente_skilt()
        navn = kjente.get(plate, "ukjent")
        client.publish(f"loxone/{camera}/skilt", plate, retain=True)
        client.publish(f"loxone/{camera}/resultat", navn, qos=1, retain=True)
        schedule_reset(client, camera)
        lagre_i_db(plate, event_id, tidspunkt, snapshot_path, kilde=kilde, camera=camera)
    else:
        if er_verifisering:
            log.info(f"GPT feilet, bruker Frigate sin lesing: {frigate_plate}")
            kjente = load_kjente_skilt()
            navn = kjente.get(frigate_plate, "ukjent")
            logg_til_db(tidspunkt, frigate_plate, camera)
            client.publish(f"loxone/{camera}/skilt", frigate_plate, retain=True)
            client.publish(f"loxone/{camera}/resultat", navn, qos=1, retain=True)
            schedule_reset(client, camera)
            lagre_i_db(frigate_plate, event_id, tidspunkt, snapshot_path,
                        kilde="frigate_gpt_feilet", camera=camera)
        else:
            log.info("GPT kunne ikke lese skilt, publiserer 'ukjent'")
            threading.Thread(target=send_tts, args=("Ukjent i oppkjørselen",), daemon=True).start()
            logg_til_db(tidspunkt, 'ukjent', camera)
            client.publish(f"loxone/{camera}/resultat", "ukjent", qos=1, retain=True)
            schedule_reset(client, camera)
            lagre_i_db("ukjent", event_id, tidspunkt, snapshot_path,
                        kilde="ukjent", frigate_plate=frigate_plate, camera=camera)


# ── Hjelpefunksjoner ──────────────────────────────────────────────────────────



def schedule_reset(client, camera):
    def reset():
        client.publish(f"loxone/{camera}/resultat", "", qos=0, retain=False)
        log.info(f"Resultat-topic blanket ({camera})")
    t = threading.Timer(RESET_SECONDS, reset)
    t.daemon = True
    t.start()


def send_tts(tekst):
    try:
        s = _load_settings_full()
        tts = s.get('dashboard', {}).get('tts', {})
        if not tts.get('enabled', False):
            return
        ip   = tts.get('loxone_ip', '192.168.1.100')
        user = tts.get('loxone_user', '')
        pwd  = tts.get('loxone_pass', '')
        zones = []
        if tts.get('gang', False):
            zones.append(tts.get('gang_input', 'TTS LPR Gang'))
        if tts.get('stue', False):
            zones.append(tts.get('stue_input', 'TTS LPR Stue'))
        for zone in zones:
            url = f"http://{user}:{pwd}@{ip}/dev/sps/io/{requests.utils.quote(zone)}/{requests.utils.quote(tekst)}"
            r = requests.get(url, timeout=5)
            log.info(f"TTS '{tekst}' → {zone} (HTTP {r.status_code})")
    except Exception as e:
        log.warning(f"TTS feilet: {e}")


def _behandle_plate(client, plate, eid, camera, preframe=None):
    tidspunkt = now()
    live_frame = preframe
    if not live_frame:
        try:
            _r = requests.get(f"http://127.0.0.1:1984/api/frame.jpeg?src={camera}", timeout=3)
            live_frame = _r.content if _r.status_code == 200 and len(_r.content) > 1000 else None
        except Exception:
            live_frame = None
    logg_til_db(tidspunkt, plate, camera)
    log.info(f"Skilt bekreftet: {plate} ({camera})")
    kjente = load_kjente_skilt()
    navn = kjente.get(plate, "ukjent")
    log.info(f"Publiserer som: {navn}")
    client.publish(f"loxone/{camera}/skilt", plate, retain=True)
    client.publish(f"loxone/{camera}/resultat", navn, qos=1, retain=True)
    schedule_reset(client, camera)
    threading.Thread(target=send_tts, args=(f"{navn} i oppkjørselen",), daemon=True).start()

    if camera_gpt_verify(camera):
        def _gpt_verify(event_id=eid, cam=camera, frigate_plate=plate):
            import time as _t
            _t.sleep(3)
            snap = hent_snapshot(event_id, now(), prefiks="verify")
            if not snap:
                log.info(f"GPT verify: ingen snapshot ({cam})")
                return
            gpt_result = gpt_les_skilt(snap)
            import sqlite3 as _sq
            try:
                with _sq.connect('/opt/homeserver/lpr_ukjente/ukjente.db') as _conn:
                    row = _conn.execute("SELECT kilde FROM ukjente WHERE event_id = ?", (event_id,)).fetchone()
                    if row:
                        if gpt_result and gpt_result != frigate_plate:
                            log.warning(f"GPT verify UENIG: Frigate={frigate_plate}, GPT={gpt_result} ({cam})")
                            _conn.execute("UPDATE ukjente SET kilde = ? WHERE event_id = ?",
                                         (row[0] + '_gpt_uenig', event_id))
                        elif gpt_result:
                            log.info(f"GPT verify ENIG: {frigate_plate} ✅ ({cam})")
                            _conn.execute("UPDATE ukjente SET kilde = ? WHERE event_id = ?",
                                         (row[0] + '_gpt_enig', event_id))
                        else:
                            log.info(f"GPT verify: kunne ikke lese ({cam})")
            except Exception as _e:
                log.warning(f"GPT verify DB-oppdatering feilet: {_e}")
        threading.Thread(target=_gpt_verify, daemon=True).start()

    def lagre():
        if live_frame:
            ts = tidspunkt.replace(':', '-').replace(' ', '_')
            fp = os.path.join(SNAPSHOT_DIR, f"{ts}_{plate}.jpg")
            with open(fp, 'wb') as f:
                f.write(live_frame)
            path = fp
            log.info(f"Live frame lagret: {fp}")
        else:
            path = hent_snapshot(eid, tidspunkt, prefiks=plate)
        kilde = "frigate" if navn == "ukjent" else "kjent"
        lagre_i_db(plate, eid, tidspunkt, path, kilde=kilde, camera=camera)

    threading.Thread(target=lagre, daemon=True).start()


def load_kjente_skilt():
    try:
        with open(SKILT_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ── Snapshot-rens ─────────────────────────────────────────────────────────────

def prune_snapshots():
    import time as _t
    cutoff = _t.time() - (PRUNE_DAYS * 86400)
    try:
        removed = 0
        for fn in os.listdir(SNAPSHOT_DIR):
            fp = os.path.join(SNAPSHOT_DIR, fn)
            if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                os.remove(fp)
                removed += 1
        if removed:
            log.info(f"Slettet {removed} gamle snapshots")
    except Exception as e:
        log.warning(f"Snapshot-rens feilet: {e}")


def prune_snapshots_worker():
    import time as _t
    while True:
        _t.sleep(86400)
        prune_snapshots()


# ── MQTT-handlers ─────────────────────────────────────────────────────────────

def on_timeout(client, event_id, camera):
    with state_lock:
        if cam_pending_event_id.get(camera) != event_id:
            return
        log.info(f"Event {event_id} ({camera}): timeout, starter GPT-fallback")
        cam_pending_timer[camera] = None
        cam_pending_event_id[camera] = None
    t = threading.Thread(target=gpt_fallback, args=(client, event_id, camera))
    t.daemon = True
    t.start()


def on_event_new(client, event_id, label, camera):
    if camera not in LPR_CAMERAS or label != "car":
        return
    with state_lock:
        if cam_pending_timer.get(camera):
            cam_pending_timer[camera].cancel()
        log.info(f"Event {event_id}: ny bil-event ({camera}), starter {WAIT_SECONDS}s timer")
        cam_pending_event_id[camera] = event_id
        t = threading.Timer(WAIT_SECONDS, on_timeout, args=(client, event_id, camera))
        t.daemon = True
        t.start()
        cam_pending_timer[camera] = t

    def capture_delayed():
        import time as _t
        _t.sleep(SNAPSHOT_DELAY)
        if event_id not in cam_event_frames.get(camera, {}):
            try:
                _fr = requests.get(f"http://127.0.0.1:1984/api/frame.jpeg?src={camera}", timeout=5)
                if _fr.status_code == 200 and len(_fr.content) > 1000:
                    cam_event_frames.setdefault(camera, {})[event_id] = _fr.content
                    cam_lpr_frames.setdefault(camera, {})[event_id]   = _fr.content
                    log.info(f"Delayed frame captured for {event_id} ({camera})")
                else:
                    log.warning(f"Delayed frame feilet: HTTP {_fr.status_code}")
            except Exception as e:
                log.warning(f"Delayed frame exception: {e}")
    threading.Thread(target=capture_delayed, daemon=True).start()


def on_event_end(client, event_id, camera):
    if camera not in LPR_CAMERAS:
        return
    log.info(f"Event {event_id}: avsluttet ({camera})")
    with state_lock:
        cam_lpr_collection.get(camera, {}).pop(event_id, None)
        cam_lpr_frames.get(camera, {}).pop(event_id, None)
        cam_event_frames.get(camera, {}).pop(event_id, None)
    client.publish(f"loxone/{camera}/skilt", "", retain=True)
    with state_lock:
        still_pending = (cam_pending_event_id.get(camera) == event_id)
    if still_pending:
        threading.Thread(target=prefetch_snapshot, args=(event_id, camera), daemon=True).start()


def on_lpr(client, plate_raw, camera):
    if camera not in LPR_CAMERAS:
        return
    match = PLATE_REGEX.search(plate_raw or "")
    if not match:
        return
    plate = match.group()

    old_timer = None
    with state_lock:
        eid = cam_pending_event_id.get(camera)
        if not eid:
            return
        cam_lpr_collection.setdefault(camera, {})
        if eid not in cam_lpr_collection[camera]:
            cam_lpr_collection[camera][eid] = {'votes': [], 'timer': None}
        cam_lpr_collection[camera][eid]['votes'].append(plate)
        log.info(f"LPR stemme: {plate} ({len(cam_lpr_collection[camera][eid]['votes'])} stemmer for {eid})")
        first_vote = (len(cam_lpr_collection[camera][eid]['votes']) == 1)
        old_timer = cam_lpr_collection[camera][eid].get('timer')
        if cam_pending_timer.get(camera):
            cam_pending_timer[camera].cancel()
            cam_pending_timer[camera] = None

    if old_timer:
        old_timer.cancel()

    if first_vote and eid not in cam_lpr_frames.get(camera, {}):
        try:
            _fr = requests.get(f"http://127.0.0.1:1984/api/frame.jpeg?src={camera}", timeout=2)
            if _fr.status_code == 200 and len(_fr.content) > 1000:
                cam_lpr_frames.setdefault(camera, {})[eid] = _fr.content
                log.info(f"LPR første-stemme frame captured for {eid} ({camera})")
            else:
                log.warning(f"Første-stemme frame feilet: HTTP {_fr.status_code}")
        except Exception as e:
            log.warning(f"Første-stemme frame exception: {e}")

    def commit():
        with state_lock:
            col = cam_lpr_collection.get(camera, {}).pop(eid, None)
            if not col or not col['votes']:
                return
            # Prioriter 5-sifrede skilt over 4-sifrede (4-siffer er MC, sjelden)
            fem_sifret = [v for v in col['votes'] if len(v) == 7]
            if fem_sifret:
                vinner = max(set(fem_sifret), key=fem_sifret.count)
            else:
                vinner = max(set(col['votes']), key=col['votes'].count)
            cam_pending_event_id[camera] = None
        total = len(col['votes'])
        best  = col['votes'].count(vinner)
        konf  = best / total
        log.info(f"LPR vinner: {vinner} ({best}/{total} stemmer, konfidens {konf:.0%}) ({camera})")
        preframe = cam_lpr_frames.get(camera, {}).pop(eid, None)
        if konf >= KONF_TERSKEL:
            _behandle_plate(client, vinner, eid, camera, preframe=preframe)
        else:
            if not camera_gpt_enabled(camera):
                _behandle_plate(client, vinner, eid, camera, preframe=preframe)
                return
            log.info(f"Lav konfidens ({konf:.0%}), sender til GPT-fallback ({camera})")
            threading.Thread(target=gpt_fallback, args=(client, eid, camera, vinner),
                             daemon=True).start()

    new_timer = threading.Timer(COMMIT_WINDOW, commit)
    new_timer.daemon = True
    new_timer.start()

    with state_lock:
        if camera in cam_lpr_collection and eid in cam_lpr_collection[camera]:
            cam_lpr_collection[camera][eid]['timer'] = new_timer


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    if msg.topic == "frigate/events":
        ev_type  = payload.get('type')
        after    = payload.get('after') or payload.get('before') or {}
        event_id = after.get('id')
        label    = after.get('label')
        camera   = after.get('camera')
        if not event_id:
            return
        if ev_type == 'new':
            on_event_new(client, event_id, label, camera)
        elif ev_type == 'end':
            on_event_end(client, event_id, camera)

    elif msg.topic == "frigate/tracked_object_update":
        if payload.get('type') == 'lpr':
            camera = payload.get('camera', '')
            on_lpr(client, payload.get('plate', ''), camera)


def on_connect(client, userdata, flags, rc, *args):
    log.info(f"Tilkoblet MQTT (rc={rc})")
    client.subscribe("frigate/events")
    client.subscribe("frigate/tracked_object_update")
    for camera in LPR_CAMERAS:
        client.publish(f"loxone/{camera}/skilt", "", retain=True)
    log.info(f"LPR aktiv på kameraer: {LPR_CAMERAS}")


def main():
    init_db()
    prune_snapshots()
    threading.Thread(target=prune_snapshots_worker, daemon=True).start()
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="lpr_bridge_v2")
    except AttributeError:
        client = mqtt.Client(client_id="lpr_bridge_v2")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)

    def shutdown(signum, frame):
        log.info("Shutdown")
        client.loop_stop()
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    client.loop_forever()


if __name__ == "__main__":
    main()
