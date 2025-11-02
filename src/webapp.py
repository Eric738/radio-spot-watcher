#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radio Spot Watcher v2.91 (2025-10-31) — Thème clair
Nouveautés v2.91 :
  - DXCC auto : création dxcc_latest.json local + tentative de mise à jour en ligne à chaque démarrage
  - Matching DXCC robuste (préfixe le plus long, nettoyage suffixes /P /M /MM /QRP /DX /AM /MAR)
  - Logs explicites : [DXCC] ... entrées chargées / mises à jour
Conserve 2.86 : carte, watchlist, filtres bande/mode, charts canvas, RSS, export CSV, palettes.
"""

import os, json, csv, re, socket, signal, logging, threading, time
from datetime import datetime, timezone
from collections import deque, defaultdict
from typing import Dict, List, Optional, Tuple

import requests
import feedparser
from flask import Flask, jsonify, Response, render_template_string

# =========================
# Config
# =========================
VERSION = "v2.91 (2025-10-31)"
HTTP_PORT = int(os.environ.get("PORT", 8000))

# Cluster (primaire + fallback)
CLUSTER_PRIMARY = (os.environ.get("CLUSTER_HOST", "dxfun.com"), int(os.environ.get("CLUSTER_PORT", 8000)))
CLUSTER_FALLBACK = (os.environ.get("CLUSTER_FALLBACK_HOST", "f5len.org"), int(os.environ.get("CLUSTER_FALLBACK_PORT", 8000)))
CLUSTER_CALLSIGN = os.environ.get("CLUSTER_CALLSIGN", "F1ABC")

# Données / limites
MAX_SPOTS = int(os.environ.get("MAX_SPOTS", 200))
MAX_MAP_SPOTS = int(os.environ.get("MAX_MAP_SPOTS", 30))
SPOTS_FILE = os.environ.get("SPOTS_FILE", "spots.json")
DXCC_FILE  = os.environ.get("DXCC_FILE",  "dxcc.json")
LOG_FILE   = os.environ.get("LOG_FILE",   "rspot.log")

# DXCC : URL (modifiable)
DXCC_REMOTE_URL = os.environ.get(
    #"DXCC_REMOTE_URL",
    ""
)

# RSS
RSS_FEEDS = [
    "https://www.dx-world.net/feed/",
    "https://clublog.freshdesk.com/support/discussions/topics/3000175080.rss"
]
RSS_UPDATE_INTERVAL = 300  # sec

# =========================
# Logging
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("radio-spot-watcher")
try:
    from logging.handlers import RotatingFileHandler
    rh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
    rh.setLevel(logging.INFO)
    rh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(rh)
except Exception as e:
    logger.warning(f"RotatingFileHandler unavailable: {e}")

# =========================
# App core
# =========================
class RadioSpotWatcher:
    def __init__(self):
        self.app = Flask(__name__)
        self.spots = deque(maxlen=MAX_SPOTS)

        self.current_cluster = CLUSTER_PRIMARY
        self.cluster_socket: Optional[socket.socket] = None
        self.cluster_connected = False

        self.dxcc_map: Dict[str, Dict] = {}
        self.sorted_prefixes: List[str] = []
        self.dxcc_update_date = "unknown"

        self.rss_data: List[Dict] = []
        self.most_wanted = [
            {"name": "Bouvet Island",           "flag": "🇧🇻", "prefix": "3Y0"},
            {"name": "South Sandwich Islands",  "flag": "🇬🇸", "prefix": "VP8"},
            {"name": "Amsterdam & St Paul",     "flag": "🇫🇷", "prefix": "FT5"},
            {"name": "Baker Island",            "flag": "🇺🇸", "prefix": "KH1"},
            {"name": "North Korea",             "flag": "🇰🇵", "prefix": "HL9"},
            {"name": "Clipperton Island",       "flag": "🇫🇷", "prefix": "FO0"},
            {"name": "Heard Island",            "flag": "🇦🇺", "prefix": "VK0"}
        ]

        self.lock = threading.RLock()
        self.stop_event = threading.Event()

        # Charge DXCC (création locale + tentative de mise à jour en ligne)
        self.ensure_local_dxcc_then_update()
        self.sorted_prefixes = sorted(self.dxcc_map.keys(), key=len, reverse=True)

        # Spots persistés
        self.load_spots_from_file()

        # Routes + workers
        self.setup_routes()
        self.threads: List[threading.Thread] = []

    # ------------- DXCC -------------
    @staticmethod
    def _fallback_dxcc_min() -> Dict[str, Dict]:
        # Minimal (10), lat/lon approximatifs
        return {
            "F":  {"country": "France",          "lat": 46.0,  "lon":   2.0,  "continent": "EU"},
            "EA": {"country": "Spain",           "lat": 40.0,  "lon":  -4.0,  "continent": "EU"},
            "I":  {"country": "Italy",           "lat": 42.5,  "lon":  12.5,  "continent": "EU"},
            "DL": {"country": "Germany",         "lat": 51.0,  "lon":   9.0,  "continent": "EU"},
            "G":  {"country": "England",         "lat": 52.0,  "lon":   0.0,  "continent": "EU"},
            "JA": {"country": "Japan",           "lat": 36.0,  "lon": 138.0,  "continent": "AS"},
            "VK": {"country": "Australia",       "lat":-25.0,  "lon": 135.0,  "continent": "OC"},
            "K":  {"country": "United States",   "lat": 39.0,  "lon": -98.0,  "continent": "NA"},
            "PY": {"country": "Brazil",          "lat":-10.0,  "lon": -55.0,  "continent": "SA"},
            "ZS": {"country": "South Africa",    "lat":-29.0,  "lon":  24.0,  "continent": "AF"},
        }

    def ensure_local_dxcc_then_update(self):
        # 1) Charge local ou crée fallback
        local_loaded = False
        if os.path.exists(DXCC_FILE):
            try:
                with open(DXCC_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.dxcc_map = self._coerce_any_dxcc_format(data)
                logger.info(f"[DXCC] Fichier local chargé ({len(self.dxcc_map)} entrées)")
                local_loaded = True
            except Exception as e:
                logger.warning(f"[DXCC] Local invalide, fallback : {e}")

        if not local_loaded:
            self.dxcc_map = self._fallback_dxcc_min()
            with open(DXCC_FILE, "w", encoding="utf-8") as f:
                json.dump(self.dxcc_map, f, ensure_ascii=False, indent=2)
            logger.info(f"[DXCC] Création locale par défaut ({len(self.dxcc_map)} entrées)")

        # 2) Tente MAJ en ligne (non bloquant si échec)
        try:
            logger.info(f"[DXCC] Tentative de mise à jour en ligne: {DXCC_REMOTE_URL}")
            r = requests.get(DXCC_REMOTE_URL, timeout=15)
            r.raise_for_status()
            data = r.json()
            updated = self._coerce_any_dxcc_format(data)
            if len(updated) >= len(self.dxcc_map):  # garde seulement si mieux ou égal
                self.dxcc_map = updated
                with open(DXCC_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.dxcc_map, f, ensure_ascii=False, indent=2)
                self.dxcc_update_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                logger.info(f"[DXCC] Mise à jour réussie ({len(self.dxcc_map)} entrées)")
            else:
                logger.info(f"[DXCC] MAJ ignorée (trop petite : {len(updated)} < {len(self.dxcc_map)})")
        except Exception as e:
            logger.warning(f"[DXCC] MAJ en ligne échouée : {e}")

    def _coerce_any_dxcc_format(self, data) -> Dict[str, Dict]:
        """
        Accepte :
          - dict { "F": {"country":"France","lat":..,"lon":..,"continent":"EU"}, ... }
          - dict { "F":"France", ... }  (complétion sans lat/lon)
          - list [{"prefix":"F","country":"France","lat":..,"lon":..,"continent":"EU"}, ...]
        """
        out: Dict[str, Dict] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                pref = k.upper().strip()
                if isinstance(v, dict):
                    out[pref] = {
                        "country": v.get("country","") or str(v.get("name","")) or "",
                        "lat": float(v.get("lat", 0) or 0),
                        "lon": float(v.get("lon", 0) or 0),
                        "continent": v.get("continent","") or ""
                    }
                else:
                    out[pref] = {"country": str(v), "lat": 0.0, "lon": 0.0, "continent": ""}
        elif isinstance(data, list):
            for row in data:
                if not isinstance(row, dict): continue
                pref = str(row.get("prefix","")).upper().strip()
                if not pref: continue
                out[pref] = {
                    "country": row.get("country","") or "",
                    "lat": float(row.get("lat", 0) or 0),
                    "lon": float(row.get("lon", 0) or 0),
                    "continent": row.get("continent","") or ""
                }
        return out

    SUFFIX_TRASH = ("/P","/M","/MM","/QRP","/DX","/A","/AM","/MAR")
    HYPHEN_TRASH = ("-P","-M","-MM","-QRP","-DX")

    def _clean_call(self, callsign: str) -> str:
        c = (callsign or "").upper().strip()
        if not c: return ""
        for suf in self.SUFFIX_TRASH + self.HYPHEN_TRASH:
            if c.endswith(suf):
                c = c[:-len(suf)]
        if "/" in c:
            c = c.split("/")[0]  # garde la partie la plus à gauche (préfixe DX)
        return c

    def dxcc_lookup(self, callsign: str) -> Dict:
        if not self.dxcc_map:
            return {"country": "Unknown", "lat": 0, "lon": 0, "continent": "??"}
        raw = (callsign or "").upper()
        base = self._clean_call(raw)
        # match sur préfixe le plus long
        for pref in self.sorted_prefixes:
            if base.startswith(pref):
                return self.dxcc_map.get(pref, {"country":"Unknown","lat":0,"lon":0,"continent":"??"})
        # essai brut
        for pref in self.sorted_prefixes:
            if raw.startswith(pref):
                return self.dxcc_map.get(pref, {"country":"Unknown","lat":0,"lon":0,"continent":"??"})
        return {"country":"Unknown","lat":0,"lon":0,"continent":"??"}

    # ------------- Spots -------------
    DX_RE = re.compile(r'(?:DX (?:de|from)?\s*)([A-Z0-9/]+)[:\s]*\s*([0-9.]+)\s+([A-Z0-9/]+)\s*(.*?)\s*(\d{3,4}Z)?\s*(.*)', re.I)

    def _detect_mode_band(self, freq_str: str, comment: str = "") -> Tuple[str, str]:
        try:
            freq = float(freq_str)
        except Exception:
            return "UNK", "UNK"
        # band
        if 1800 <= freq <= 2000: band = "160m"
        elif 3500 <= freq <= 4000: band = "80m"
        elif 7000 <= freq <= 7300: band = "40m"
        elif 10100 <= freq <= 10150: band = "30m"
        elif 14000 <= freq <= 14350: band = "20m"
        elif 18068 <= freq <= 18168: band = "17m"
        elif 21000 <= freq <= 21450: band = "15m"
        elif 24890 <= freq <= 24990: band = "12m"
        elif 28000 <= freq <= 29700: band = "10m"
        elif 50000 <= freq <= 54000: band = "6m"
        elif 144000 <= freq <= 148000: band = "2m"
        elif 430000 <= freq <= 440000: band = "70cm"
        elif 10488000 <= freq <= 10492000: band = "QO-100"
        else: band = "UNK"
        up = (comment or "").upper()
        if "QO-100" in up or "QO100" in up: band = "QO-100"
        # mode
        if "FT8" in up: mode = "FT8"
        elif "FT4" in up: mode = "FT4"
        elif "CW" in up or "QCW" in up: mode = "CW"
        elif "SSB" in up or "USB" in up or "LSB" in up: mode = "SSB"
        elif any(x in up for x in ("RTTY","PSK","MFSK")): mode = "DIGI"
        else:
            if band in ("160m","80m","40m") and (freq % 1000) < 200: mode = "CW"
            elif band in ("20m","15m","10m") and (freq % 1000) < 200: mode = "CW"
            elif (freq % 1000 > 70) and (freq % 1000 < 80): mode = "FT8"
            else: mode = "SSB"
        return mode, band

    def parse_dx_line(self, line: str) -> Optional[Dict]:
        if not line or not (line.startswith("DX ") or line.startswith("DX de ") or line.startswith("DX from ")):
            return None
        m = self.DX_RE.match(line)
        if not m: return None
        spotter, freq, call = m.group(1) or "", m.group(2) or "", m.group(3) or ""
        comment_part, time_part, tail = m.group(4) or "", m.group(5) or "", m.group(6) or ""
        full_comment = (comment_part + " " + tail).strip()
        if not time_part:
            time_part = datetime.now(timezone.utc).strftime("%H%MZ")

        mode, band = self._detect_mode_band(freq, full_comment)
        d = self.dxcc_lookup(call)
        return {
            "utc": time_part,
            "freq": freq,
            "call": call,
            "mode": mode,
            "band": band,
            "dxcc": d.get("country",""),
            "grid": "",
            "spotter": spotter,
            "lat": d.get("lat",0),
            "lon": d.get("lon",0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "comment": full_comment
        }

    # ------------- Persist -------------
    def save_spots(self):
        try:
            with self.lock:
                data = list(self.spots)
            tmp = SPOTS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SPOTS_FILE)
        except Exception as e:
            logger.warning(f"save_spots error: {e}")

    def load_spots_from_file(self):
        try:
            if os.path.exists(SPOTS_FILE):
                with open(SPOTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    with self.lock:
                        self.spots = deque(data, maxlen=MAX_SPOTS)
                logger.info(f"[SPOTS] {len(self.spots)} spots chargés")
            else:
                logger.info("[SPOTS] Aucun fichier spots.json")
        except Exception as e:
            logger.warning(f"[SPOTS] Lecture échouée: {e}")
            with self.lock:
                self.spots = deque(maxlen=MAX_SPOTS)

    # ------------- Cluster -------------
    def connect_cluster(self):
        # ferme socket précédente
        try:
            if self.cluster_socket:
                try: self.cluster_socket.close()
                except: pass
        finally:
            self.cluster_socket = None

        host, port = self.current_cluster
        logger.info(f"[CLUSTER] Connexion {host}:{port}")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((host, port))
            try:
                s.send((CLUSTER_CALLSIGN + "\n").encode("utf-8"))
            except Exception:
                pass
            self.cluster_socket = s
            self.cluster_connected = True
            logger.info("[CLUSTER] Connecté")
        except Exception as e:
            logger.error(f"[CLUSTER] Échec: {e}")
            self.cluster_connected = False
            self.current_cluster = CLUSTER_FALLBACK if self.current_cluster == CLUSTER_PRIMARY else CLUSTER_PRIMARY

    def _cluster_reader(self):
        s = self.cluster_socket
        if not s: return
        buf = ""
        try:
            s.settimeout(5.0)
        except: pass

        while not self.stop_event.is_set() and self.cluster_connected and s:
            try:
                data = s.recv(4096)
                if not data:
                    logger.info("[CLUSTER] Fin de flux")
                    break
                text = data.decode("utf-8", errors="ignore")
                buf += text
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip("\r ").strip()
                    if not line: continue
                    spot = self.parse_dx_line(line)
                    if spot:
                        with self.lock:
                            self.spots.appendleft(spot)
                        self.save_spots()
            except socket.timeout:
                continue
            except Exception as e:
                logger.warning(f"[CLUSTER] read error: {e}")
                break

        self.cluster_connected = False
        try:
            if self.cluster_socket:
                try: self.cluster_socket.close()
                except: pass
        finally:
            self.cluster_socket = None

    def cluster_worker(self):
        backoff = 1
        while not self.stop_event.is_set():
            self.connect_cluster()
            if self.cluster_connected and self.cluster_socket:
                backoff = 1
                self._cluster_reader()
            else:
                time.sleep(backoff)
                backoff = min(300, backoff * 2)

    # ------------- RSS -------------
    def rss_worker(self):
        while not self.stop_event.is_set():
            entries = []
            for url in RSS_FEEDS:
                try:
                    feed = feedparser.parse(url)
                    for e in feed.entries[:8]:
                        summary = e.get("summary", "")
                        if len(summary) > 220: summary = summary[:220] + "…"
                        entries.append({
                            "title": e.get("title",""),
                            "link": e.get("link",""),
                            "published": e.get("published",""),
                            "summary": summary
                        })
                except Exception as fe:
                    logger.debug(f"[RSS] {url}: {fe}")
            with self.lock:
                self.rss_data = entries[:15]
            for _ in range(RSS_UPDATE_INTERVAL):
                if self.stop_event.wait(1): break

    # ------------- Routes -------------
    def setup_routes(self):
        @self.app.route("/")
        def index():
            return render_template_string(HTML, version=VERSION, max_map_spots=MAX_MAP_SPOTS)

        @self.app.route("/status.json")
        def status():
            with self.lock: total = len(self.spots)
            return jsonify({
                "cluster_connected": self.cluster_connected,
                "cluster_host": self.current_cluster[0],
                "version": VERSION,
                "dxcc_update": self.dxcc_update_date,
                "last_saved": datetime.now(timezone.utc).isoformat(),
                "total_spots": total
            })

        @self.app.route("/spots.json")
        def spots_json():
            with self.lock:
                return jsonify({"spots": list(self.spots), "map_spots": list(self.spots)[:MAX_MAP_SPOTS]})

        @self.app.route("/rss.json")
        def rss_json():
            with self.lock:
                return jsonify({"entries": self.rss_data})

        @self.app.route("/wanted.json")
        def wanted_json():
            return jsonify({"wanted": self.most_wanted})

        @self.app.route("/stats.json")
        def stats_json():
            with self.lock:
                L = list(self.spots)
            band_stats, mode_stats = defaultdict(int), defaultdict(int)
            for s in L:
                band_stats[s.get("band","UNK")] += 1
                mode_stats[s.get("mode","UNK")] += 1
            return jsonify({"bands": dict(band_stats), "modes": dict(mode_stats)})

        @self.app.route("/export.csv")
        def export_csv():
            with self.lock: L = list(self.spots)
            header = ["utc","freq","call","mode","band","dxcc","grid","spotter","lat","lon","timestamp","comment"]
            def gen():
                yield ",".join(header) + "\n"
                for s in L:
                    row = [str(s.get(h,"")).replace('"','""') for h in header]
                    yield '"' + '","'.join(row) + '"\n'
            resp = Response(gen(), mimetype="text/csv; charset=utf-8")
            resp.headers.set("Content-Disposition", "attachment", filename="spots.csv")
            return resp

    # ------------- Workers -------------
    def start_workers(self):
        for target, name in [
            (self.cluster_worker, "cluster"),
            (self.rss_worker,     "rss"),
            (self.persist_worker, "persist")
        ]:
            t = threading.Thread(target=target, daemon=True, name=name)
            t.start()

    def persist_worker(self):
        while not self.stop_event.is_set():
            try:
                self.save_spots()
            except Exception as e:
                logger.debug(f"persist: {e}")
            if self.stop_event.wait(60): break

    def run(self):
        def _sig(sig, frame):
            logger.info(f"Signal {sig}, arrêt…")
            threading.Thread(target=self._shutdown, daemon=True).start()
        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)

        self.start_workers()
        logger.info(f"Démarrage Radio Spot Watcher {VERSION} sur port {HTTP_PORT}")
        try:
            self.app.run(host="0.0.0.0", port=HTTP_PORT, debug=False, use_reloader=False)
        finally:
            self._shutdown()

    def _shutdown(self):
        self.stop_event.set()
        try:
            if self.cluster_socket:
                try: self.cluster_socket.shutdown(socket.SHUT_RDWR)
                except: pass
                try: self.cluster_socket.close()
                except: pass
        except: pass
        try: self.save_spots()
        except: pass
        logger.info("Arrêt OK")

# =========================
# UI (thème clair + palettes)
# =========================
HTML = r'''
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Radio Spot Watcher</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
<style>
:root{
  --bg:#ffffff; --page-bg:#f1f5f9; --text:#0f172a; --muted:#64748b;
  --accent:#3b82f6; --accent-strong:#2563eb; --divider:#e6e9ee;
  --card-shadow:0 1px 3px rgba(11,20,35,0.06);
  --table-row-hover:#f8fafc;
  --watch-bg: var(--accent);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--page-bg);color:var(--text);line-height:1.6}
.header{background:var(--bg);padding:1rem 1.25rem;border-bottom:1px solid var(--divider);display:flex;justify-content:space-between;align-items:center;box-shadow:var(--card-shadow)}
.title-block{display:flex;flex-direction:column}
.header h1{color:var(--accent);font-size:1.6rem;margin-bottom:0.1rem}
.version{font-size:0.85rem;color:var(--muted)}
.status{display:flex;align-items:center;gap:1rem}
.status-indicator{width:12px;height:12px;border-radius:50%;background:#ef4444}
.status-indicator.connected{background:#22c55e}
.main-container{display:grid;grid-template-columns:2fr 1fr;gap:1.25rem;padding:1.25rem;max-width:1400px;margin:0 auto}
.card{background:var(--bg);border-radius:8px;padding:1rem;box-shadow:var(--card-shadow);margin-bottom:1rem}
.card h2{color:var(--accent);margin-bottom:0.5rem;font-size:1.05rem;position:relative;padding-bottom:0.4rem}
.card h2::after{content:"";display:block;height:1px;background:var(--divider);margin-top:8px;width:100%;border-radius:1px}
#map{height:420px;border-radius:6px;margin-bottom:0.75rem}
.map-controls{display:flex;gap:0.5rem;margin-bottom:1rem}
.map-size-btn{padding:0.45rem 0.8rem;border:1px solid var(--divider);background:#fff;border-radius:5px;cursor:pointer;font-size:0.9rem}
.map-size-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.spots-table{max-height:480px;overflow-y:auto;border:1px solid var(--divider);border-radius:6px}
table{width:100%;border-collapse:collapse}
th{background:linear-gradient(180deg,#fbfdff,#f8fafc);padding:0.6rem;text-align:left;font-weight:700;border-bottom:2px solid var(--divider);position:sticky;top:0;z-index:2;font-size:0.9rem;color:var(--muted)}
td{padding:0.5rem 0.75rem;border-bottom:1px solid var(--divider);font-size:0.92rem}
tr:hover td{background:var(--table-row-hover)}
tr:nth-child(even) td{background:#fff}
tr.watchhit{background:var(--watch-bg)!important;color:#fff}
tr.watchhit .call-link{color:inherit!important;text-decoration:underline;font-weight:700}
.call-link{color:var(--accent);text-decoration:none;font-weight:600}
.call-link:hover{text-decoration:underline}
.watchlist-input{display:flex;gap:0.5rem;margin-bottom:0.75rem}
.watchlist-input input{flex:1;padding:0.45rem;border:1px solid var(--divider);border-radius:6px}
.btn{padding:0.45rem 0.75rem;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.9rem}
.btn:hover{background:var(--accent-strong)}
.watchlist-items{display:flex;flex-wrap:wrap;gap:0.5rem}
.watchlist-item{background:#f8fafc;padding:0.3rem 0.5rem;border-radius:6px;display:flex;align-items:center;gap:0.5rem;font-size:0.9rem;border:1px solid var(--divider)}
.remove-btn{cursor:pointer;color:#ef4444;font-weight:bold}
.rss-item{margin-bottom:1rem;padding-bottom:1rem;border-bottom:1px solid var(--divider)}
.rss-title{color:#f59e0b;font-weight:700;margin-bottom:0.25rem}
.rss-title a{color:inherit;text-decoration:none;font-weight:700}
.rss-summary{font-size:0.9rem;color:var(--muted)}
.wanted-item{display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;padding:0.5rem;background:#f8fafc;border-radius:6px;border:1px solid var(--divider)}
.filter-controls{display:flex;gap:0.75rem;align-items:center;flex-wrap:wrap}
.filter-controls select{padding:0.38rem 0.5rem;border-radius:6px;border:1px solid var(--divider);background:#fff}
.chart-container{margin-bottom:1rem}
.chart{border:1px solid var(--divider);border-radius:6px}
.footer{text-align:center;padding:1rem;color:var(--muted);font-size:0.9rem;border-top:1px solid var(--divider);background:var(--bg);margin-top:1rem}
.divider{height:1px;background:var(--divider);margin:12px 0;border-radius:1px;box-shadow:0 1px 0 rgba(255,255,255,0.6) inset}
.palette-select{display:flex;gap:0.5rem;align-items:center}
@media (max-width: 900px){
  .main-container{grid-template-columns:1fr;padding:1rem}
  .header{flex-direction:column;gap:0.5rem;align-items:flex-start}
  #map{height:300px}
}
.marker-cluster-small,.marker-cluster-medium,.marker-cluster-large{
  background:rgba(255,255,255,0.95);border:1px solid var(--divider);color:var(--text)
}
</style>
</head>
<body>
<header class="header">
  <div class="title-block">
    <h1>Radio Spot Watcher</h1>
    <div class="version">Version: {{ version }}</div>
  </div>
  <div style="display:flex; gap:1rem; align-items:center;">
    <div class="status">
      <span id="cluster-status">Cluster: </span>
      <div id="status-indicator" class="status-indicator"></div>
      <span id="dxcc-update">DXCC: Loading...</span>
    </div>
    <div class="palette-select" style="margin-left:0.8rem;">
      <label style="font-size:0.9rem;color:var(--muted);margin-right:6px;">Palette :</label>
      <select id="palette-choice" style="padding:0.3rem 0.5rem;border-radius:6px;border:1px solid var(--divider);">
        <option value="default">1. Default (clair)</option>
        <option value="ocean">2. Ocean</option>
        <option value="sunset">3. Sunset</option>
        <option value="contrast">4. High Contrast</option>
        <option value="extended">5. Extended</option>
        <option value="candy">6. Candy</option>
        <option value="forest">7. Forest</option>
        <option value="fire">8. Fire</option>
        <option value="violet">9. Violet</option>
        <option value="teal">10. Teal</option>
      </select>
    </div>
  </div>
</header>

<div class="divider"></div>

<div class="main-container">
  <div class="left-column">
    <div class="card">
      <h2>Carte des spots DX</h2>
      <div class="map-controls">
        <button class="map-size-btn" onclick="setMapSize('small')">Petite</button>
        <button class="map-size-btn active" onclick="setMapSize('medium')">Moyenne</button>
        <button class="map-size-btn" onclick="setMapSize('large')">Grande</button>
        <button class="btn" onclick="exportCSV()" style="margin-left:auto;">Export CSV</button>
      </div>
      <div id="map"></div>
    </div>

    <div class="card">
      <h2>Derniers spots DX</h2>
      <div class="spots-table">
        <table>
          <thead>
            <tr>
              <th>UTC</th><th>Freq</th><th>Call</th><th>Mode</th>
              <th>Bande</th><th>DXCC</th><th>Grid</th><th>Spotter</th>
            </tr>
          </thead>
          <tbody id="spots-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2>Watchlist</h2>
      <div id="watchlist-messages"></div>
      <div class="watchlist-input">
        <input type="text" id="watchlist-input" placeholder="Indicatif..." maxlength="10">
        <button class="btn" onclick="addToWatchlist()">➕</button>
      </div>
      <div class="watchlist-items" id="watchlist-items"></div>
    </div>
  </div>

  <div class="right-column">
    <div class="card">
      <h2>Horloges</h2>
      <div style="display:flex; gap:1rem; align-items:center;">
        <div style="min-width:150px;">
          <div style="font-size:0.85rem;color:var(--muted);">UTC</div>
          <div id="utc-time" style="font-family:monospace;font-weight:700;color:var(--accent);font-size:1.05rem;">--:--:--</div>
          <div id="utc-date" style="font-size:0.85rem;color:var(--muted);">---</div>
        </div>
        <div style="min-width:150px;">
          <div style="font-size:0.85rem;color:var(--muted);">Heure locale</div>
          <div id="local-time" style="font-family:monospace;font-weight:700;color:var(--accent-strong);font-size:1.05rem;">--:--:--</div>
          <div id="local-date" style="font-size:0.85rem;color:var(--muted);">---</div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Filtres</h2>
      <div class="filter-controls">
        <div>
          <label for="filter-band"><strong>Bande</strong></label><br>
          <select id="filter-band"></select>
        </div>
        <div>
          <label for="filter-mode"><strong>Mode</strong></label><br>
          <select id="filter-mode"></select>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Activité par bande</h2>
      <div class="chart-container"><canvas id="band-chart" class="chart" width="300" height="200"></canvas></div>
    </div>

    <div class="card">
      <h2>Activité par mode</h2>
      <div class="chart-container"><canvas id="mode-chart" class="chart" width="300" height="200"></canvas></div>
    </div>

    <div class="card">
      <h2>Flux RSS DX</h2>
      <div id="rss-content"></div>
    </div>

    <div class="card">
      <h2>Most Wanted DXCC</h2>
      <div id="most-wanted"></div>
    </div>
  </div>
</div>

<footer class="footer">Radio Spot Watcher {{ version }}</footer>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
let map, markersLayer;
let watchlist = JSON.parse(localStorage.getItem('watchlist') || '[]');
let mapSize = localStorage.getItem('mapSize') || 'medium';
const BAND_LIST = ['All','160m','80m','40m','30m','20m','17m','15m','12m','10m','6m','2m','70cm','QO-100','UNK'];
const MODE_LIST = ['All','FT8','FT4','CW','SSB','DIGI','UNK'];

const DEFAULT_BAND_COLORS = {
  '160m':'#ef4444','80m':'#f97316','40m':'#facc15','30m':'#84cc16','20m':'#3b82f6',
  '17m':'#6366f1','15m':'#8b5cf6','12m':'#06b6d4','10m':'#10b981','6m':'#ef7bbf',
  '2m':'#ef4444','70cm':'#fb7185','QO-100':'#a78bfa','UNK':'#94a3b8'
};
const DEFAULT_PALETTE = ['#60a5fa','#34d399','#fbbf24','#f87171','#a78bfa','#f472b6','#22d3ee','#84cc16','#fb7185','#f59e0b'];
const PALETTES = {
  'default': {'--accent':'#3b82f6','--accent-strong':'#2563eb', watchBg:'#3b82f6', bands: DEFAULT_BAND_COLORS, palette_colors: DEFAULT_PALETTE},
  'ocean':   {'--accent':'#0ea5a4','--accent-strong':'#059669', watchBg:'#0b6b65',
              bands:{'160m':'#064e3b','80m':'#0ea5a4','40m':'#0891b2','30m':'#06b6d4','20m':'#3b82f6','17m':'#60a5fa','15m':'#7c3aed','12m':'#38bdf8','10m':'#06b6d4','6m':'#06b6d4','2m':'#0b6b65','70cm':'#0284c7','QO-100':'#7dd3fc','UNK':'#94a3b8'},
              palette_colors:['#064e3b','#0ea5a4','#0891b2','#06b6d4','#3b82f6','#60a5fa','#7c3aed','#38bdf8','#06b6d4','#0b6b65']},
  'sunset':  {'--accent':'#f97316','--accent-strong':'#ef4444', watchBg:'#7c2d12',
              bands:{'160m':'#7c2d12','80m':'#ea580c','40m':'#f59e0b','30m':'#f97316','20m':'#ef4444','17m':'#f43f5e','15m':'#fb7185','12m':'#f97316','10m':'#f43f5e','6m':'#f472b6','2m':'#b45309','70cm':'#c2410c','QO-100':'#fb7185','UNK':'#94a3b8'},
              palette_colors:['#7c2d12','#ea580c','#f59e0b','#f97316','#ef4444','#f43f5e','#fb7185','#f97316','#f43f5e','#f472b6']},
  'contrast':{'--accent':'#111827','--accent-strong':'#0f172a', watchBg:'#0b1220',
              bands:{'160m':'#111827','80m':'#374151','40m':'#4b5563','30m':'#6b7280','20m':'#0f172a','17m':'#111827','15m':'#111827','12m':'#111827','10m':'#0f172a','6m':'#374151','2m':'#1f2937','70cm':'#374151','QO-100':'#111827','UNK':'#0f172a'},
              palette_colors:['#111827','#374151','#4b5563','#6b7280','#0f172a','#111827','#111827','#111827','#374151','#1f2937']},
  'extended':{'--accent':'#7c3aed','--accent-strong':'#6c5ce7', watchBg:'#7c3aed',
              bands:{'160m':'#7c3aed','80m':'#60a5fa','40m':'#34d399','30m':'#f59e0b','20m':'#fb7185','17m':'#f472b6','15m':'#a78bfa','12m':'#06b6d4','10m':'#10b981','6m':'#fd7b9c','2m':'#ef4444','70cm':'#00b894','QO-100':'#00cec9','UNK':'#94a3b8'},
              palette_colors:['#7c3aed','#60a5fa','#34d399','#f59e0b','#fb7185','#f472b6','#a78bfa','#06b6d4','#10b981','#00b894']},
  'candy':   {'--accent':'#ec4899','--accent-strong':'#db2777', watchBg:'#ec4899',
              bands:{'160m':'#ec4899','80m':'#f472b6','40m':'#fb7185','30m':'#f97316','20m':'#f59e0b','17m':'#22d3ee','15m':'#a78bfa','12m':'#60a5fa','10m':'#34d399','6m':'#10b981','2m':'#ef4444','70cm':'#f43f5e','QO-100':'#06b6d4','UNK':'#94a3b8'},
              palette_colors:['#ec4899','#f472b6','#fb7185','#f97316','#f59e0b','#22d3ee','#a78bfa','#60a5fa','#34d399','#10b981']},
  'forest':  {'--accent':'#16a34a','--accent-strong':'#15803d', watchBg:'#16a34a',
              bands:{'160m':'#166534','80m':'#16a34a','40m':'#22c55e','30m':'#84cc16','20m':'#65a30d','17m':'#059669','15m':'#0ea5a4','12m':'#10b981','10m':'#22c55e','6m':'#84cc16','2m':'#065f46','70cm':'#047857','QO-100':'#0ea5a4','UNK':'#94a3b8'},
              palette_colors:['#16a34a','#22c55e','#84cc16','#65a30d','#059669','#0ea5a4','#10b981','#22c55e','#84cc16','#065f46']},
  'fire':    {'--accent':'#ef4444','--accent-strong':'#dc2626', watchBg:'#ef4444',
              bands:{'160m':'#7f1d1d','80m':'#b91c1c','40m':'#ef4444','30m':'#f97316','20m':'#f59e0b','17m':'#fb7185','15m':'#f43f5e','12m':'#e11d48','10m':'#ea580c','6m':'#f87171','2m':'#b91c1c','70cm':'#dc2626','QO-100':'#f97316','UNK':'#94a3b8'},
              palette_colors:['#ef4444','#dc2626','#b91c1c','#f97316','#f59e0b','#fb7185','#f43f5e','#e11d48','#ea580c','#f87171']},
  'violet':  {'--accent':'#8b5cf6','--accent-strong':'#7c3aed', watchBg:'#8b5cf6',
              bands:{'160m':'#4c1d95','80m':'#6d28d9','40m':'#7c3aed','30m':'#8b5cf6','20m':'#a78bfa','17m':'#c4b5fd','15m':'#9333ea','12m':'#7c3aed','10m':'#6d28d9','6m':'#c084fc','2m':'#a78bfa','70cm':'#9333ea','QO-100':'#8b5cf6','UNK':'#94a3b8'},
              palette_colors:['#8b5cf6','#7c3aed','#a78bfa','#c084fc','#9333ea','#6d28d9','#c4b5fd','#7c3aed','#6d28d9','#4c1d95']},
  'teal':    {'--accent':'#14b8a6','--accent-strong':'#0d9488', watchBg:'#14b8a6',
              bands:{'160m':'#115e59','80m':'#0f766e','40m':'#14b8a6','30m':'#22d3ee','20m':'#06b6d4','17m':'#38bdf8','15m':'#60a5fa','12m':'#3b82f6','10m':'#0ea5a4','6m':'#10b981','2m':'#0f766e','70cm':'#0ea5b3','QO-100':'#22d3ee','UNK':'#94a3b8'},
              palette_colors:['#14b8a6','#0d9488','#0ea5a4','#22d3ee','#06b6d4','#38bdf8','#60a5fa','#3b82f6','#10b981','#0f766e']}
};

document.addEventListener('DOMContentLoaded', () => {
  initMap(); initFilters(); loadWatchlist(); initPalette(); initClocks();
  updateData(); setInterval(updateData, 5000);
  document.getElementById('watchlist-input').addEventListener('keypress', e => { if (e.key === 'Enter') addToWatchlist(); });
});

function initPalette(){
  const sel = document.getElementById('palette-choice');
  const saved = localStorage.getItem('uiPalette') || 'default';
  sel.value = saved; applyPalette(saved);
  sel.addEventListener('change', () => { localStorage.setItem('uiPalette', sel.value); applyPalette(sel.value); updateData(); });
}
function applyPalette(name){
  const p = PALETTES[name] || PALETTES['default'];
  for (const k of ['--accent','--accent-strong']){ if (p[k]) document.documentElement.style.setProperty(k, p[k]); }
  if (p.watchBg) document.documentElement.style.setProperty('--watch-bg', p.watchBg);
  window.BAND_COLORS = Object.assign({}, DEFAULT_BAND_COLORS, p.bands || {});
  window.PALETTE_COLORS = (p.palette_colors && p.palette_colors.length===10) ? p.palette_colors : DEFAULT_PALETTE;
}

function initMap(){
  map = L.map('map').setView([20,0], 2);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(map);
  markersLayer = L.markerClusterGroup({spiderfyOnMaxZoom:true,showCoverageOnHover:false,maxClusterRadius:40});
  map.addLayer(markersLayer);
  setMapSize(localStorage.getItem('mapSize') || 'medium');
}
function setMapSize(size){
  const el = document.getElementById('map');
  document.querySelectorAll('.map-size-btn').forEach(b=>b.classList.remove('active'));
  if (size==='small') el.style.height='300px';
  else if (size==='large') el.style.height='600px';
  else { el.style.height='420px'; size='medium'; }
  const btn = Array.from(document.querySelectorAll('.map-size-btn')).find(b=>b.getAttribute('onclick').includes(`'${size}'`));
  if (btn) btn.classList.add('active');
  localStorage.setItem('mapSize', size);
  setTimeout(()=>map.invalidateSize(),150);
}

function initFilters(){
  const bSel = document.getElementById('filter-band');
  const mSel = document.getElementById('filter-mode');
  const BL = ['All','160m','80m','40m','30m','20m','17m','15m','12m','10m','6m','2m','70cm','QO-100','UNK'];
  const ML = ['All','FT8','FT4','CW','SSB','DIGI','UNK'];
  BL.forEach(b=>{const o=document.createElement('option');o.value=b;o.textContent=b;bSel.appendChild(o);});
  ML.forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;mSel.appendChild(o);});
  bSel.value = localStorage.getItem('filterBand') || 'All';
  mSel.value = localStorage.getItem('filterMode') || 'All';
  bSel.addEventListener('change', ()=>{localStorage.setItem('filterBand', bSel.value); updateData();});
  mSel.addEventListener('change', ()=>{localStorage.setItem('filterMode', mSel.value); updateData();});
}

function updateData(){
  fetch('/status.json').then(r=>r.json()).then(d=>{
    const ind = document.querySelector('.status-indicator');
    const st  = document.getElementById('cluster-status');
    const dx  = document.getElementById('dxcc-update');
    ind.className = 'status-indicator ' + (d.cluster_connected ? 'connected' : '');
    st.textContent = `Cluster: ${d.cluster_host}`;
    dx.textContent = `DXCC: ${d.dxcc_update || '—'}`;
  }).catch(()=>{});

  fetch('/spots.json').then(r=>r.json()).then(d=>{
    const all = d.spots || [];
    const bf = localStorage.getItem('filterBand') || 'All';
    const mf = localStorage.getItem('filterMode') || 'All';
    const filtered = all.filter(s=>{
      const bOK = (bf==='All') || (s.band===bf);
      const mOK = (mf==='All') || (s.mode===mf);
      return bOK && mOK;
    });
    updateSpotsTable(filtered);
    updateMapMarkers(filtered.slice(0, {{ max_map_spots }} ));
    updateCharts(filtered);
  }).catch(()=>{});

  fetch('/rss.json').then(r=>r.json()).then(d=>updateRSS(d.entries||[])).catch(()=>{});
  fetch('/wanted.json').then(r=>r.json()).then(d=>updateWanted(d.wanted||[])).catch(()=>{});
}

function updateSpotsTable(spots){
  const tb = document.getElementById('spots-tbody'); tb.innerHTML='';
  const wl = JSON.parse(localStorage.getItem('watchlist') || '[]');
  spots.forEach(s=>{
    const tr = document.createElement('tr');
    if (wl.includes((s.call||'').toUpperCase())) tr.classList.add('watchhit');
    tr.innerHTML = `
      <td>${s.utc||''}</td>
      <td>${s.freq||''}</td>
      <td><a class="call-link" href="https://www.qrz.com/db/${s.call||''}" target="_blank">${s.call||''}</a></td>
      <td>${s.mode||''}</td>
      <td>${s.band||''}</td>
      <td>${s.dxcc||''}</td>
      <td>${s.grid||''}</td>
      <td>${s.spotter||''}</td>`;
    tb.appendChild(tr);
  });
}
function updateMapMarkers(spots){
  markersLayer.clearLayers();
  (spots||[]).forEach(s=>{
    if (s.lat && s.lon){
      const color = (window.BAND_COLORS||{})[s.band] || '#94a3b8';
      const m = L.circleMarker([s.lat, s.lon], {radius:6, fillColor:color, color:'#cbd5e1', weight:1.5, opacity:1, fillOpacity:0.95});
      m.bindPopup(`<strong>${s.call||''}</strong><br>${s.freq||''} kHz - ${s.mode||''}<br>${s.band||''} - ${s.dxcc||''}<br><small>${s.comment||''}</small>`);
      markersLayer.addLayer(m);
    }
  });
}
function updateRSS(entries){
  const c = document.getElementById('rss-content'); c.innerHTML='';
  entries.forEach(e=>{
    const d = document.createElement('div'); d.className='rss-item';
    d.innerHTML = `<div class="rss-title"><a href="${e.link}" target="_blank">${e.title}</a></div>
                   <div class="rss-summary">${e.summary||''}</div>`;
    c.appendChild(d);
  });
}
function updateWanted(list){
  const c = document.getElementById('most-wanted'); c.innerHTML='';
  list.forEach(x=>{
    const d = document.createElement('div'); d.className='wanted-item';
    d.innerHTML = `<span class="flag">${x.flag||''}</span><span>${x.name||''}</span>`;
    c.appendChild(d);
  });
}
function updateCharts(spots){
  const bc={}, mc={};
  (spots||[]).forEach(s=>{ bc[s.band||'UNK']=(bc[s.band||'UNK']||0)+1; mc[s.mode||'UNK']=(mc[s.mode||'UNK']||0)+1;});
  drawBar('band-chart', bc, window.BAND_COLORS||{});
  drawBar('mode-chart', mc, {'FT8':'#0ea5b3','FT4':'#06b6d4','CW':'#ef4444','SSB':'#3b82f6','DIGI':'#a78bfa','UNK':'#94a3b8'});
}
function drawBar(id, data, cmap){
  const cv = document.getElementById(id); if(!cv) return;
  const ctx = cv.getContext('2d'); ctx.clearRect(0,0,cv.width,cv.height);
  const entries = Object.entries(data||{}).sort((a,b)=>b[1]-a[1]); if(!entries.length) return;
  const maxV = Math.max(...entries.map(e=>e[1]));
  const barW = Math.max(20,(cv.width/entries.length)-10), maxH=cv.height-40;
  const pal=(window.PALETTE_COLORS&&PALETTE_COLORS.length===10)?PALETTE_COLORS:['#60a5fa','#34d399','#fbbf24','#f87171','#a78bfa','#f472b6','#22d3ee','#84cc16','#fb7185','#f59e0b'];
  entries.forEach((e,i)=>{
    const [lbl,val]=e; const h=(val/maxV)*maxH; const x=i*(barW+10)+10; const y=cv.height-h-20;
    const col = cmap[lbl] || cmap[(lbl||'').toUpperCase()] || pal[i%pal.length];
    ctx.fillStyle=col; ctx.fillRect(x,y,barW,h);
    ctx.fillStyle='#1e293b'; ctx.font='12px sans-serif'; ctx.textAlign='center';
    const txt=(lbl||''); ctx.fillText(txt.length>8?txt.slice(0,7)+'…':txt, x+barW/2, cv.height-5);
    ctx.fillStyle='#0f172a'; ctx.fillText(String(val), x+barW/2, y-6);
  });
}

// Watchlist
function addToWatchlist(){
  const input=document.getElementById('watchlist-input'); const call=(input.value||'').trim().toUpperCase(); if(!call) return;
  let list=JSON.parse(localStorage.getItem('watchlist')||'[]'); if(list.includes(call)) return;
  list.push(call); localStorage.setItem('watchlist', JSON.stringify(list)); input.value=''; loadWatchlist();
}
function removeFromWatchlist(call){
  let list=JSON.parse(localStorage.getItem('watchlist')||'[]'); list=list.filter(c=>c!==call); localStorage.setItem('watchlist', JSON.stringify(list)); loadWatchlist();
}
function loadWatchlist(){
  const c=document.getElementById('watchlist-items'); c.innerHTML='';
  (JSON.parse(localStorage.getItem('watchlist')||'[]')).forEach(call=>{
    const it=document.createElement('div'); it.className='watchlist-item';
    it.innerHTML=`<span>${call}</span><span class="remove-btn" onclick="removeFromWatchlist('${call}')">🗑️</span>`;
    c.appendChild(it);
  });
}

// Clocks
function initClocks(){
  const utcT=document.getElementById('utc-time'), utcD=document.getElementById('utc-date');
  const locT=document.getElementById('local-time'), locD=document.getElementById('local-date');
  const fmtLoc=d=>({time:d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit',second:'2-digit'}),date:d.toLocaleDateString(undefined,{weekday:'short',year:'numeric',month:'short',day:'numeric'})});
  const fmtUTC=d=>({time:new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false,timeZone:'UTC'}).format(d),date:new Intl.DateTimeFormat('en-GB',{weekday:'short',year:'numeric',month:'short',day:'numeric',timeZone:'UTC'}).format(d)});
  function tick(){const now=new Date(),L=fmtLoc(now),U=fmtUTC(now); if(utcT) utcT.textContent=U.time+' UTC'; if(utcD) utcD.textContent=U.date.replace(/,/g,'')+' (UTC)'; if(locT) locT.textContent=L.time; if(locD) locD.textContent=L.date.replace(/,/g,'');}
  tick(); setInterval(tick,1000);
}
</script>
</body>
</html>
'''

# =========================
# ============================================

# Nouvelle gestion DXCC via cty.csv (v2.91)

# ============================================

import csv, json, os

from pathlib import Path




def load_dxcc():
    import csv
    dxcc = {}
    csv_file = "/home/eric/radio-spot-watcher/src/cty.csv"
    print(f"[DXCC] Lecture du fichier CSV : {csv_file}")
    try:
        with open(csv_file, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                prefix = row.get("Prefix", "").strip()
                if not prefix or prefix in dxcc:
                    continue
                try:
                    dxcc[prefix] = {
                        "country": row.get("Entity", "Unknown").strip(),
                        "continent": row.get("Continent", "??").strip(),
                        "lat": float(row.get("Latitude", 0.0)),
                        "lon": float(row.get("Longitude", 0.0))
                    }
                except Exception as e:
                    print(f"[DXCC] Ligne ignorée : {prefix} ({e})")
        print(f"[DXCC] Fichier local chargé ({len(dxcc)} entrées)")
    except Exception as e:
        print(f"[DXCC] Erreur lors du chargement CSV : {e}")
        dxcc = {}
    return dxcc




# Chargement au démarrage

DXCC_DATA = load_dxcc()


# Entrée principale
# =========================

# --- Détection améliorée du pays à partir du préfixe ---
def detect_country(call, dxcc):
    """
    Retourne le pays correspondant à un indicatif d'après dxcc_latest.json.
    Recherche le préfixe le plus long correspondant (F5, F, etc.)
    """
    if not call or not dxcc:
        return "Unknown"

    call = call.upper().strip()
    best_match = None

    # Trie les préfixes du plus long au plus court pour trouver le plus précis
    for prefix in sorted(dxcc.keys(), key=len, reverse=True):
        if call.startswith(prefix):
            best_match = prefix
            break

    if best_match:
        return dxcc[best_match]["country"]
    else:
        # journalise les appels non trouvés
        try:
            with open("rspot.log", "a") as logf:
                logf.write(f"[WARN] Unknown prefix: {call}\\")
        except:
            pass
        return "Unknown"


if __name__ == "__main__":
    app = RadioSpotWatcher()
    app.run() 