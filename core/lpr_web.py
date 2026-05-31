#!/usr/bin/env python3
"""Villa Larsnes – Hjemmeserver dashboard."""
import csv
import logging
import sqlite3
import subprocess
import time
import urllib.request
import gzip
import html
import json
import mimetypes
import os
import shutil
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('lpr-web')

BASE        = "/opt/homeserver"
LOG_FILE    = f"{BASE}/lpr_log.txt"
SKILT_FILE  = f"{BASE}/kjente_skilt.json"
WEATHER_LOG = f"{BASE}/weather_log.csv"
LUDVIG_LOG  = f"{BASE}/ludvig_log.csv"
STORM_FILE  = f"{BASE}/storm_state.txt"
STATIC_DIR  = f"{BASE}/static"
TEMPLATE    = f"{BASE}/templates/index.html"
MAX_LINES        = 2000
UKJENTE_DB       = "/opt/homeserver/lpr_ukjente/ukjente.db"
UKJENTE_SNAPSHOTS = "/opt/homeserver/lpr_ukjente/snapshots"


SETTINGS_FILE    = f"{BASE}/settings.json"
SETTINGS_DEFAULTS = {
    "lpr":    {"confidence_threshold": 0.8, "gpt_enabled": True, "wait_seconds": 10,
               "reset_seconds": 5, "commit_window": 1.5, "snapshot_delay": 1.0, "snapshot_retention_days": 30},
    "ludvig": {"trigger_count": 3, "trigger_window_sec": 600, "cooldown_sec": 1200, "retain_days": 90},
    "web":    {"max_log_lines": 2000, "stats_refresh_sec": 15, "storm_refresh_sec": 3},
    "system": {"name": "Villalarsnes", "frigate_url": "https://villaserver:8971", "portainer_url": "http://villaserver:9000", "pihole_url": "http://villaserver/admin"},
    "dashboard": {"tts": {"enabled": False, "gang": True, "stue": False, "volume": 20,
                          "loxone_ip": "192.168.1.100", "loxone_user": "voicebridge",
                          "loxone_pass": "Villa-larsnes", "gang_input": "TTS LPR Gang",
                          "stue_input": "TTS LPR Stue"}},
}

def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        result = {k: (dict(v) if not any(isinstance(vv, dict) for vv in v.values()) else {kk: dict(vv) if isinstance(vv, dict) else vv for kk, vv in v.items()}) for k, v in SETTINGS_DEFAULTS.items()}
        for section, values in saved.items():
            if section in result:
                if isinstance(values, dict):
                    for k, v in values.items():
                        if v is None:
                            continue
                        if isinstance(v, dict) and isinstance(result[section].get(k), dict):
                            result[section][k].update(v)
                        else:
                            result[section][k] = v
        return result
    except Exception:
        return {k: dict(v) for k, v in SETTINGS_DEFAULTS.items()}

def save_settings_file(data):
    # Filtrer ut None-verdier før lagring
    def filter_none(obj):
        if isinstance(obj, dict):
            return {k: filter_none(v) for k, v in obj.items() if v is not None}
        return obj
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(filter_none(data), f, indent=2)

def restart_service(name):
    try:
        subprocess.run(['systemctl', 'restart', name], timeout=15, check=True)
        return True
    except Exception:
        return False



def sync_frigate_snapshots(cameras):
    """Aktiver/deaktiver Frigate snapshots basert på LPR-status per kamera."""
    try:
        config_path = "/opt/homeserver/frigate/config.yml"
        with open(config_path) as f:
            config = f.read()

        for cam in cameras:
            name = cam['name']
            lpr  = cam.get('lpr', False)
            snap_block = f"""  {name}:
    snapshots:
      enabled: true
      retain:
        default: 30
    ffmpeg:"""
            no_snap_block = f"""  {name}:
    ffmpeg:"""

            has_snapshots = f"  {name}:" in config and "snapshots:" in config.split(f"  {name}:")[1].split("\n  ")[0]
            if lpr and not has_snapshots:
                # Legg til snapshots før ffmpeg
                config = config.replace(f"  {name}:\n    ffmpeg:", snap_block)
                log.info(f"Frigate snapshots aktivert for {name}")
            elif not lpr and has_snapshots:
                # Fjern snapshots uansett posisjon
                config = config.replace(snap_block, no_snap_block)
                log.info(f"Frigate snapshots deaktivert for {name}")

        with open(config_path, 'w') as f:
            f.write(config)
        return True
    except Exception as e:
        log.warning(f"sync_frigate_snapshots feilet: {e}")
        return False

def load_template(replacements):
    with open(TEMPLATE, encoding='utf-8') as f:
        tpl = f.read()
    for key, val in replacements.items():
        tpl = tpl.replace(key, val)
    return tpl


def load_ukjente(all_=False):
    try:
        conn = sqlite3.connect(UKJENTE_DB)
        conn.row_factory = sqlite3.Row
        if all_:
            query = "SELECT id, tidspunkt, plate, snapshot, kilde, frigate_plate, camera FROM ukjente WHERE kilde NOT LIKE 'kjent%' ORDER BY id DESC"
            rows = conn.execute(query).fetchall()
        else:
            today = datetime.now().strftime('%Y-%m-%d')
            query = "SELECT id, tidspunkt, plate, snapshot, kilde, frigate_plate, camera FROM ukjente WHERE kilde NOT LIKE 'kjent%' AND tidspunkt LIKE ? ORDER BY id DESC"
            rows = conn.execute(query, (f"{today}%",)).fetchall()
        conn.close()
        result = []
        for r in rows:
            snap = r['snapshot']
            filename = os.path.basename(snap) if snap else None
            result.append({
                'id':            r['id'],
                'tidspunkt':     r['tidspunkt'],
                'plate':         r['plate'],
                'snapshot':      f'/snapshot/{filename}' if filename else None,
                'kilde':         r['kilde'],
                'frigate_plate': r['frigate_plate'],
                'camera':        r['camera'],
            })
        return result
    except Exception:
        return []


