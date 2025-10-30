#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radio Spot Watcher v2.85
Date: 2025-10-28
Améliorations visuelles (palette configurable) + corrections et robustesse
Modifié : charts remontés, Most Wanted déplacé en bas, horloges ajoutées,
et palette étendue de 10 couleurs pour les charts.
"""

import os
import threading
import time
import json
import csv
import re
import socket
import logging
import signal
from datetime import datetime, timezone
from collections import deque, defaultdict
from typing import Dict, List, Optional, Tuple
import feedparser
import requests
from flask import Flask, render_template_string, jsonify, send_file, Response, make_response

# Configuration and environment overrides
VERSION = "v2.83 (2025-10-28)"
HTTP_PORT = int(os.environ.get('PORT', 8000))
CLUSTER_HOST = os.environ.get('CLUSTER_HOST', 'dxfun.com')
CLUSTER_PORT = int(os.environ.get('CLUSTER_PORT', 8000))
CLUSTER_PRIMARY = (CLUSTER_HOST, CLUSTER_PORT)
CLUSTER_FALLBACK = (os.environ.get('CLUSTER_FALLBACK_HOST', 'f5len.org'),
                    int(os.environ.get('CLUSTER_FALLBACK_PORT', 8000)))
CLUSTER_CALLSIGN = os.environ.get('CLUSTER_CALLSIGN', 'F1ABC')
MAX_SPOTS = int(os.environ.get('MAX_SPOTS', 200))
MAX_MAP_SPOTS = int(os.environ.get('MAX_MAP_SPOTS', 30))
RSS_UPDATE_INTERVAL = int(os.environ.get('RSS_UPDATE_INTERVAL', 300))
WANTED_UPDATE_INTERVAL = int(os.environ.get('WANTED_UPDATE_INTERVAL', 600))
SPOTS_FILE = os.environ.get('SPOTS_FILE', 'spots.json')
CTY_FILE = os.environ.get('CTY_FILE', 'cty.csv')
LOG_FILE = os.environ.get('LOG_FILE', 'rspot.log')

# Logging with rotating file handler
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
try:
    from logging.handlers import RotatingFileHandler
    rh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
    rh.setLevel(logging.INFO)
    rh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(rh)
except Exception as e:
    logger.warning(f"RotatingFileHandler not available: {e}")

class RadioSpotWatcher:
    def __init__(self):
        self.app = Flask(__name__)
        self.spots = deque(maxlen=MAX_SPOTS)
        self.current_cluster = CLUSTER_PRIMARY
        self.cluster_connected = False
        self.cluster_socket: Optional[socket.socket] = None
        self.rss_data = []
        self.most_wanted = []
        self.cty_data: Dict[str, Dict] = {}
        self.sorted_prefixes: List[str] = []
        self.dxcc_update_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        # Use RLock to allow reentrant locking if needed
        self.lock = threading.RLock()

        # Control for graceful shutdown
        self.stop_event = threading.Event()

        # Fallback minimal CTY
        self.fallback_cty = {
            'F': {'country': 'France', 'lat': 46.0, 'lon': 2.0, 'continent': 'EU'},
            'DL': {'country': 'Germany', 'lat': 51.0, 'lon': 9.0, 'continent': 'EU'},
            'I': {'country': 'Italy', 'lat': 42.0, 'lon': 12.0, 'continent': 'EU'},
            'EA': {'country': 'Spain', 'lat': 40.0, 'lon': -4.0, 'continent': 'EU'},
            'K': {'country': 'United States', 'lat': 39.0, 'lon': -98.0, 'continent': 'NA'},
            'VK': {'country': 'Australia', 'lat': -25.0, 'lon': 135.0, 'continent': 'OC'},
            'JA': {'country': 'Japan', 'lat': 36.0, 'lon': 138.0, 'continent': 'AS'},
        }

        # load resources
        self.load_cty_data()
        self.load_most_wanted()
        self.load_spots_from_file()

        # setup flask routes
        self.setup_routes()

    # -----------------------
    # CTY / DXCC helpers
    # -----------------------
    def load_cty_data(self):
        try:
            if os.path.exists(CTY_FILE):
                with open(CTY_FILE, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        prefix = row.get('prefix', '').upper().strip()
                        if prefix:
                            try:
                                lat = float(row.get('lat', 0) or 0)
                                lon = float(row.get('lon', 0) or 0)
                            except ValueError:
                                lat, lon = 0.0, 0.0
                            self.cty_data[prefix] = {
                                'country': row.get('country', '') or '',
                                'lat': lat,
                                'lon': lon,
                                'continent': row.get('continent', '') or ''
                            }
                logger.info(f"CTY data loaded: {len(self.cty_data)} entries from {CTY_FILE}")
            else:
                logger.warning(f"{CTY_FILE} not found, using fallback CTY data")
                self.cty_data = self.fallback_cty.copy()
        except Exception as e:
            logger.exception(f"Error loading CTY data: {e}")
            self.cty_data = self.fallback_cty.copy()

        # Build sorted prefixes for matching (longest-first)
        self.sorted_prefixes = sorted(self.cty_data.keys(), key=len, reverse=True)

    def load_most_wanted(self):
        # static list for now
        self.most_wanted = [
            {"name": "Bouvet Island", "flag": "🇧🇻", "prefix": "3Y0"},
            {"name": "South Sandwich Islands", "flag": "🇬🇸", "prefix": "VP8"},
            {"name": "Amsterdam & St Paul", "flag": "🇫🇷", "prefix": "FT5"},
            {"name": "Baker Island", "flag": "🇺🇸", "prefix": "KH1"},
            {"name": "North Korea", "flag": "🇰🇵", "prefix": "HL9"},
            {"name": "Clipperton Island", "flag": "🇫🇷", "prefix": "FO0"},
            {"name": "Heard Island", "flag": "🇦🇺", "prefix": "VK0"}
        ]

    def get_dxcc_info(self, callsign: str) -> Dict:
        call = (callsign or "").upper()
        # longest-prefix match using sorted_prefixes
        for pref in self.sorted_prefixes:
            if call.startswith(pref):
                return self.cty_data.get(pref, {'country': 'Unknown', 'lat': 0, 'lon': 0, 'continent': '??'})
        # fallback: search any prefix that matches start
        for pref, info in self.cty_data.items():
            if call.startswith(pref):
                return info
        return {'country': 'Unknown', 'lat': 0, 'lon': 0, 'continent': '??'}

    # -----------------------
    # Parsing / detection
    # -----------------------
    def detect_mode_and_band(self, freq_str: str, comment: str = "") -> Tuple[str, str]:
        try:
            freq = float(freq_str)
        except Exception:
            return "UNK", "UNK"

        # frequencies are expected in kHz
        # Add 2m, 70cm and QO-100 thresholds
        if 1800 <= freq <= 2000:
            band = "160m"
        elif 3500 <= freq <= 4000:
            band = "80m"
        elif 7000 <= freq <= 7300:
            band = "40m"
        elif 10100 <= freq <= 10150:
            band = "30m"
        elif 14000 <= freq <= 14350:
            band = "20m"
        elif 18068 <= freq <= 18168:
            band = "17m"
        elif 21000 <= freq <= 21450:
            band = "15m"
        elif 24890 <= freq <= 24990:
            band = "12m"
        elif 28000 <= freq <= 29700:
            band = "10m"
        elif 50000 <= freq <= 54000:
            band = "6m"
        # 2m: 144-148 MHz -> 144000-148000 kHz
        elif 144000 <= freq <= 148000:
            band = "2m"
        # 70cm: ~430-440 MHz -> 430000-440000 kHz
        elif 430000 <= freq <= 440000:
            band = "70cm"
        # QO-100: many spots mark QO-100 in comment; also detect approximate downlink ~10489000 kHz (10.489 GHz)
        elif 10488000 <= freq <= 10492000:
            band = "QO-100"
        else:
            # maybe QO-100 is indicated in comment
            band = "UNK"

        comment_upper = (comment or "").upper()
        if any(m in comment_upper for m in ("QO-100", "QO100", "QO 100")):
            band = "QO-100"

        if any(m in comment_upper for m in ("FT8", "FT-8")):
            mode = "FT8"
        elif any(m in comment_upper for m in ("FT4", "FT-4")):
            mode = "FT4"
        elif any(m in comment_upper for m in ("CW", "QCW")):
            mode = "CW"
        elif any(m in comment_upper for m in ("SSB", "USB", "LSB")):
            mode = "SSB"
        elif any(m in comment_upper for m in ("RTTY", "PSK", "MFSK")):
            mode = "DIGI"
        else:
            # heuristic fallback
            if band in ("160m", "80m", "40m") and (freq % 1000) < 200:
                mode = "CW"
            elif band in ("20m", "15m", "10m") and (freq % 1000) < 200:
                mode = "CW"
            elif "FT8" in comment_upper or (freq % 1000 > 70 and freq % 1000 < 80):
                mode = "FT8"
            else:
                mode = "SSB"
        return mode, band

    def parse_dx_spot(self, line: str) -> Optional[Dict]:
        try:
            if not line:
                return None
            # accept both "DX de " and "DX from " and some variations
            if not (line.startswith('DX de ') or line.startswith('DX from ') or line.startswith('DX ')):
                return None
            # generic pattern: spotter + spotted freq + call + ... time (e.g. 1234Z) optional comment
            # We'll try a robust regex but accept missing parts
            pattern = r'(?:DX (?:de|from)?\s*)([A-Z0-9/]+)[:\s]*\s*([0-9.]+)\s+([A-Z0-9/]+)\s*(.*?)\s*(\d{3,4}Z)?\s*(.*)'
            m = re.match(pattern, line, flags=re.IGNORECASE)
            if not m:
                return None
            spotter = m.group(1) or ''
            freq = m.group(2) or ''
            spotted = m.group(3) or ''
            # note: group(4) may contain an intermediate comment
            comment_part = m.group(4) or ''
            time_part = m.group(5) or datetime.now(timezone.utc).strftime('%H%MZ')
            tail_comment = m.group(6) or ''
            full_comment = (comment_part + ' ' + tail_comment).strip()

            mode, band = self.detect_mode_and_band(freq, full_comment)
            dxcc_info = self.get_dxcc_info(spotted)
            spot = {
                'utc': time_part,
                'freq': freq,
                'call': spotted,
                'mode': mode,
                'band': band,
                'dxcc': dxcc_info.get('country', ''),
                'grid': '',
                'spotter': spotter,
                'lat': dxcc_info.get('lat', 0),
                'lon': dxcc_info.get('lon', 0),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'comment': full_comment
            }
            return spot
        except Exception as e:
            logger.exception(f"Error parsing spot line: {e}")
            return None

    # -----------------------
    # Persistence (spots.json)
    # -----------------------
    def save_spots_to_file(self):
        try:
            with self.lock:
                data = list(self.spots)
            tmp = SPOTS_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SPOTS_FILE)
            logger.debug(f"Saved {len(data)} spots to {SPOTS_FILE}")
        except Exception:
            logger.exception("Failed to write spots file")

    def load_spots_from_file(self):
        try:
            if os.path.exists(SPOTS_FILE):
                with open(SPOTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    with self.lock:
                        self.spots = deque(data, maxlen=MAX_SPOTS)
                logger.info(f"Loaded {len(self.spots)} spots from {SPOTS_FILE}")
            else:
                logger.info("No spots file found, starting with empty list")
        except Exception:
            logger.exception("Failed to load spots file, starting empty")
            with self.lock:
                self.spots = deque(maxlen=MAX_SPOTS)

    # -----------------------
    # Cluster connection & reading
    # -----------------------
    def connect_to_cluster(self):
        try:
            if self.cluster_socket:
                try:
                    self.cluster_socket.close()
                except Exception:
                    pass
                self.cluster_socket = None
            host, port = self.current_cluster
            logger.info(f"Connecting to cluster {host}:{port}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            # send callsign (configurable)
            try:
                sock.send((CLUSTER_CALLSIGN + "\n").encode('utf-8'))
            except Exception:
                # ignore send errors; connection may still be valid
                logger.debug("Failed to send callsign initial string to cluster")
            self.cluster_socket = sock
            self.cluster_connected = True
            logger.info("Connected to DX cluster")
        except Exception as e:
            logger.error(f"Failed to connect to {self.current_cluster[0]}:{self.current_cluster[1]} - {e}")
            self.cluster_connected = False
            # swap primary/fallback properly - fix typo from earlier code
            if self.current_cluster == CLUSTER_PRIMARY:
                self.current_cluster = CLUSTER_FALLBACK
                logger.info("Switching to fallback cluster")
            else:
                self.current_cluster = CLUSTER_PRIMARY

    def read_cluster_data(self):
        # robust recv loop with buffer handling CRLF and partial lines
        buffer = ""
        sock = self.cluster_socket
        if not sock:
            return
        try:
            sock.settimeout(5.0)
        except Exception:
            pass
        while not self.stop_event.is_set() and self.cluster_connected and sock:
            try:
                data = sock.recv(4096)
                if not data:
                    logger.info("Cluster socket closed by remote")
                    break
                text = data.decode('utf-8', errors='ignore')
                buffer += text
                # process full lines
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip('\r ').strip()
                    if not line:
                        continue
                    spot = self.parse_dx_spot(line)
                    if spot:
                        with self.lock:
                            self.spots.appendleft(spot)
                            # save immediately for persistence
                            self.save_spots_to_file()
                        logger.info(f"New spot: {spot['call']} on {spot['freq']} ({spot['band']}/{spot['mode']})")
            except socket.timeout:
                continue
            except Exception as e:
                logger.exception(f"Error reading cluster data: {e}")
                break
        # ensure we mark as disconnected
        self.cluster_connected = False
        try:
            if self.cluster_socket:
                self.cluster_socket.close()
        except Exception:
            pass
        self.cluster_socket = None

    def cluster_worker(self):
        backoff = 1
        while not self.stop_event.is_set():
            try:
                self.connect_to_cluster()
                if self.cluster_socket and self.cluster_connected:
                    # reset backoff after successful connect
                    backoff = 1
                    self.read_cluster_data()
                else:
                    # failed connect: wait backoff
                    time.sleep(backoff)
                    backoff = min(300, backoff * 2)
            except Exception as e:
                logger.exception(f"Cluster worker exception: {e}")
                time.sleep(backoff)
                backoff = min(300, backoff * 2)
        logger.info("Cluster worker exiting (stop_event set)")

    # -----------------------
    # RSS worker (unchanged but robust)
    # -----------------------
    def rss_worker(self):
        rss_feeds = [
            "https://www.dx-world.net/feed/",
            "https://clublog.freshdesk.com/support/discussions/topics/3000175080.rss"
        ]
        while not self.stop_event.is_set():
            try:
                rss_entries = []
                for feed_url in rss_feeds:
                    try:
                        feed = feedparser.parse(feed_url)
                        for entry in feed.entries[:8]:
                            summary = entry.get('summary') or ''
                            rss_entries.append({
                                'title': entry.get('title', ''),
                                'link': entry.get('link', ''),
                                'published': entry.get('published', ''),
                                'summary': summary[:200] + '...' if len(summary) > 200 else summary
                            })
                    except Exception as e:
                        logger.debug(f"Error fetching RSS {feed_url}: {e}")
                        continue
                with self.lock:
                    self.rss_data = rss_entries[:15]
                logger.info(f"RSS updated: {len(self.rss_data)} entries")
            except Exception as e:
                logger.exception(f"RSS worker error: {e}")
            # sleep with early exit check
            for _ in range(int(RSS_UPDATE_INTERVAL / 1) if RSS_UPDATE_INTERVAL >= 1 else [1]):
                if self.stop_event.wait(1):
                    break

    def most_wanted_worker(self):
        # placeholder for periodic refresh (kept minimal)
        while not self.stop_event.is_set():
            try:
                # just sleep for the configured interval
                if self.stop_event.wait(WANTED_UPDATE_INTERVAL):
                    break
            except Exception as e:
                logger.exception(f"Most Wanted worker error: {e}")

    # -----------------------
    # Flask routes
    # -----------------------
    def setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template_string(HTML_TEMPLATE, version=VERSION, max_map_spots=MAX_MAP_SPOTS)

        @self.app.route('/spots.json')
        def spots_json():
            with self.lock:
                map_spots = list(self.spots)[:MAX_MAP_SPOTS]
                return jsonify({
                    'spots': list(self.spots),
                    'map_spots': map_spots
                })

        @self.app.route('/status.json')
        def status_json():
            with self.lock:
                total = len(self.spots)
            return jsonify({
                'cluster_connected': self.cluster_connected,
                'cluster_host': self.current_cluster[0],
                'version': VERSION,
                'dxcc_update': self.dxcc_update_date,
                'last_saved': datetime.now(timezone.utc).isoformat(),
                'total_spots': total
            })

        @self.app.route('/rss.json')
        def rss_json():
            with self.lock:
                return jsonify({'entries': self.rss_data})

        @self.app.route('/wanted.json')
        def wanted_json():
            return jsonify({'wanted': self.most_wanted})

        @self.app.route('/stats.json')
        def stats_json():
            with self.lock:
                spots_list = list(self.spots)
            band_stats = defaultdict(int)
            mode_stats = defaultdict(int)
            for spot in spots_list:
                band_stats[spot.get('band', 'UNK')] += 1
                mode_stats[spot.get('mode', 'UNK')] += 1
            return jsonify({
                'bands': dict(band_stats),
                'modes': dict(mode_stats)
            })

        @self.app.route('/export.csv')
        def export_csv():
            # generate CSV on the fly
            with self.lock:
                spots_list = list(self.spots)
            def generate():
                header = ['utc', 'freq', 'call', 'mode', 'band', 'dxcc', 'grid', 'spotter', 'lat', 'lon', 'timestamp', 'comment']
                yield ','.join(header) + '\n'
                for s in spots_list:
                    row = [str(s.get(h, '')).replace('"', '""') for h in header]
                    yield '"' + '","'.join(row) + '"\n'
            resp = Response(generate(), mimetype='text/csv; charset=utf-8')
            resp.headers.set("Content-Disposition", "attachment", filename="spots.csv")
            return resp

        @self.app.route('/healthz')
        def healthz():
            return jsonify({'status': 'ok', 'version': VERSION})

    # -----------------------
    # Worker management
    # -----------------------
    def start_workers(self):
        # threads: cluster, rss, most_wanted, periodic save
        self.threads = []
        t_cluster = threading.Thread(target=self.cluster_worker, daemon=True, name='cluster-worker')
        t_rss = threading.Thread(target=self.rss_worker, daemon=True, name='rss-worker')
        t_mw = threading.Thread(target=self.most_wanted_worker, daemon=True, name='mostwanted-worker')
        t_persist = threading.Thread(target=self.periodic_persist_worker, daemon=True, name='persist-worker')
        self.threads.extend([t_cluster, t_rss, t_mw, t_persist])
        for t in self.threads:
            t.start()
        logger.info("All workers started")

    def periodic_persist_worker(self):
        # periodically persist to disk as safety (even though we save on append)
        while not self.stop_event.is_set():
            try:
                self.save_spots_to_file()
            except Exception:
                logger.exception("Error during periodic persist")
            if self.stop_event.wait(60):  # every minute
                break

    def stop_workers(self):
        logger.info("Stopping workers...")
        self.stop_event.set()
        # close socket to unblock recv
        try:
            if self.cluster_socket:
                try:
                    self.cluster_socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.cluster_socket.close()
                except Exception:
                    pass
        except Exception:
            pass
        # join threads shortly
        for t in getattr(self, 'threads', []):
            try:
                t.join(timeout=2.0)
            except Exception:
                pass
        # final persist
        try:
            self.save_spots_to_file()
        except Exception:
            logger.exception("Error saving spots on shutdown")
        logger.info("Workers stopped")

    # -----------------------
    # Run
    # -----------------------
    def run(self):
        # register signal handlers for graceful shutdown
        def _sig_handler(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            # call stop and exit
            threading.Thread(target=self._shutdown_from_signal, daemon=True).start()

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        self.start_workers()
        logger.info(f"Starting Radio Spot Watcher {VERSION} on port {HTTP_PORT}")
        # Run Flask server
        try:
            # debug False, use reloader off so signals behave
            self.app.run(host='0.0.0.0', port=HTTP_PORT, debug=False, use_reloader=False)
        finally:
            logger.info("Flask server terminated, stopping workers")
            self.stop_workers()

    def _shutdown_from_signal(self):
        # used to avoid doing heavy work in signal handler context
        self.stop_workers()
        # attempt to exit process
        try:
            os._exit(0)
        except Exception:
            pass

# -----------------------
# HTML Template with palette UI + visual improvements
# -----------------------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Radio Spot Watcher</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
    <style>
        :root{
            --bg: #ffffff;
            --page-bg: #f1f5f9;
            --text: #0f172a;
            --muted: #64748b;
            --accent: #3b82f6;
            --accent-strong: #2563eb;
            --divider: #e6e9ee;
            --card-shadow: 0 1px 3px rgba(11,20,35,0.06);
            --table-row-hover: #f8fafc;
            --watch-bg: var(--accent);
        }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color:var(--page-bg); color:var(--text); line-height:1.6; }
        .header { background:var(--bg); padding:1rem 1.25rem; border-bottom:1px solid var(--divider); display:flex; justify-content:space-between; align-items:center; box-shadow:var(--card-shadow); }
        .title-block { display:flex; flex-direction:column; }
        .header h1 { color:var(--accent); font-size:1.6rem; margin-bottom:0.1rem; }
        .version { font-size:0.85rem; color:var(--muted); }
        .status { display:flex; align-items:center; gap:1rem; }
        .status-indicator { width:12px; height:12px; border-radius:50%; background-color:#ef4444; }
        .status-indicator.connected { background-color:#22c55e; }
        .main-container { display:grid; grid-template-columns:2fr 1fr; gap:1.25rem; padding:1.25rem; max-width:1400px; margin:0 auto; }
        .card { background:var(--bg); border-radius:8px; padding:1rem; box-shadow:var(--card-shadow); margin-bottom:1rem; }
        .card h2 { color:var(--accent); margin-bottom:0.5rem; font-size:1.05rem; position:relative; padding-bottom:0.4rem; }
        .card h2::after { content: ""; display:block; height:1px; background:var(--divider); margin-top:8px; width:100%; border-radius:1px; }
        #map { height:420px; border-radius:6px; margin-bottom:0.75rem; }
        .map-controls { display:flex; gap:0.5rem; margin-bottom:1rem; }
        .map-size-btn { padding:0.45rem 0.8rem; border:1px solid var(--divider); background:#fff; border-radius:5px; cursor:pointer; font-size:0.9rem; }
        .map-size-btn.active { background:var(--accent); color:white; border-color:var(--accent); }
        .spots-table { max-height:480px; overflow-y:auto; border:1px solid var(--divider); border-radius:6px; }
        table { width:100%; border-collapse:collapse; }
        th { background: linear-gradient(180deg, #fbfdff, #f8fafc); padding:0.6rem; text-align:left; font-weight:700; border-bottom:2px solid var(--divider); position:sticky; top:0; z-index:2; font-size:0.9rem; color:var(--muted); }
        td { padding:0.5rem 0.75rem; border-bottom:1px solid var(--divider); font-size:0.92rem; }
        tr:hover td { background:var(--table-row-hover); }
        tr:nth-child(even) td { background: #fff; }
        tr.watchhit { background: var(--watch-bg) !important; color:#fff; }
        tr.watchhit .call-link { color: inherit !important; text-decoration:underline; font-weight:700; }
        .call-link { color:var(--accent); text-decoration:none; font-weight:600; }
        .call-link:hover { text-decoration:underline; }
        .watchlist-input { display:flex; gap:0.5rem; margin-bottom:0.75rem; }
        .watchlist-input input { flex:1; padding:0.45rem; border:1px solid var(--divider); border-radius:6px; }
        .btn { padding:0.45rem 0.75rem; background:var(--accent); color:white; border:none; border-radius:6px; cursor:pointer; font-size:0.9rem; }
        .btn:hover { background:var(--accent-strong); }
        .watchlist-items { display:flex; flex-wrap:wrap; gap:0.5rem; }
        .watchlist-item { background:#f8fafc; padding:0.3rem 0.5rem; border-radius:6px; display:flex; align-items:center; gap:0.5rem; font-size:0.9rem; border:1px solid var(--divider); }
        .remove-btn { cursor:pointer; color:#ef4444; font-weight:bold; }
        .rss-item { margin-bottom:1rem; padding-bottom:1rem; border-bottom:1px solid var(--divider); }
        .rss-title { color:#f59e0b; font-weight:700; margin-bottom:0.25rem; }
        .rss-title a { color:inherit; text-decoration:none; font-weight:700; }
        .rss-summary { font-size:0.9rem; color:var(--muted); }
        .wanted-item { display:flex; align-items:center; gap:0.5rem; margin-bottom:0.5rem; padding:0.5rem; background:#f8fafc; border-radius:6px; border:1px solid var(--divider); }
        .filter-controls { display:flex; gap:0.75rem; align-items:center; flex-wrap:wrap; }
        .filter-controls select { padding:0.38rem 0.5rem; border-radius:6px; border:1px solid var(--divider); background:#fff; }
        .chart-container { margin-bottom:1rem; }
        .chart { border:1px solid var(--divider); border-radius:6px; }
        .footer { text-align:center; padding:1rem; color:var(--muted); font-size:0.9rem; border-top:1px solid var(--divider); background:var(--bg); margin-top:1rem; }
        .divider { height:1px; background:var(--divider); margin:12px 0; border-radius:1px; box-shadow:0 1px 0 rgba(255,255,255,0.6) inset; }
        .palette-select { display:flex; gap:0.5rem; align-items:center; }
        .palette-swatch { width:20px; height:20px; border-radius:4px; border:1px solid var(--divider); cursor:pointer; }
        .top-controls { display:flex; gap:0.5rem; align-items:center; }
        @media (max-width: 900px) {
            .main-container { grid-template-columns:1fr; padding:1rem; }
            .header { flex-direction:column; gap:0.5rem; align-items:flex-start; }
            #map { height:300px; }
        }
        /* cluster badge style */
        .marker-cluster-small { background: rgba(255,255,255,0.9); border:1px solid var(--divider); color:var(--text); }
        .marker-cluster-medium { background: rgba(255,255,255,0.95); border:1px solid var(--divider); color:var(--text); }
        .marker-cluster-large { background: rgba(255,255,255,0.98); border:1px solid var(--divider); color:var(--text); }
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
                <label style="font-size:0.9rem; color:var(--muted); margin-right:6px;">Palette :</label>
                <select id="palette-choice" style="padding:0.3rem 0.5rem; border-radius:6px; border:1px solid var(--divider);">
                    <option value="default">Clair (par défaut)</option>
                    <option value="ocean">Ocean</option>
                    <option value="sunset">Sunset</option>
                    <option value="contrast">High Contrast</option>
                    <option value="extended">Extended (10 couleurs)</option>
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
                                <th>UTC</th>
                                <th>Freq</th>
                                <th>Call</th>
                                <th>Mode</th>
                                <th>Bande</th>
                                <th>DXCC</th>
                                <th>Grid</th>
                                <th>Spotter</th>
                            </tr>
                        </thead>
                        <tbody id="spots-tbody">
                        </tbody>
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
            <!-- Horloges (alignées avec la colonne filtres/charts) -->
            <div class="card">
                <h2>Horloges</h2>
                <div style="display:flex; gap:1rem; align-items:center;">
                    <div style="min-width:150px;">
                        <div style="font-size:0.85rem; color:var(--muted);">UTC</div>
                        <div id="utc-time" style="font-family: monospace; font-weight:700; color:var(--accent); font-size:1.05rem;">--:--:--</div>
                        <div id="utc-date" style="font-size:0.85rem; color:var(--muted);">---</div>
                    </div>
                    <div style="min-width:150px;">
                        <div style="font-size:0.85rem; color:var(--muted);">Heure locale</div>
                        <div id="local-time" style="font-family: monospace; font-weight:700; color:var(--accent-strong); font-size:1.05rem;">--:--:--</div>
                        <div id="local-date" style="font-size:0.85rem; color:var(--muted);">---</div>
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

            <!-- Charts remontés avant RSS / Most Wanted -->
            <div class="card">
                <h2>Activité par bande</h2>
                <div class="chart-container">
                    <canvas id="band-chart" class="chart" width="300" height="200"></canvas>
                </div>
            </div>

            <div class="card">
                <h2>Activité par mode</h2>
                <div class="chart-container">
                    <canvas id="mode-chart" class="chart" width="300" height="200"></canvas>
                </div>
            </div>

            <div class="card">
                <h2>Flux RSS DX</h2>
                <div id="rss-content"></div>
            </div>

            <!-- Most Wanted déplacé en bas -->
            <div class="card">
                <h2>Most Wanted DXCC</h2>
                <div id="most-wanted"></div>
            </div>
        </div>
    </div>

    <footer class="footer">
        Radio Spot Watcher {{ version }}
    </footer>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <script>
        // Globals
        let map;
        let markersLayer;
        let watchlist = JSON.parse(localStorage.getItem('watchlist') || '[]');
        let mapSize = localStorage.getItem('mapSize') || 'medium';

        const BAND_LIST = ['All','160m','80m','40m','30m','20m','17m','15m','12m','10m','6m','2m','70cm','QO-100','UNK'];
        const MODE_LIST = ['All','FT8','FT4','CW','SSB','DIGI','UNK'];

        // default band colors (can be overridden by palette)
        const DEFAULT_BAND_COLORS = {
            '160m': '#ef4444',
            '80m': '#f97316',
            '40m': '#facc15',
            '30m': '#84cc16',
            '20m': '#3b82f6',
            '17m': '#6366f1',
            '15m': '#8b5cf6',
            '12m': '#06b6d4',
            '10m': '#10b981',
            '6m': '#ef7bbf',
            '2m': '#ef4444',
            '70cm': '#fb7185',
            'QO-100': '#a78bfa',
            'UNK': '#94a3b8'
        };

        // PALETTE ET COULEURS ETENDUES (10 couleurs)
        const DEFAULT_PALETTE = [
            '#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa',
            '#f472b6', '#22d3ee', '#84cc16', '#fb7185', '#f59e0b'
        ];

        const PALETTES = {
            'default': {
                '--accent': '#3b82f6',
                '--accent-strong': '#2563eb',
                watchBg: '#3b82f6',
                bands: DEFAULT_BAND_COLORS,
                palette_colors: DEFAULT_PALETTE
            },
            'ocean': {
                '--accent': '#0ea5a4',
                '--accent-strong': '#059669',
                watchBg: '#0b6b65',
                bands: {
                    '160m':'#064e3b','80m':'#0ea5a4','40m':'#0891b2','30m':'#06b6d4','20m':'#3b82f6','17m':'#60a5fa',
                    '15m':'#7c3aed','12m':'#38bdf8','10m':'#06b6d4','6m':'#06b6d4','2m':'#0b6b65','70cm':'#0284c7','QO-100':'#7dd3fc','UNK':'#94a3b8'
                },
                palette_colors: ['#064e3b','#0ea5a4','#0891b2','#06b6d4','#3b82f6','#60a5fa','#7c3aed','#38bdf8','#06b6d4','#0b6b65']
            },
            'sunset': {
                '--accent': '#f97316',
                '--accent-strong': '#ef4444',
                watchBg: '#7c2d12',
                bands: {
                    '160m':'#7c2d12','80m':'#ea580c','40m':'#f59e0b','30m':'#f97316','20m':'#ef4444','17m':'#f43f5e',
                    '15m':'#fb7185','12m':'#f97316','10m':'#f43f5e','6m':'#f472b6','2m':'#b45309','70cm':'#c2410c','QO-100':'#fb7185','UNK':'#94a3b8'
                },
                palette_colors: ['#7c2d12','#ea580c','#f59e0b','#f97316','#ef4444','#f43f5e','#fb7185','#f97316','#f43f5e','#f472b6']
            },
            'contrast': {
                '--accent': '#111827',
                '--accent-strong': '#0f172a',
                watchBg: '#0b1220',
                bands: {
                    '160m':'#111827','80m':'#374151','40m':'#4b5563','30m':'#6b7280','20m':'#0f172a','17m':'#111827',
                    '15m':'#111827','12m':'#111827','10m':'#0f172a','6m':'#374151','2m':'#1f2937','70cm':'#374151','QO-100':'#111827','UNK':'#0f172a'
                },
                palette_colors: ['#111827','#374151','#4b5563','#6b7280','#0f172a','#111827','#111827','#111827','#374151','#1f2937']
            },
            'extended': {
                '--accent': '#7c3aed',
                '--accent-strong': '#6c5ce7',
                watchBg: '#7c3aed',
                bands: {
                    '160m':'#7c3aed','80m':'#60a5fa','40m':'#34d399','30m':'#f59e0b','20m':'#fb7185','17m':'#f472b6',
                    '15m':'#a78bfa','12m':'#06b6d4','10m':'#10b981','6m':'#fd7b9c','2m':'#ef4444','70cm':'#00b894','QO-100':'#00cec9','UNK':'#94a3b8'
                },
                palette_colors: ['#7c3aed','#60a5fa','#34d399','#f59e0b','#fb7185','#f472b6','#a78bfa','#06b6d4','#10b981','#00b894']
            }
        };

        // Receive max map spots from server (rendered by Jinja)
        const CLIENT_MAX_MAP_SPOTS = {{ max_map_spots }} || 30;

        document.addEventListener('DOMContentLoaded', function() {
            initMap();
            initFilters();
            loadWatchlist();
            initPalette();
            initClocks();
            updateData();
            setInterval(updateData, 5000);
            document.getElementById('watchlist-input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') addToWatchlist();
            });
        });

        function initPalette() {
            const sel = document.getElementById('palette-choice');
            const saved = localStorage.getItem('uiPalette') || 'default';
            sel.value = saved;
            applyPalette(saved);
            sel.addEventListener('change', function() {
                localStorage.setItem('uiPalette', sel.value);
                applyPalette(sel.value);
                updateData(); // refresh markers / charts colors
            });
        }

        function applyPalette(name) {
            const p = PALETTES[name] || PALETTES['default'];
            if (p['--accent']) document.documentElement.style.setProperty('--accent', p['--accent']);
            if (p['--accent-strong']) document.documentElement.style.setProperty('--accent-strong', p['--accent-strong']);
            if (p['watchBg']) document.documentElement.style.setProperty('--watch-bg', p['watchBg']);
            // map band colors
            window.BAND_COLORS = Object.assign({}, DEFAULT_BAND_COLORS, p.bands || {});
            // palette colors for charts
            window.PALETTE_COLORS = p.palette_colors || DEFAULT_PALETTE;
        }

        function initMap() {
            map = L.map('map').setView([20, 0], 2);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);
            // use markercluster for nicer display
            markersLayer = L.markerClusterGroup({
                spiderfyOnMaxZoom: true,
                showCoverageOnHover: false,
                maxClusterRadius: 40
            });
            map.addLayer(markersLayer);
            setMapSize(mapSize);
        }

        function initFilters() {
            const bandSelect = document.getElementById('filter-band');
            const modeSelect = document.getElementById('filter-mode');

            BAND_LIST.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b;
                opt.textContent = b;
                bandSelect.appendChild(opt);
            });
            MODE_LIST.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                modeSelect.appendChild(opt);
            });

            const savedBand = localStorage.getItem('filterBand') || 'All';
            const savedMode = localStorage.getItem('filterMode') || 'All';
            bandSelect.value = savedBand;
            modeSelect.value = savedMode;

            bandSelect.addEventListener('change', () => {
                localStorage.setItem('filterBand', bandSelect.value);
                updateData();
            });
            modeSelect.addEventListener('change', () => {
                localStorage.setItem('filterMode', modeSelect.value);
                updateData();
            });
        }

        function setMapSize(size) {
            const mapElement = document.getElementById('map');
            const buttons = document.querySelectorAll('.map-size-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            switch(size) {
                case 'small': mapElement.style.height = '300px'; break;
                case 'large': mapElement.style.height = '600px'; break;
                default: mapElement.style.height = '420px'; size = 'medium';
            }
            const btn = Array.from(buttons).find(b => b.getAttribute('onclick').includes(`'${size}'`));
            if (btn) btn.classList.add('active');
            localStorage.setItem('mapSize', size);
            mapSize = size;
            setTimeout(() => map.invalidateSize(), 150);
        }

        function updateData() {
            fetch('/status.json').then(r => r.json()).then(data => {
                const indicator = document.getElementById('status-indicator');
                const status = document.getElementById('cluster-status');
                const dxccUpdate = document.getElementById('dxcc-update');
                indicator.className = 'status-indicator ' + (data.cluster_connected ? 'connected' : '');
                status.textContent = `Cluster: ${data.cluster_host} `;
                dxccUpdate.textContent = `DXCC: ${data.dxcc_update}`;
            }).catch(()=>{});

            fetch('/spots.json').then(r => r.json()).then(data => {
                const allSpots = data.spots || [];
                const bandFilter = localStorage.getItem('filterBand') || 'All';
                const modeFilter = localStorage.getItem('filterMode') || 'All';

                const filteredSpots = allSpots.filter(s => {
                    const bandOk = (bandFilter === 'All') || (s.band === bandFilter);
                    const modeOk = (modeFilter === 'All') || (s.mode === modeFilter);
                    return bandOk && modeOk;
                });

                updateSpotsTable(filteredSpots);
                updateMap(filteredSpots.slice(0, CLIENT_MAX_MAP_SPOTS));
                updateChartsFromSpots(filteredSpots);
            }).catch(()=>{});

            fetch('/rss.json').then(r => r.json()).then(data => updateRSS(data.entries)).catch(()=>{});
            fetch('/wanted.json').then(r => r.json()).then(data => updateMostWanted(data.wanted)).catch(()=>{});
        }

        function updateSpotsTable(spots) {
            const tbody = document.getElementById('spots-tbody');
            tbody.innerHTML = '';
            spots.forEach(spot => {
                const row = document.createElement('tr');
                const isWatched = watchlist.includes(spot.call.toUpperCase());
                if (isWatched) row.classList.add('watchhit');
                row.innerHTML = `
                    <td>${spot.utc}</td>
                    <td>${spot.freq}</td>
                    <td><a href="https://www.qrz.com/db/${spot.call}" target="_blank" class="call-link">${spot.call}</a></td>
                    <td>${spot.mode}</td>
                    <td>${spot.band}</td>
                    <td>${spot.dxcc}</td>
                    <td>${spot.grid}</td>
                    <td>${spot.spotter}</td>
                `;
                tbody.appendChild(row);
            });
        }

        function updateMap(spots) {
            markersLayer.clearLayers();
            const toUse = spots.slice(0, CLIENT_MAX_MAP_SPOTS || 30);
            toUse.forEach(spot => {
                if (spot.lat && spot.lon) {
                    const color = (window.BAND_COLORS && window.BAND_COLORS[spot.band]) || '#94a3b8';
                    const marker = L.circleMarker([spot.lat, spot.lon], {
                        radius: 6,
                        fillColor: color,
                        color: '#cbd5e1',
                        weight: 1.5,
                        opacity: 1,
                        fillOpacity: 0.95
                    });
                    marker.bindPopup(`
                        <strong>${spot.call}</strong><br>
                        ${spot.freq} kHz - ${spot.mode}<br>
                        ${spot.band} - ${spot.dxcc}<br>
                        <small>${spot.comment || ''}</small>
                    `);
                    markersLayer.addLayer(marker);
                }
            });
        }

        function updateRSS(entries) {
            const container = document.getElementById('rss-content');
            container.innerHTML = '';
            (entries || []).forEach(entry => {
                const item = document.createElement('div');
                item.className = 'rss-item';
                item.innerHTML = `
                    <div class="rss-title">
                        <a href="${entry.link}" target="_blank">${entry.title}</a>
                    </div>
                    <div class="rss-summary">${entry.summary}</div>
                `;
                container.appendChild(item);
            });
        }

        function updateMostWanted(wanted) {
            const container = document.getElementById('most-wanted');
            container.innerHTML = '';
            (wanted || []).forEach(item => {
                const div = document.createElement('div');
                div.className = 'wanted-item';
                div.innerHTML = `
                    <span class="flag">${item.flag}</span>
                    <span>${item.name}</span>
                `;
                container.appendChild(div);
            });
        }

        function updateChartsFromSpots(spots) {
            const bandCounts = {};
            const modeCounts = {};
            spots.forEach(s => {
                const b = s.band || 'UNK';
                const m = s.mode || 'UNK';
                bandCounts[b] = (bandCounts[b] || 0) + 1;
                modeCounts[m] = (modeCounts[m] || 0) + 1;
            });
            updateChart('band-chart', bandCounts, window.BAND_COLORS || DEFAULT_BAND_COLORS);
            updateChart('mode-chart', modeCounts, { 'FT8':'#0ea5b3','FT4':'#06b6d4','CW':'#ef4444','SSB':'#3b82f6','DIGI':'#a78bfa','UNK':'#94a3b8' });
        }

        // Canvas-based simple bar-chart renderer using palette of 10 colors when needed
        function updateChart(canvasId, data, colorMap = {}) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (!data || Object.keys(data).length === 0) return;
            const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
            const values = entries.map(e => e[1]);
            const maxValue = Math.max(...values);
            const barWidth = Math.max(20, (canvas.width / entries.length) - 10);
            const maxBarHeight = canvas.height - 40;
            const palette = window.PALETTE_COLORS && window.PALETTE_COLORS.length ? window.PALETTE_COLORS : DEFAULT_PALETTE;

            entries.forEach((entry, index) => {
                const [label, value] = entry;
                const barHeight = (value / maxValue) * maxBarHeight;
                const x = index * (barWidth + 10) + 10;
                const y = canvas.height - barHeight - 20;
                const color = colorMap[label] || colorMap[label.toUpperCase()] || palette[index % palette.length] || '#3b82f6';
                ctx.fillStyle = color;
                ctx.fillRect(x, y, barWidth, barHeight);
                ctx.fillStyle = '#1e293b';
                ctx.font = '12px sans-serif';
                ctx.textAlign = 'center';
                const labelText = label.length > 8 ? label.slice(0, 7) + '…' : label;
                ctx.fillText(labelText, x + barWidth/2, canvas.height - 5);
                ctx.fillStyle = '#0f172a';
                ctx.fillText(value.toString(), x + barWidth/2, y - 6);
            });
        }

        function addToWatchlist() {
            const input = document.getElementById('watchlist-input');
            const call = input.value.trim().toUpperCase();
            if (!call) return;
            if (watchlist.includes(call)) {
                showMessage('Indicatif déjà dans la watchlist', 'error');
                return;
            }
            watchlist.push(call);
            localStorage.setItem('watchlist', JSON.stringify(watchlist));
            input.value = '';
            loadWatchlist();
            showMessage('Indicatif ajouté à la watchlist', 'success');
        }

        function removeFromWatchlist(call) {
            watchlist = watchlist.filter(c => c !== call);
            localStorage.setItem('watchlist', JSON.stringify(watchlist));
            loadWatchlist();
            showMessage('Indicatif retiré de la watchlist', 'success');
        }

        function loadWatchlist() {
            const container = document.getElementById('watchlist-items');
            container.innerHTML = '';
            watchlist.forEach(call => {
                const item = document.createElement('div');
                item.className = 'watchlist-item';
                item.innerHTML = `
                    <span>${call}</span>
                    <span class="remove-btn" onclick="removeFromWatchlist('${call}')">🗑️</span>
                `;
                container.appendChild(item);
            });
        }

        function showMessage(text, type = 'success') {
            const container = document.getElementById('watchlist-messages');
            const message = document.createElement('div');
            message.className = `message ${type}`;
            message.style.padding = '0.5rem';
            message.style.borderRadius = '6px';
            message.style.marginBottom = '0.5rem';
            message.style.fontSize = '0.9rem';
            message.style.background = type === 'success' ? '#dcfce7' : '#fee2e2';
            message.style.color = type === 'success' ? '#166534' : '#991b1b';
            container.appendChild(message);
            message.textContent = text;
            setTimeout(() => {
                if (message.parentNode) message.parentNode.removeChild(message);
            }, 3000);
        }

        function exportCSV() {
            window.location.href = '/export.csv';
        }

        // Clocks: update every second
        function initClocks() {
            const utcTimeEl = document.getElementById('utc-time');
            const utcDateEl = document.getElementById('utc-date');
            const localTimeEl = document.getElementById('local-time');
            const localDateEl = document.getElementById('local-date');

            function formatLocal(d){
                const time = d.toLocaleTimeString(undefined, {hour:'2-digit', minute:'2-digit', second:'2-digit'});
                const date = d.toLocaleDateString(undefined, {weekday:'short', year:'numeric', month:'short', day:'numeric'});
                return {time,date};
            }
            function formatUTC(d){
                const time = new Intl.DateTimeFormat('en-GB', { hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false, timeZone: 'UTC' }).format(d);
                const date = new Intl.DateTimeFormat('en-GB', { weekday:'short', year:'numeric', month:'short', day:'numeric', timeZone: 'UTC' }).format(d);
                return {time,date};
            }
            function update(){
                const now = new Date();
                const loc = formatLocal(now);
                const utc = formatUTC(now);
                if(utcTimeEl) utcTimeEl.textContent = utc.time + ' UTC';
                if(utcDateEl) utcDateEl.textContent = utc.date.replace(/,/g,'') + ' (UTC)';
                if(localTimeEl) localTimeEl.textContent = loc.time;
                if(localDateEl) localDateEl.textContent = loc.date.replace(/,/g,'');
            }
            update();
            setInterval(update, 1000);
        }
    </script>
</body>
</html>
'''

# -----------------------
# Entrypoint
# -----------------------
if __name__ == '__main__':
    try:
        app = RadioSpotWatcher()
        app.run()
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.exception(f"Application error: {e}")