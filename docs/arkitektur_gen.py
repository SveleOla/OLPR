#!/usr/bin/env python3
"""Genererer core/static/arkitektur.svg — OLPR systemoversikt i Deep Cyan."""
import html
import os

W, H = 1680, 1010

CYAN, TEAL = "#22d3ee", "#5eead4"
GREEN, AMBER = "#34d399", "#fbbf24"
TEXT, DIM, MUTED = "#dfe9f2", "#9db4c6", "#5e7991"

boxes = {}
def box(id, x, y, w, h, title, sub, accent=CYAN, em=False):
    boxes[id] = dict(x=x, y=y, w=w, h=h, title=title, sub=sub, accent=accent, em=em)

# ── Inndata (venstre) ──
box('cams',   60, 215, 280, 92, "Kameraer", "RTSP · H.264 · VAAPI|sub/main detect-stream", TEAL)
box('client', 60, 645, 280, 92, "Klienter", "nettleser · LAN|session-login (PBKDF2)", TEAL)

# ── Kjerne (midten) ──
box('frigate', 470, 215, 300, 100, "Frigate NVR", "LPR + AI · Coral/CPU|config autogenerert fra dashboard", CYAN, em=True)
box('mqtt',    470, 450, 300, 92, "Mosquitto", "MQTT-broker · Docker", CYAN, em=True)
box('web',     470, 645, 300, 100, "lpr_web", "Dashboard :8080|auth · logg · statistikk · kameraoppsett", TEAL, em=True)
box('install', 470, 815, 300, 70, "install.sh", "én kommando på ren Debian 13", MUTED)

box('lprb',    880, 300, 320, 92, "lpr_bridge", "LPR-events → MQTT|GPT-4o-fallback ved lav konfidens", CYAN)

# ── Ut / sky / lagring (høyre) ──
box('kunde', 1330, 215, 290, 100, "Kundesystem", "bom · port · parkering|abonnerer på MQTT-topics", GREEN)
box('cloud', 1330, 450, 290, 78, "GPT-4o (OpenAI)", "skiltverifisering · valgfritt", AMBER)
box('store', 1330, 590, 290, 92, "SQLite + snapshots", "logg.db · ukjente.db|snapshots · Frigate-opptak", TEAL)

def edge(id, side, dy=0):
    b = boxes[id]
    if side == 'r': return (b['x']+b['w'], b['y']+b['h']/2+dy)
    if side == 'l': return (b['x'],        b['y']+b['h']/2+dy)
    if side == 'b': return (b['x']+b['w']/2+dy, b['y']+b['h'])
    if side == 't': return (b['x']+b['w']/2+dy, b['y'])

arrows = [
    ('cams','r','frigate','l',TEAL,False,0,0),
    ('client','r','web','l',TEAL,False,0,20),
    ('frigate','b','mqtt','t',CYAN,False,0,0),
    ('frigate','r','lprb','l',CYAN,True,0,-26),       # snapshot via Frigate API
    ('mqtt','r','lprb','l',CYAN,False,-20,26),
    ('lprb','r','kunde','l',GREEN,False,-24,0),
    ('lprb','r','cloud','l',AMBER,True,8,0),
    ('lprb','r','store','l',TEAL,False,32,-22),
    ('store','l','web','r',TEAL,False,22,5),
]

def arrow_path(p1, p2):
    x1,y1 = p1; x2,y2 = p2
    mx = (x1+x2)/2
    return f"M {x1:.0f} {y1:.0f} C {mx:.0f} {y1:.0f}, {mx:.0f} {y2:.0f}, {x2:.0f} {y2:.0f}"

svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="\'JetBrains Mono\', \'DejaVu Sans Mono\', monospace">')
svg.append(f'''<defs>
  <linearGradient id="title" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#e9fbff"/><stop offset="1" stop-color="{TEAL}"/>
  </linearGradient>
  <radialGradient id="bgglow" cx="0.35" cy="0.1" r="0.9">
    <stop offset="0" stop-color="{CYAN}" stop-opacity="0.09"/>
    <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="boxfill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#10202c"/><stop offset="1" stop-color="#0b141d"/>
  </linearGradient>
  <marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0 1 L9 5 L0 9 Z" fill="context-stroke"/>
  </marker>
</defs>''')
svg.append(f'<rect width="{W}" height="{H}" fill="#060b11"/>')
svg.append(f'<rect width="{W}" height="{H}" fill="url(#bgglow)"/>')

# Tittel
svg.append(f'<text x="60" y="92" font-size="38" font-weight="bold" fill="url(#title)">OLPR — systemoversikt</text>')
svg.append(f'<text x="60" y="128" font-size="15" fill="{MUTED}">Automatisk skiltgjenkjenning · Frigate · Docker · Coral/CPU · offline-klar · én-kommandos installasjon</text>')

def panel(x, y, w, h, label):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#0b141d" fill-opacity="0.45" stroke="#6ec8eb" stroke-opacity="0.14"/>')
    svg.append(f'<text x="{x+22}" y="{y+34}" font-size="13" letter-spacing="2.5" fill="{MUTED}" font-weight="bold">{label}</text>')

panel(40, 165, 320, 612, "INNDATA")
panel(440, 165, 790, 760, "KJERNE — DOCKER + SYSTEMD")
panel(1300, 165, 350, 560, "UT · SKY · LAGRING")

for a in arrows:
    f_id, fs, t_id, ts, color, dashed, dy1, dy2 = a
    p = arrow_path(edge(f_id, fs, dy1), edge(t_id, ts, dy2))
    dash = ' stroke-dasharray="7 6"' if dashed else ''
    svg.append(f'<path d="{p}" fill="none" stroke="{color}" stroke-width="2.4" stroke-opacity="0.75" marker-end="url(#ah)"{dash}/>')

for id, b in boxes.items():
    glow = f' style="filter: drop-shadow(0 0 14px {b["accent"]}55)"' if b['em'] else ''
    sw = 2.4 if b['em'] else 1.6
    svg.append(f'<g{glow}>')
    svg.append(f'<rect x="{b["x"]}" y="{b["y"]}" width="{b["w"]}" height="{b["h"]}" rx="13" fill="url(#boxfill)" stroke="{b["accent"]}" stroke-opacity="0.85" stroke-width="{sw}"/>')
    subs = b['sub'].split('|')
    th = 30 + (0 if len(subs) > 1 else 8)
    svg.append(f'<text x="{b["x"]+20}" y="{b["y"]+th}" font-size="18" font-weight="bold" fill="{TEXT}">{html.escape(b["title"])}</text>')
    for i, s in enumerate(subs):
        svg.append(f'<text x="{b["x"]+20}" y="{b["y"]+th+22+i*17}" font-size="12.5" fill="{DIM}">{html.escape(s)}</text>')
    svg.append('</g>')

svg.append(f'<text x="60" y="{H-40}" font-size="13" fill="{MUTED}">MQTT-topics: {{system}}/{{kamera}}/resultat · {{system}}/{{kamera}}/skilt — dokumentasjon: docs/olpr.md</text>')
svg.append('</svg>')

out = os.path.join(os.path.dirname(__file__), '..', 'core', 'static', 'arkitektur.svg')
open(os.path.abspath(out), 'w').write('\n'.join(svg))
print("skrevet:", os.path.abspath(out))