def load_events_24h(all_=False):
    skilt = load_skilt()
    try:
        with open(SETTINGS_FILE) as _sf:
            _cams = json.load(_sf).get('cameras', [])
        lpr_cams = [c['name'] for c in _cams if c.get('lpr')] or ['oppkjorsel']
    except Exception:
        lpr_cams = ['oppkjorsel']
    events = []
    cutoff = int(time.time()) - (86400 * 30 if all_ else 86400)
    for _cam in lpr_cams:
        try:
            _url = f'http://localhost:5000/api/events?camera={_cam}&label=car&after={cutoff}&limit=500&has_snapshot=1'
            with urllib.request.urlopen(_url, timeout=5) as r:
                _evs = json.loads(r.read())
                for _e in _evs:
                    _e['_lpr_camera'] = _cam
                events.extend(_evs)
        except Exception:
            pass
    if not events:
        return []
    events.sort(key=lambda e: e.get('start_time', 0), reverse=True)
    ukjente_by_event = {}
    local_snapshots  = {}
    try:
        conn = sqlite3.connect(UKJENTE_DB)
        conn.row_factory = sqlite3.Row
        ukjente_kilde = {}
        ukjente_frigate = {}
        ukjente_camera = {}
        for row in conn.execute("SELECT event_id, plate, snapshot, kilde, frigate_plate, camera FROM ukjente WHERE event_id IS NOT NULL"):
            ukjente_by_event[row['event_id']] = row['plate']
            ukjente_kilde[row['event_id']]    = row['kilde']
            ukjente_frigate[row['event_id']] = row['frigate_plate']
            ukjente_camera[row['event_id']]  = row['camera']
            if row['snapshot']:
                local_snapshots[row['event_id']] = '/snapshot/' + os.path.basename(row['snapshot'])
        conn.close()
    except Exception:
        pass
    log_entries = []
    try:
        conn = sqlite3.connect(LOGG_DB)
        cutoff_str = (datetime.now() - timedelta(hours=25)).strftime('%Y-%m-%d %H:%M:%S')
        rows = conn.execute("SELECT tidspunkt, plate FROM logg WHERE tidspunkt > ? ORDER BY id ASC", (cutoff_str,)).fetchall()
        conn.close()
        for r in rows:
            try:
                ts = datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S')
                log_entries.append({'ts': ts, 'plate': r[1]})
            except ValueError:
                pass
    except Exception:
        pass
    result = []
    for ev in events:
        event_id = ev.get('id', '')
        start_ts = ev.get('start_time', 0)
        end_ts   = ev.get('end_time') or (start_ts + 30)
        plate    = ukjente_by_event.get(event_id)
        source   = 'ukjent'
        if not plate:
            ev_start = datetime.fromtimestamp(start_ts)
            ev_end   = datetime.fromtimestamp(end_ts) + timedelta(seconds=5)
            for entry in log_entries:
                if ev_start <= entry['ts'] <= ev_end:
                    plate  = entry['plate']
                    source = 'lpr'
                    break
        if not plate:
            plate  = 'ukjent'
            source = 'ukjent'
        navn = skilt.get(plate, '')
        result.append({
            'event_id':       event_id,
            'tidspunkt':      datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d %H:%M'),
            'plate':          plate,
            'navn':           navn,
            'source':         source,
            'kilde':          ukjente_kilde.get(event_id, 'kjent' if source == 'lpr' else None),
            'frigate_plate':  ukjente_frigate.get(event_id),
            'camera':         ukjente_camera.get(event_id) or ev.get('_lpr_camera', ''),
            'local_snapshot': local_snapshots.get(event_id),
        })
    return result


def load_statistikk():
    skilt  = load_skilt()
    try:
        with open('/opt/homeserver/hjemme_skilt.json') as f:
            hjemme = set(json.load(f))
    except Exception:
        hjemme = set()

    lines   = load_all_lines()
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(' ', maxsplit=3)
        if len(parts) >= 3:
            try:
                ts    = datetime.strptime(f"{parts[0]} {parts[1]}", '%Y-%m-%d %H:%M:%S')
                plate = parts[2].strip()
                if plate:
                    entries.append({'ts': ts, 'plate': plate})
            except ValueError:
                pass
    if not entries:
        return {}

    vehicle_visits = defaultdict(list)
    for e in entries:
        vehicle_visits[e['plate']].append(e['ts'])

    ukjente_count = sum(1 for e in entries if e['plate'] == 'ukjent' or e['plate'] not in skilt)

    # Kun kjente besøkende (ikke hjemmebiler, ikke ukjente)
    vehicle_stats = []
    for plate, visits in vehicle_visits.items():
        if plate == 'ukjent' or plate not in skilt or plate in hjemme:
            continue
        vs   = sorted(visits)
        navn = skilt.get(plate, '')
        avg_days = round((vs[-1] - vs[0]).days / (len(vs) - 1), 1) if len(vs) > 1 and (vs[-1] - vs[0]).days > 0 else None
        hours     = [v.hour for v in vs]
        top_hours = [h for h, _ in Counter(hours).most_common(2)]
        vehicle_stats.append({
            'plate':      plate,
            'navn':       navn,
            'count':      len(vs),
            'first':      vs[0].strftime('%Y-%m-%d %H:%M'),
            'last':       vs[-1].strftime('%Y-%m-%d %H:%M'),
            'avg_days':   avg_days,
            'top_hours':  top_hours,
        })
    vehicle_stats.sort(key=lambda x: x['count'], reverse=True)

    day_visits  = defaultdict(set)
    weekday_cnt = defaultdict(int)
    hour_cnt    = defaultdict(int)
    for e in entries:
        if e['plate'] in hjemme:
            continue
        day_visits[e['ts'].date()].add(e['plate'])
        weekday_cnt[e['ts'].weekday()] += 1
        hour_cnt[e['ts'].hour] += 1

    today = datetime.now().date()
    daily = []
    for i in range(9, -1, -1):
        d = today - timedelta(days=i)
        daily.append({
            'label':  d.strftime('%-d. %b'),
            'unique': len(day_visits.get(d, set())),
            'total':  sum(1 for e in entries if e['ts'].date() == d and e['plate'] not in hjemme),
        })

    dager = ['Man','Tir','Ons','Tor','Fre','Lør','Søn']

    hjemme_stats = []
    for plate in sorted(hjemme):
        if plate not in vehicle_visits:
            continue
        vs   = sorted(vehicle_visits[plate])
        navn = skilt.get(plate, plate)
        avg  = round((vs[-1] - vs[0]).days / (len(vs) - 1), 1) if len(vs) > 1 and (vs[-1] - vs[0]).days > 0 else None
        hrs  = [v.hour for v in vs]
        top_hours = [h for h, _ in Counter(hrs).most_common(2)]
        hjemme_stats.append({
            'plate':     plate,
            'navn':      navn,
            'count':     len(vs),
            'avg_days':  avg,
            'top_hours': top_hours,
            'last':      vs[-1].strftime('%Y-%m-%d %H:%M'),
        })

    return {
        'total':         len(entries),
        'unike':         len([p for p in vehicle_visits if p not in hjemme and p != 'ukjent']),
        'ukjente_count': ukjente_count,
        'vehicle_stats': vehicle_stats[:30],
        'top5':          vehicle_stats[:5],
        'daily':         daily,
        'weekday':       [{'day': dager[i], 'count': weekday_cnt.get(i, 0)} for i in range(7)],
        'hourly':        [{'hour': f'{i:02d}', 'count': hour_cnt.get(i, 0)} for i in range(24)],
        'hjemme_stats':  hjemme_stats,
    }


def load_skilt():
    try:
        with open(SKILT_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_skilt(data):
    with open(SKILT_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_lines(filepath, compressed=False):
    try:
        if compressed:
            with gzip.open(filepath, 'rt', encoding='utf-8', errors='ignore') as f:
                return f.readlines()
        with open(filepath, encoding='utf-8', errors='ignore') as f:
            return f.readlines()
    except FileNotFoundError:
        return []


LOGG_DB = "/opt/homeserver/lpr_ukjente/logg.db"

def load_all_lines():
    try:
        conn = sqlite3.connect(LOGG_DB)
        rows = conn.execute("SELECT tidspunkt, plate, camera FROM logg ORDER BY id ASC").fetchall()
        conn.close()
        return [f"{r[0]} {r[1]} {r[2] or ''}\n" for r in rows]
    except Exception:
        return []

def load_today_lines():
    try:
        conn = sqlite3.connect(LOGG_DB)
        today = datetime.now().strftime('%Y-%m-%d')
        rows = conn.execute(
            "SELECT tidspunkt, plate, camera FROM logg WHERE tidspunkt LIKE ? ORDER BY id ASC",
            (f"{today}%",)
        ).fetchall()
        conn.close()
        return [f"{r[0]} {r[1]} {r[2] or ''}\n" for r in rows]
    except Exception:
        return []
def load_logg_entries(all_=False):
    try:
        skilt = load_skilt()
        conn_logg = sqlite3.connect(LOGG_DB)
        conn_logg.row_factory = sqlite3.Row
        if all_:
            rows = conn_logg.execute(
                "SELECT id, tidspunkt, plate, camera FROM logg ORDER BY id DESC"
            ).fetchall()
        else:
            today = datetime.now().strftime('%Y-%m-%d')
            rows = conn_logg.execute(
                "SELECT id, tidspunkt, plate, camera FROM logg WHERE tidspunkt LIKE ? ORDER BY id DESC",
                (f"{today}%",)
            ).fetchall()
        conn_logg.close()

        # Hent alle ukjente for å koble snapshot
        conn_ukjente = sqlite3.connect(UKJENTE_DB)
        conn_ukjente.row_factory = sqlite3.Row
        ukjente_rows = conn_ukjente.execute(
            "SELECT tidspunkt, plate, snapshot, kilde, frigate_plate FROM ukjente"
        ).fetchall()
        conn_ukjente.close()

        # Bygg oppslagstabell: (plate, dato+time uten sekunder) -> ukjente-rad
        ukjente_map = {}
        for u in ukjente_rows:
            key = (u['plate'], u['tidspunkt'][:16])  # match på minutt
            ukjente_map[key] = u

        result = []
        for r in rows:
            plate = r['plate']
            key = (plate, r['tidspunkt'][:16])
            u = ukjente_map.get(key)
            snapshot = None
            kilde = None
            frigate_plate = None
            if u and u['snapshot']:
                snapshot = '/snapshot/' + os.path.basename(u['snapshot'])
                kilde = u['kilde']
                frigate_plate = u['frigate_plate']
            result.append({
                'tidspunkt': r['tidspunkt'],
                'dato':      r['tidspunkt'][:10],
                'tid':       r['tidspunkt'][11:16],
                'plate':     plate,
                'camera':    r['camera'] or '',
                'navn':      skilt.get(plate, ''),
                'snapshot':  snapshot,
                'kilde':     kilde,
                'frigate_plate': frigate_plate,
                'linje':     f"{r['tidspunkt']} {plate}",
            })
        return result
    except Exception as e:
        log.warning(f"load_logg_entries feilet: {e}")
        return []
    
def get_system_stats():
    stats = {}
    try:
        load1, load5, load15 = os.getloadavg()
        stats['load'] = f"{load1:.2f} / {load5:.2f} / {load15:.2f}"
    except Exception:
        stats['load'] = 'N/A'
    try:
        meminfo = {}
        with open('/proc/meminfo') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(':')] = int(parts[1])
        total     = meminfo.get('MemTotal', 1)
        available = meminfo.get('MemAvailable', 0)
        used      = total - available
        pct       = int(used / total * 100)
        stats['ram']     = f"{used // 1024} MB / {total // 1024} MB ({pct}%)"
        stats['ram_pct'] = pct
    except Exception:
        stats['ram']     = 'N/A'
        stats['ram_pct'] = 0
    try:
        usage    = shutil.disk_usage('/')
        used_gb  = usage.used  / 1e9
        total_gb = usage.total / 1e9
        pct      = int(usage.used / usage.total * 100)
        stats['disk']     = f"{used_gb:.1f} GB / {total_gb:.1f} GB ({pct}%)"
        stats['disk_pct'] = pct
    except Exception:
        stats['disk']     = 'N/A'
        stats['disk_pct'] = 0
    return stats


def load_weather(hours):
    bucket_sec = {3: 0, 24: 300, 168: 1800}.get(hours, 0)
    cutoff     = datetime.now() - timedelta(hours=hours)
    epoch      = datetime(1970, 1, 1)
    raw        = []
    try:
        with open(WEATHER_LOG, 'r') as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                try:
                    ts = datetime.fromisoformat(row[0])
                    if ts < cutoff:
                        continue
                    raw.append({
                        'ts':        ts,
                        'temp':      float(row[1]) if len(row) > 1 and row[1] else None,
                        'wind':      float(row[2]) if len(row) > 2 and row[2] else None,
                        'rain':      int(row[3])   if len(row) > 3 and row[3] else 0,
                        'storm':     int(row[4])   if len(row) > 4 and row[4] else 0,
                        'solskinn':  int(row[5])   if len(row) > 5 and row[5] else 0,
                        'lysstyrke': int(float(row[6])) if len(row) > 6 and row[6] else None,
                    })
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        return []
    if not raw:
        return []
    if bucket_sec == 0:
        return [{'ts': r['ts'].strftime('%Y-%m-%dT%H:%M:%S'), 'temp': r['temp'],
                 'wind': r['wind'], 'rain': r['rain'], 'storm': r['storm'],
                 'solskinn': r['solskinn'], 'lysstyrke': r['lysstyrke']} for r in raw]
    buckets = defaultdict(list)
    for r in raw:
        key = int((r['ts'] - epoch).total_seconds() // bucket_sec) * bucket_sec
        buckets[key].append(r)
    result = []
    for key in sorted(buckets.keys()):
        group  = buckets[key]
        temps  = [r['temp']      for r in group if r['temp']      is not None]
        winds  = [r['wind']      for r in group if r['wind']      is not None]
        lux    = [r['lysstyrke'] for r in group if r['lysstyrke'] is not None]
        ts     = epoch + timedelta(seconds=key)
        result.append({
            'ts':        ts.strftime('%Y-%m-%dT%H:%M:%S'),
            'temp':      round(sum(temps) / len(temps), 1) if temps else None,
            'wind':      round(sum(winds) / len(winds), 1) if winds else None,
            'rain':      max(r['rain']     for r in group),
            'storm':     max(r['storm']    for r in group),
            'solskinn':  max(r['solskinn'] for r in group),
            'lysstyrke': int(sum(lux) / len(lux)) if lux else None,
        })
    return result


def load_ludvig():
    events = []
    try:
        with open(LUDVIG_LOG, 'r') as f:
            for row in csv.reader(f):
                if len(row) < 1:
                    continue
                try:
                    events.append(datetime.fromisoformat(row[0]))
                except ValueError:
                    continue
    except FileNotFoundError:
        pass

    events.sort()

    def get_night_date(ts):
        if ts.hour >= 17:
            return ts.date()
        elif ts.hour < 10:
            return (ts - timedelta(days=1)).date()
        return None

    nights = defaultdict(list)
    for ev in events:
        nd = get_night_date(ev)
        if nd is not None:
            nights[nd].append(ev)

    today       = datetime.now().date()
    nights_data = []
    for i in range(13, -1, -1):
        d   = today - timedelta(days=i)
        evs = nights.get(d, [])
        nights_data.append({
            'date':  d.isoformat(),
            'label': d.strftime('%-d. %b'),
            'count': len(evs),
            'first': evs[0].strftime('%H:%M')  if evs else None,
            'last':  evs[-1].strftime('%H:%M') if evs else None,
        })

    all_nights = [(d, evs) for d, evs in nights.items() if evs]
    stats = None
    if all_nights:
        counts   = [len(evs) for _, evs in all_nights]
        worst    = max(all_nights, key=lambda x: len(x[1]))
        calmest  = min(all_nights, key=lambda x: len(x[1]))
        all_evs  = [ev for _, evs in all_nights for ev in evs]
        def sort_key(ev):
            return ev.hour - 17 if ev.hour >= 17 else ev.hour + 7
        stats = {
            'avg':           round(sum(counts) / len(counts), 1),
            'worst_date':    worst[0].strftime('%-d. %b'),
            'worst_count':   len(worst[1]),
            'calmest_date':  calmest[0].strftime('%-d. %b'),
            'calmest_count': len(calmest[1]),
            'earliest':      min(all_evs, key=sort_key).strftime('%H:%M'),
            'latest':        max(all_evs, key=sort_key).strftime('%H:%M'),
        }

    recent = [{'ts': ev.strftime('%Y-%m-%dT%H:%M:%S'),
               'date': ev.strftime('%-d. %b'),
               'time': ev.strftime('%H:%M')}
              for ev in reversed(events[-100:])]

    # Timeline: siste 3 døgn
    today_date = datetime.now().date()
    timeline = []
    for i in range(2, -1, -1):
        d   = today_date - timedelta(days=i)
        evs = [ev for ev in events if ev.date() == d]
        timeline.append({
            'label':  d.strftime('%-d. %b'),
            'events': [{'time': ev.strftime('%H:%M'),
                        'hour': ev.hour + ev.minute / 60} for ev in evs]
        })

    return {'nights': nights_data, 'stats': stats, 'events': recent, 'timeline': timeline}






class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_html(self, body, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(body.encode())

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path):
        filepath = STATIC_DIR + path[7:]  # strip /static
        try:
            mime, _ = mimetypes.guess_type(filepath)
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-type', mime or 'text/plain')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith('/static/'):
            self.serve_static(parsed.path)
            return

        if parsed.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
            return

        if parsed.path == '/api/status':
            self.send_json(get_system_stats())
            return

        if parsed.path == '/api/storm':
            try:
                with open(STORM_FILE) as f:
                    val = int(f.read().strip())
            except Exception:
                val = 0
            self.send_json({'storm': val})
            return

        if parsed.path == '/api/weather':
            qs     = parse_qs(parsed.query)
            range_ = qs.get('range', ['3h'])[0]
            hours  = {'3h': 3, '1d': 24, '7d': 168}.get(range_, 3)
            self.send_json(load_weather(hours))
            return

        if parsed.path == '/api/ludvig':
            self.send_json(load_ludvig())
            return

        if parsed.path == '/api/logg':
            qs2      = parse_qs(parsed.query)
            all_     = qs2.get('all', ['0'])[0] == '1'
            page     = int(qs2.get('page', ['1'])[0])
            per_page = int(qs2.get('per_page', ['20'])[0])
            entries  = load_logg_entries(all_)
            total    = len(entries)
            start    = (page - 1) * per_page
            end      = start + per_page
            self.send_json({
                'lines':       entries[start:end],
                'total':       total,
                'today_total': len(load_logg_entries(False)),
                'page':        page,
                'per_page':    per_page,
                'pages':       (total + per_page - 1) // per_page,
                'show_all':    all_,
            })
            return

        if parsed.path == '/api/statistikk':
            self.send_json(load_statistikk())
            return

        if parsed.path == '/api/events24h':
            qs2  = parse_qs(parsed.query)
            all_ = qs2.get('all', ['0'])[0] == '1'
            self.send_json(load_events_24h(all_))
            return

        if parsed.path.startswith('/api/frigate_snapshot/'):
            event_id = os.path.basename(parsed.path)
            try:
                url = f'http://localhost:5000/api/events/{event_id}/snapshot.jpg?crop=1'
                with urllib.request.urlopen(url, timeout=5) as r:
                    data = r.read()
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(404)
                self.end_headers()
            return

        if parsed.path == '/api/ukjente':
            qs2  = parse_qs(parsed.query)
            all_ = qs2.get('all', ['0'])[0] == '1'
            self.send_json(load_ukjente(all_))
            return

        if parsed.path == '/api/ukjente/slett':
            qs2 = parse_qs(parsed.query)
            uid = qs2.get('id', [None])[0]
            if uid:
                try:
                    conn = sqlite3.connect(UKJENTE_DB)
                    row  = conn.execute('SELECT snapshot FROM ukjente WHERE id=?', (uid,)).fetchone()
                    if row and row[0]:
                        try: os.remove(row[0])
                        except Exception: pass
                    conn.execute('DELETE FROM ukjente WHERE id=?', (uid,))
                    conn.commit(); conn.close()
                    self.send_json({'ok': True})
                except Exception as e:
                    self.send_json({'ok': False, 'error': str(e)})
            else:
                self.send_json({'ok': False})
            return

        if parsed.path.startswith('/snapshot/'):
            filename = os.path.basename(parsed.path[10:])
            filepath = os.path.join(UKJENTE_SNAPSHOTS, filename)
            try:
                with open(filepath, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                self.wfile.write(data)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
            return

        if parsed.path == '/api/gpt/test':
            try:
                s     = load_settings()['lpr']
                key   = s.get('openai_api_key', '')
                model = s.get('gpt_model', 'gpt-4o')
                if not key:
                    self.send_json({'ok': False, 'error': 'Ingen API-nøkkel konfigurert'})
                    return
                import requests as _req
                r = _req.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 5,
                          "messages": [{"role": "user", "content": "Reply with OK"}]},
                    timeout=10
                )
                if r.status_code == 200:
                    self.send_json({'ok': True, 'model': model,
                                    'response': r.json()['choices'][0]['message']['content'].strip()})
                else:
                    err = r.json().get('error', {}).get('message', f'HTTP {r.status_code}')
                    self.send_json({'ok': False, 'error': err})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})
            return

        if parsed.path == '/api/camera/test':
            qs2  = parse_qs(parsed.query)
            ip   = qs2.get('ip', [''])[0]
            user = qs2.get('user', [''])[0]
            pwd  = qs2.get('pass', [''])[0]
            path_rtsp = qs2.get('path', ['/Streaming/Channels/101'])[0]
            if not path_rtsp.startswith('/'):
                path_rtsp = '/' + path_rtsp
            url = f"rtsp://{user}:{pwd}@{ip}:554{path_rtsp}"
            try:
                result = subprocess.run(
                    ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', url],
                    capture_output=True, text=True, timeout=10
                )
                data    = json.loads(result.stdout)
                video   = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
                if video:
                    fps_str = video.get('r_frame_rate', '25/1')
                    try:
                        num, den = map(int, fps_str.split('/'))
                        fps = round(num / den, 1) if den else 25
                    except Exception:
                        fps = 25
                    self.send_json({'ok': True, 'codec': video.get('codec_name', '?'),
                                    'width': video.get('width', 0), 'height': video.get('height', 0), 'fps': fps})
                else:
                    self.send_json({'ok': False, 'error': 'Ingen videostrøm funnet'})
            except subprocess.TimeoutExpired:
                self.send_json({'ok': False, 'error': 'Tidsavbrutt (10s)'})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})
            return

        if parsed.path == '/api/cameras':
            try:
                with open(SETTINGS_FILE) as f:
                    self.send_json(json.load(f).get('cameras', []))
            except Exception:
                self.send_json([])
            return

        if parsed.path == '/api/docs':
            try:
                s = load_settings()
                with open(SETTINGS_FILE) as _f:
                    cameras = json.load(_f).get('cameras', [])
            except Exception:
                cameras = []
            services = {}
            for svc in ['lpr-bridge', 'lpr-web', 'ludvig-bridge', 'weather-bridge', 'borte-bridge']:
                try:
                    active = subprocess.run(['systemctl', 'is-active', svc],
                                            capture_output=True, text=True).stdout.strip()
                    show = subprocess.run(
                        ['systemctl', 'show', svc, '--property=ExecStart,Description,ActiveEnterTimestamp'],
                        capture_output=True, text=True).stdout.strip()
                    props = {}
                    for line in show.splitlines():
                        k, _, v = line.partition('=')
                        props[k] = v
                    exec_start = ''
                    raw = props.get('ExecStart', '')
                    import re as _re
                    m = _re.search(r'argv\[\]=([^;]+)', raw)
                    if m:
                        exec_start = m.group(1).strip()
                    services[svc] = {
                        'status':      active,
                        'description': props.get('Description', ''),
                        'exec':        exec_start,
                        'started':     props.get('ActiveEnterTimestamp', '').replace('n/a', ''),
                    }
                except Exception:
                    services[svc] = {'status': 'unknown', 'description': '', 'exec': '', 'started': ''}
            self.send_json({
                'system':   s.get('system', {}),
                'lpr':      s.get('lpr', {}),
                'ludvig':   s.get('ludvig', {}),
                'web':      s.get('web', {}),
                'cameras':  cameras,
                'services': services,
            })
            return

        if parsed.path == '/api/frigate_config':
            try:
                with urllib.request.urlopen('http://127.0.0.1:5000/api/config', timeout=5) as r:
                    fc = json.loads(r.read())
                result = {}
                for name, cam in fc.get('cameras', {}).items():
                    detect = cam.get('detect', {})
                    objects = cam.get('objects', {}).get('track', [])
                    inputs = cam.get('ffmpeg', {}).get('inputs', [])
                    roles = []
                    for inp in inputs:
                        roles.extend(inp.get('roles', []))
                    result[name] = {
                        'width':   detect.get('width'),
                        'height':  detect.get('height'),
                        'fps':     detect.get('fps'),
                        'objects': objects,
                        'record':  'record' in roles,
                        'detect':  detect.get('enabled', True),
                    }
                self.send_json(result)
            except Exception as e:
                self.send_json({})
            return

        if parsed.path == '/api/settings':
            s = load_settings()
            try:
                with open(SETTINGS_FILE) as _f:
                    s['cameras'] = json.load(_f).get('cameras', [])
            except Exception:
                s['cameras'] = []
            self.send_json(s)
            return

        if parsed.path == '/api/tts/test':
            try:
                import requests as _req
                s = load_settings()
                tts = s.get('dashboard', {}).get('tts', {})
                ip   = tts.get('loxone_ip', '192.168.1.100')
                user = tts.get('loxone_user', '')
                pwd  = tts.get('loxone_pass', '')
                zones = []
                if tts.get('gang', False): zones.append(tts.get('gang_input', 'TTS LPR Gang'))
                if tts.get('stue', False): zones.append(tts.get('stue_input', 'TTS LPR Stue'))
                if not zones: zones = [tts.get('gang_input', 'TTS LPR Gang')]
                for zone in zones:
                    from urllib.parse import quote as _q
                    url = f"http://{user}:{pwd}@{ip}/dev/sps/io/{_q(zone)}/Test%20fra%20dashboard"
                    _req.get(url, timeout=5)
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})
            return

        if parsed.path == '/api/borte':
            try:
                with open('/opt/homeserver/borte_state.json') as f:
                    self.send_json(json.load(f))
            except Exception:
                self.send_json({})
            return

        qs       = parse_qs(parsed.query)
        show_all = qs.get('all', ['0'])[0] == '1'
        skilt    = load_skilt()
        lines    = load_all_lines()
        lines    = lines[-load_settings()['web'].get('max_log_lines', MAX_LINES):]

        log_rows     = ""
        current_date = None
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            parts = line.split(' ', maxsplit=2)
            dato  = html.escape(parts[0]) if len(parts) > 0 else ""
            tid   = html.escape(parts[1]) if len(parts) > 1 else ""
            plate = html.escape(parts[2].strip()) if len(parts) > 2 else ""
            if show_all and dato != current_date:
                current_date = dato
                log_rows += f'<tr class="date-sep"><td colspan="5">📅 {dato}</td></tr>'
            eier = skilt.get(plate, "")
            if eier:
                eier_html = f'<span class="kjent">{html.escape(eier)}</span>'
            else:
                eier_html = (
                    f'<form method="POST" class="inline">'
                    f'<input type="hidden" name="action" value="add">'
                    f'<input type="hidden" name="plate" value="{plate}">'
                    f'<input type="text" name="name" placeholder="Navn..." required>'
                    f'<button type="submit">+ Legg til</button>'
                    f'</form>'
                )
            log_rows += (
                f"<tr><td>{dato}</td><td>{tid}</td>"
                f"<td><b>{plate}</b></td><td>{eier_html}</td>"
                f'<td><button class="del" onclick="slettLoggRad(this, \'{dato} {tid} {plate}\')">✕</button></td></tr>'
            )

        kjente_rows = (
            '<tr class="add-row"><td colspan="3">'
            '<form method="POST" class="inline" style="display:flex;gap:8px;align-items:center;">'
            '<input type="hidden" name="action" value="add">'
            '<input type="text" name="plate" placeholder="AB12345" required '
            'pattern="[A-Za-z]{2}[0-9]{5}" style="text-transform:uppercase;width:110px;">'
            '<input type="text" name="name" placeholder="Eier / kallenavn" required style="flex:1;">'
            '<button type="submit">+ Legg til ny bil</button>'
            '</form></td></tr>'
        )
        for plate, name in sorted(skilt.items(), key=lambda x: x[1].lower()):
            ep = html.escape(plate)
            en = html.escape(name)
            kjente_rows += (
                f'<tr><td><b>{ep}</b></td>'
                f'<td><form method="POST" class="inline">'
                f'<input type="hidden" name="action" value="edit">'
                f'<input type="hidden" name="plate" value="{ep}">'
                f'<input type="text" name="name" value="{en}" required>'
                f'<button type="submit">Lagre</button>'
                f'</form></td>'
                f'<td><form method="POST" class="inline" '
                f'onsubmit="return confirm(\'Slette {ep} ({en})?\');">'
                f'<input type="hidden" name="action" value="delete">'
                f'<input type="hidden" name="plate" value="{ep}">'
                f'<button type="submit" class="del">Slett</button>'
                f'</form></td></tr>'
            )

        stats    = get_system_stats()
        logg_status = "Oppdateres hvert 30. sekund"
        logg_label  = f"Logg ({len(lines)} – historikk)" if show_all else f"Logg ({len(lines)})"
        ingen_logg  = '<tr><td colspan="5">Ingen registreringer ennå</td></tr>'

        page = load_template({
            '__SYSTEM_NAME__': load_settings()['system'].get('name', 'Villalarsnes'),
            '__FRIGATE_URL__': load_settings()['system'].get('frigate_url', 'https://villaserver:8971'),
            '__PORTAINER_URL__': load_settings()['system'].get('portainer_url', 'http://villaserver:9000'),
            '__PIHOLE_URL__': load_settings()['system'].get('pihole_url', 'http://villaserver/admin'),
            '__LOGG_LABEL__':  logg_label,
            '__SKILT_COUNT__': str(len(skilt)),
            '__STAT_LOAD__':   stats['load'],
            '__STAT_RAM__':    stats['ram'],
            '__STAT_DISK__':   stats['disk'],
            '__RAM_PCT__':     str(stats['ram_pct']),
            '__DISK_PCT__':    str(stats['disk_pct']),
            '__LOGG_STATUS__': logg_status,
            '__LOG_ROWS__':    '',
            '__KJENTE_ROWS__': kjente_rows,
        })
        self.send_html(page)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(length).decode() if length else '{}'
        try:
            post_params = json.loads(raw_body)
        except Exception:
            post_params = {}

        if self.path == '/api/restart/all':
            import threading as _th
            def do_restart():
                import time as _t, subprocess as _sp
                _t.sleep(0.5)
                for svc in ['lpr-bridge', 'ludvig-bridge', 'weather-bridge', 'borte-bridge']:
                    restart_service(svc)
                _sp.run(['docker', 'restart', 'frigate'], timeout=60)
                restart_service('lpr-web')
            _th.Thread(target=do_restart, daemon=True).start()
            self.send_json({'ok': True, 'message': 'Restarter alle tjenester...'})
            return

        if self.path == '/api/tts/test':
            try:
                import requests as _req
                s = load_settings()
                tts = s.get('dashboard', {}).get('tts', {})
                ip   = tts.get('loxone_ip', '192.168.1.100')
                user = tts.get('loxone_user', '')
                pwd  = tts.get('loxone_pass', '')
                zones = []
                if tts.get('gang', False): zones.append(tts.get('gang_input', 'TTS LPR Gang'))
                if tts.get('stue', False): zones.append(tts.get('stue_input', 'TTS LPR Stue'))
                if not zones: zones = [tts.get('gang_input', 'TTS LPR Gang')]
                for zone in zones:
                    from urllib.parse import quote as _q
                    url = f"http://{user}:{pwd}@{ip}/dev/sps/io/{_q(zone)}/Test%20fra%20dashboard"
                    _req.get(url, timeout=5)
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})
            return

        if self.path == '/api/settings/dashboard/tts':
            try:
                s = load_settings()
                existing = s.get('dashboard', {}).get('tts', {})
                # Bare oppdater user-felt, bevar system-felt
                allowed = {'enabled', 'gang', 'stue', 'volume'}
                filtered = {k: v for k, v in post_params.items() if k in allowed}
                s.setdefault('dashboard', {})['tts'] = {**existing, **filtered}
                save_settings_file(s)
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})
            return

        if self.path == '/api/cameras':
            try:
                cameras = json.loads(raw_body)
                s = load_settings()
                old_lpr = {c['name']: c.get('lpr', False) for c in s.get('cameras', [])}
                new_lpr = {c['name']: c.get('lpr', False) for c in cameras}
                lpr_changed = old_lpr != new_lpr
                s['cameras'] = cameras
                save_settings_file(s)
                restarted = []
                if lpr_changed:
                    sync_frigate_snapshots(cameras)
                    try:
                        r = subprocess.run(['docker', 'restart', 'frigate'],
                                           capture_output=True, text=True, timeout=60)
                        if r.returncode == 0:
                            restarted.append('frigate')
                        else:
                            log.warning(f"docker restart frigate feilet: {r.stderr}")
                    except subprocess.TimeoutExpired:
                        log.warning("docker restart frigate tidsavbrutt")
                    except Exception as e:
                        log.warning(f"docker restart frigate exception: {e}")
                    restart_service('lpr-bridge')
                    restarted.append('lpr-bridge')
                self.send_json({'ok': True, 'restarted': restarted})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})
            return

        if self.path == '/api/settings':
            try:
                data   = json.loads(raw_body)
                current = load_settings()
                lpr_changed    = data.get('lpr')    != current.get('lpr')
                ludvig_changed = data.get('ludvig') != current.get('ludvig')
                # Bevar cameras-seksjonen
                try:
                    with open(SETTINGS_FILE) as _f:
                        _existing = json.load(_f)
                    if 'cameras' in _existing and 'cameras' not in data:
                        data['cameras'] = _existing['cameras']
                except Exception:
                    pass
                save_settings_file(data)
                restarted = []
                if lpr_changed:
                    restart_service('lpr-bridge')
                    restarted.append('lpr-bridge')
                if ludvig_changed:
                    restart_service('ludvig-bridge')
                    restarted.append('ludvig-bridge')
                self.send_json({'ok': True, 'restarted': restarted})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})
            return

        if self.path == '/api/logg/slett':
            try:
                params = parse_qs(raw_body)
                linje  = params.get('linje', [''])[0]
                if linje:
                    parts = linje.strip().split(' ', maxsplit=2)
                    if len(parts) >= 3:
                        tidspunkt = f"{parts[0]} {parts[1]}"
                        plate     = parts[2].strip().split(' ')[0]
                        conn = sqlite3.connect(LOGG_DB)
                        conn.execute("DELETE FROM logg WHERE tidspunkt = ? AND plate = ?",
                                     (tidspunkt, plate))
                        conn.commit()
                        conn.close()
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)})
            return

        if self.path == '/api/borte/reset':
            try:
                with open('/opt/homeserver/borte_state.json') as f:
                    data = json.load(f)
                data['last_run_date']      = None
                data['last_run_confirmed'] = None
                with open('/opt/homeserver/borte_state.json', 'w') as f:
                    json.dump(data, f, indent=2)
                self.send_json({'ok': True})
            except Exception:
                self.send_json({'ok': False})
            return

        if self.path == '/api/borte/toggle':
            try:
                with open('/opt/homeserver/borte_state.json') as f:
                    data = json.load(f)
                data['automatikk'] = not data.get('automatikk', True)
                with open('/opt/homeserver/borte_state.json', 'w') as f:
                    json.dump(data, f, indent=2)
                self.send_json({'automatikk': data['automatikk']})
            except Exception:
                self.send_json({})
            return

        try:
            params = parse_qs(raw_body)
            action = params.get('action', [''])[0]
            plate  = params.get('plate', [''])[0].strip().upper()
            name   = params.get('name',  [''])[0].strip()
            skilt  = load_skilt()
            if action == 'add' and plate and name:
                skilt[plate] = name
                save_skilt(skilt)
            elif action == 'edit' and plate and name:
                skilt[plate] = name
                save_skilt(skilt)
            elif action == 'delete' and plate:
                skilt.pop(plate, None)
                save_skilt(skilt)
        except Exception:
            pass

        referer = self.headers.get('Referer', '')
        tab = ''
        if referer:
            qs = parse_qs(urlparse(referer).query)
            if qs.get('tab'):
                tab = '?tab=' + qs['tab'][0]
        self.send_response(303)
        self.send_header('Location', '/' + tab)
        self.end_headers()


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
