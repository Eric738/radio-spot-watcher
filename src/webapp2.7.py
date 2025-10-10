#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# Radio Spot Watcher — v2.7.0 stable (production)
# - Cluster F5LEN robuste: TCP ping, attente prompt login:, keepalive, reconnexion auto 5 min
# - Carte Leaflet: vert=normal, rouge clignotant 10 s = WATCHLIST ou MostWanted
# - Watchlist complète (ajout & suppression)
# - Most Wanted ClubLog (cache + MAJ hebdo)
# - Flux RSS (DX-World, OnAllBands -> fallback ARRL)
# - Panneau solaire (hamqsl)
# - MAJ DXCC, stats, compteur spots réels (UI + console 5 min)
# - Port 8000, debug False
# ============================================================

from flask import Flask, render_template_string, jsonify, request
import telnetlib, random, time, threading, requests, re, csv, os, json, socket
from datetime import datetime, timedelta

VERSION = "v2.7.0 stable"
app = Flask(__name__)

# ---------------------- ÉTAT ----------------------
spots = []  # {timestamp, timestamp_full, frequency, callsign, dxcc, band, mode, lat, lon, source}
REAL_SPOT_COUNT = 0
REAL_SPOT_COUNT_LOCK = threading.Lock()

WATCHLIST = ["FT8WW", "3Y0J", "J38LD"]  # tu peux modifier

DEFAULT_CLUSTER = {"host": "dxcluster.f5len.org", "port": 7373, "login": "F1SMV"}
STATUS = {
    "connected": False,
    "last_update": None,
    "last_error": None,
}

# ---------------------- DXCC (préfixes) ----------------------
CTY_URL  = "https://www.country-files.com/cty/cty.csv"
CTY_FILE = os.path.join(os.path.dirname(__file__), "cty.csv")
PREFIX_TO_COUNTRY = {}
SORTED_PREFIXES   = []

def update_cty():
    try:
        r = requests.get(CTY_URL, timeout=25)
        r.raise_for_status()
        with open(CTY_FILE, "wb") as f:
            f.write(r.content)
        print("[CTY] Fichier mis à jour.")
        return True
    except Exception as e:
        print("[CTY] Erreur de mise à jour:", e)
        return False

def load_cty():
    global PREFIX_TO_COUNTRY, SORTED_PREFIXES
    if not os.path.exists(CTY_FILE):
        update_cty()
    PREFIX_TO_COUNTRY.clear()
    try:
        with open(CTY_FILE, "r", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) >= 2:
                    PREFIX_TO_COUNTRY[row[0].strip().upper()] = row[1].strip()
        # fallbacks fréquents
        PREFIX_TO_COUNTRY.update({
            "F":"France","DL":"Fed. Rep. of Germany","G":"England","M":"England","GM":"Scotland",
            "I":"Italy","EA":"Spain","CT":"Portugal","ON":"Belgium","PA":"Netherlands",
            "K":"United States","W":"United States","N":"United States","VE":"Canada",
            "JA":"Japan","VK":"Australia","ZS":"South Africa","PY":"Brazil","LU":"Argentina",
            "VP2M":"Montserrat","EA8":"Canary Islands","4S":"Sri Lanka","LX":"Luxembourg",
        })
        SORTED_PREFIXES = sorted(PREFIX_TO_COUNTRY.keys(), key=len, reverse=True)
        print(f"[CTY] {len(PREFIX_TO_COUNTRY)} préfixes chargés.")
    except Exception as e:
        print("[CTY] Erreur de chargement:", e)

def dxcc_from_call(call):
    call = (call or "").upper().strip()
    for pref in SORTED_PREFIXES:
        if call.startswith(pref):
            return PREFIX_TO_COUNTRY.get(pref, "?")
    return "?"

# ---------------------- Centroïdes pays -> lat/lon ----------------------
COUNTRY_CENTROIDS = {
    "France": (46.7, 2.3), "Fed. Rep. of Germany": (51.1, 10.3), "England": (52.35, -1.17),
    "Scotland": (56.49, -4.2), "Italy": (42.8, 12.5), "Spain": (40.3, -3.7), "Portugal": (39.5, -8.0),
    "Belgium": (50.8, 4.4), "Netherlands": (52.2, 5.3), "United States": (39.8, -98.6), "Canada": (56.1, -106.3),
    "Japan": (36.2, 138.25), "Australia": (-25.0, 133.0), "South Africa": (-30.6, 22.9), "Brazil": (-10.3, -53.1),
    "Argentina": (-38.4, -63.6), "Oman": (21.47, 55.98), "Sri Lanka": (7.87, 80.77), "Luxembourg": (49.8, 6.1),
    "Canary Islands": (28.3, -16.6), "Montserrat": (16.75, -62.2)
}
def centroid_for(country: str):
    return COUNTRY_CENTROIDS.get(country or "", (None, None))

# ---------------------- UTILS ----------------------
DX_PATTERN = re.compile(
    r"^DX de\s+([A-Z0-9/-]+).*?[:>]?\s+(\d+(?:\.\d+)?)\s+([A-Z0-9/]+)\s*(.*)$",
    re.IGNORECASE
)

def guess_band(f):
    if 1.8<=f<=2.0: return "160m"
    if 3.5<=f<=4.0: return "80m"
    if 7.0<=f<=7.3: return "40m"
    if 10.1<=f<=10.15: return "30m"
    if 14.0<=f<=14.35: return "20m"
    if 18.068<=f<=18.168: return "17m"
    if 21.0<=f<=21.45: return "15m"
    if 24.89<=f<=24.99: return "12m"
    if 28.0<=f<=29.7: return "10m"
    if 50.0<=f<=54.0: return "6m"
    return "?"

def detect_mode(txt, f=None):
    t = (txt or "").upper()
    if "FT8" in t: return "FT8"
    if "CW" in t: return "CW"
    if "SSB" in t or "USB" in t or "LSB" in t: return "SSB"
    if f and 14.074 <= f <= 14.076: return "FT8"
    return "?"

def canon_call(cs: str) -> str:
    if not cs: return ""
    cs = re.sub(r"\s+", "", cs.upper())
    return re.sub(r"(?:/P|/QRP|/M|/MM|/AM)$", "", cs)

# ---------------------- CLEANUP ----------------------
def cleanup_spots():
    while True:
        cutoff = datetime.utcnow() - timedelta(minutes=15)
        def keep(s):
            try:
                ts = datetime.strptime(s["timestamp_full"], "%Y-%m-%d %H:%M:%S")
                return ts > cutoff
            except Exception:
                return True
        spots[:] = [s for s in spots if keep(s)]
        time.sleep(60)

# ---------------------- SOLAIRE ----------------------
def refresh_solar():
    HAMQSL_JSON = "https://www.hamqsl.com/solarjson.php"
    while True:
        try:
            r = requests.get(HAMQSL_JSON, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
            if r.ok:
                j = r.json()
                app.config["SOLAR"] = {
                    "sfi": j.get("solar",{}).get("solarf"),
                    "kp": j.get("geomag",{}).get("kpindex"),
                    "sun": j.get("solar",{}).get("sunspots"),
                    "at": datetime.utcnow().strftime("%H:%M")
                }
        except Exception as e:
            print("[SOLAR] Erreur:", e)
        time.sleep(3*3600)

# ---------------------- RSS ----------------------
def load_rss(url):
    try:
        import feedparser
        r = requests.get(url, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        if feed.entries:
            return [{"title": e.title, "link": e.link} for e in feed.entries[:10]]
    except Exception as e:
        print("[RSS]", url, "->", e)
    return [{"title":"Flux indisponible","link":"#"}]

@app.route("/rss1.json")
def rss1():
    return jsonify(load_rss("https://www.dx-world.net/feed/"))

@app.route("/rss2.json")
def rss2():
    data = load_rss("https://feeds.feedburner.com/OnAllBands")
    if len(data)==1 and data[0]["link"]=="#":
        data = load_rss("https://www.arrl.org/news/rss")
    return jsonify(data)

# ---------------------- Most Wanted (ClubLog) ----------------------
MOST_FILE = os.path.join(os.path.dirname(__file__), "most_wanted.json")
DEFAULT_MW = ["Bouvet Island","Crozet Island","Scarborough Reef","North Korea","Palmyra & Jarvis",
              "Navassa Island","Prince Edward & Marion","South Sandwich","Macquarie Island",
              "Peter I Island","Kure Island","Heard Island","Andaman & Nicobar","Palestine",
              "Johnston Island","Yemen","Syria","Bhutan","Eritrea","Somalia","Chad","Djibouti",
              "Central African Republic","Gabon","Equatorial Guinea","Macao","Sudan","Oman",
              "Myanmar","Iran","Libya","Western Sahara","Guinea","Benin","Burundi","Laos"]

def load_most():
    if os.path.exists(MOST_FILE):
        try: return json.load(open(MOST_FILE,encoding="utf-8"))
        except Exception: pass
    return DEFAULT_MW

def save_most(lst):
    try: json.dump(lst, open(MOST_FILE,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e: print("[MOST] save:", e)

def fetch_clublog(limit=50):
    try:
        html = requests.get("https://clublog.org/mostwanted.php", timeout=25, headers={"User-Agent":"Mozilla/5.0"}).text
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S|re.I)
        out = []
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S|re.I)
            if not cells: continue
            txt = re.sub("<.*?>","",cells[0]).strip()
            if txt and not txt.isdigit() and "Most Wanted" not in txt:
                out.append(txt)
        dedup=[]
        [dedup.append(x) for x in out if x not in dedup]
        return dedup[:limit] if dedup else None
    except Exception as e:
        print("[ClubLog] erreur:", e)
        return None

MOST_WANTED = load_most()
def updater_most():
    global MOST_WANTED
    while True:
        time.sleep(7*24*3600)
        new = fetch_clublog(50)
        if new:
            MOST_WANTED = new
            save_most(new)

@app.route("/wanted.json")
def wanted_json():
    return jsonify({"list": MOST_WANTED})

# ---------------------- API diverses ----------------------
@app.route("/update_cty")
def update_cty_route():
    ok = update_cty()
    load_cty()
    return jsonify({"success": ok, "count": len(PREFIX_TO_COUNTRY)})

@app.route("/dxcc_status.json")
def dxcc_status():
    return jsonify({"prefix_count": len(PREFIX_TO_COUNTRY)})

@app.route("/remove_call", methods=["POST"])
def remove_call():
    incoming = request.json.get("call","")
    cc = canon_call(incoming)
    idx = next((i for i,v in enumerate(WATCHLIST) if canon_call(v)==cc), None)
    if idx is not None:
        del WATCHLIST[idx]
        return jsonify({"ok":True, "watchlist": WATCHLIST})
    return jsonify({"ok":False, "watchlist": WATCHLIST}), 404

@app.route("/spots.json")
def spots_json():
    return jsonify(spots)

@app.route("/stats.json")
def stats_json():
    with REAL_SPOT_COUNT_LOCK:
        c = REAL_SPOT_COUNT
    return jsonify({
        "connected": STATUS["connected"],
        "real_spot_count": c,
        "last_update": STATUS["last_update"],
        "solar": app.config.get("SOLAR")
    })

# ---------------------- CLUSTER ----------------------
def tcp_ping(host, port, timeout=3.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def read_until_any(tn, prompts, timeout=6):
    end = time.time()+timeout
    buf = b""
    while time.time() < end:
        try:
            chunk = tn.read_eager()
            if chunk:
                buf += chunk
                low = buf.lower()
                for p in prompts:
                    if p in low:
                        return True
        except EOFError:
            break
        time.sleep(0.05)
    return False

def cluster_worker():
    global REAL_SPOT_COUNT
    while True:
        if not tcp_ping(DEFAULT_CLUSTER["host"], DEFAULT_CLUSTER["port"], 3):
            STATUS["connected"]=False
            STATUS["last_error"]="Ping échoué"
            print("[CLUSTER] Ping échoué — nouvelle tentative dans 5 min")
            time.sleep(300)
            continue

        try:
            tn = telnetlib.Telnet(DEFAULT_CLUSTER["host"], DEFAULT_CLUSTER["port"], timeout=15)
            # attendre prompt login/call
            try:
                tn.read_until(b"login:", timeout=4)
            except Exception:
                # fallback : scruter tout retour
                read_until_any(tn, [b"login:", b"call:"], timeout=4)
            tn.write((DEFAULT_CLUSTER["login"]+"\n").encode())
            time.sleep(0.5)
            tn.write(b"set/dx filter by_band all\n")
            tn.write(b"sh/dx 50\n")
            STATUS["connected"]=True
            STATUS["last_error"]=None
            print(f"[INFO] Radio Spot Watcher {VERSION} — cluster F5LEN connecté")
        except Exception as e:
            STATUS["connected"]=False
            STATUS["last_error"]=str(e)
            print("[CLUSTER] Erreur de connexion:", e)
            time.sleep(300)
            continue

        last_data = time.time()
        try:
            while True:
                raw = tn.read_until(b"\n", timeout=30)
                if not raw:
                    if time.time()-last_data > 60:
                        tn.write(b"sh/dx\n")
                        last_data = time.time()
                    continue
                line = raw.decode(errors="ignore").strip()
                if not line.startswith("DX de "):
                    continue
                m = DX_PATTERN.match(line)
                if not m:
                    continue
                _, freq, call, txt = m.groups()
                try:
                    f = float(freq)
                except Exception:
                    continue
                if f > 1000: f /= 1000.0
                now = datetime.utcnow()
                country = dxcc_from_call(call)
                lat, lon = centroid_for(country)
                s = {
                    "timestamp": now.strftime("%H:%M:%S"),
                    "timestamp_full": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "frequency": f"{f:.3f} MHz",
                    "callsign": call.upper(),
                    "dxcc": country,
                    "band": guess_band(f),
                    "mode": detect_mode(txt, f),
                    "lat": lat, "lon": lon,
                    "source": "cluster"
                }
                spots.insert(0, s)
                del spots[500:]
                with REAL_SPOT_COUNT_LOCK:
                    REAL_SPOT_COUNT += 1
                STATUS["last_update"] = now.strftime("%H:%M:%S")
                last_data = time.time()
        except Exception as e:
            STATUS["connected"]=False
            STATUS["last_error"]=str(e)
            print("[CLUSTER] Boucle interrompue:", e)
            time.sleep(30)  # petit backoff avant retry

# ---------------------- SIMULATION ----------------------
def simulate_spots():
    demo = ["F4ABC","DL1XYZ","JA1NQZ","VK0DS","PY0F","A45XR","ZS1ABC","EA8/ON4ZZZ","VP2MAA","4STAB","LX25GDG","IW2NEF","KI7QCF"]
    while True:
        f = random.choice([7.032,7.074,10.136,14.074,18.100,21.074,24.902,28.074,50.313])
        call = random.choice(demo)
        now = datetime.utcnow()
        country = dxcc_from_call(call)
        lat, lon = centroid_for(country)
        s = {
            "timestamp": now.strftime("%H:%M:%S"),
            "timestamp_full": now.strftime("%Y-%m-%d %H:%M:%S"),
            "frequency": f"{f:.3f} MHz",
            "callsign": call,
            "dxcc": country,
            "band": guess_band(f),
            "mode": random.choice(["FT8","CW","SSB","?"]),
            "lat": lat, "lon": lon,
            "source": "sim"
        }
        spots.insert(0, s)
        del spots[500:]
        time.sleep(8)

# ---------------------- CONSOLE ----------------------
def console_totals():
    while True:
        time.sleep(300)
        with REAL_SPOT_COUNT_LOCK:
            c = REAL_SPOT_COUNT
        print(f"[CLUSTER] Total spots reçus : {c}")

# ---------------------- UI ----------------------
@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        new_call = request.form.get("new_call","").upper().strip()
        if new_call and canon_call(new_call) not in [canon_call(x) for x in WATCHLIST]:
            WATCHLIST.append(new_call)

    html = """<!DOCTYPE html><html><head>
<meta charset="utf-8"><title>Radio Spot Watcher — {{ version }}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css">
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{background:#0b1220;color:#e5e7eb;font-family:system-ui,Segoe UI,Arial,sans-serif;margin:18px}
h2{margin:0 0 12px 0}
.grid{display:grid;grid-template-columns:1.6fr 1fr;gap:14px}
.card{background:#121826;border:1px solid #223049;border-radius:14px;padding:12px}
#map{height:420px;border-radius:12px;border:1px solid #2b3342}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.kpill{padding:6px 10px;border-radius:999px;background:#0f1623;border:1px solid #2b3342}
.formline{display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap}
.formline input{padding:8px;border-radius:8px;border:1px solid #2b3342;background:#0d1421;color:#fff}
.formline button{padding:8px 12px;border:none;border-radius:8px;background:#2563eb;color:#fff;cursor:pointer}
.badge{display:inline-flex;gap:6px;align-items:center;padding:6px 10px;border-radius:999px;background:#151b26;border:1px solid #2b3342}
.tbl{width:100%;border-collapse:collapse}
.tbl th,.tbl td{padding:8px 10px;text-align:left}
.tbl thead th{position:sticky;top:0;background:#1a2232}
.tbl tr:nth-child(even){background:#0f1522}
.small{opacity:.85}
.col2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
</style>
</head><body>
<h2>📡 Radio Spot Watcher — {{ version }}</h2>

<div class="grid">
  <div class="card">
    <div class="kpis">
      <span class="kpill">Cluster: <b id="conn">Hors ligne</b></span>
      <span class="kpill">Spots réels: <b id="rcnt">0</b></span>
      <span class="kpill">Dernière MAJ: <b id="last">—</b></span>
      <span class="kpill">SFI/Kp/Sun: <b id="solar">—</b></span>
    </div>
    <div class="formline">
      <form method="POST" style="display:flex;gap:8px;align-items:center">
        <input name="new_call" placeholder="Ajouter un indicatif à surveiller">
        <button>Ajouter</button>
      </form>
      <div class="badge">WATCHLIST: <span id="wl">{{ ', '.join(watchlist) }}</span></div>
      <button id="updateDXCC" class="badge" style="cursor:pointer">Mettre à jour DXCC</button>
      <span id="dxccInfo" class="small"></span>
    </div>
    <div id="map"></div>
    <div class="col2" style="margin-top:10px">
      <div class="card" style="padding:8px"><canvas id="barChart"></canvas></div>
      <div class="card" style="padding:8px"><canvas id="pieChart"></canvas></div>
    </div>
  </div>

  <div class="card">
    <table class="tbl">
      <thead><tr><th>Heure</th><th>Fréq</th><th>Indicatif</th><th>DXCC</th><th>Bande</th><th>Mode</th><th></th></tr></thead>
      <tbody id="tb"><tr><td colspan="7">Chargement…</td></tr></tbody>
    </table>
    <div class="card" style="margin-top:10px">
      <div><b>Most Wanted (ClubLog)</b></div>
      <ul id="mw" class="small"><li>Chargement…</li></ul>
    </div>
    <div class="card" style="margin-top:10px">
      <div><b>DX-World</b></div>
      <ul id="rss1" class="small"><li>Chargement…</li></ul>
    </div>
    <div class="card" style="margin-top:10px">
      <div><b>OnAllBands / ARRL</b></div>
      <ul id="rss2" class="small"><li>Chargement…</li></ul>
    </div>
  </div>
</div>

<script>
const WATCHLIST = {{ watchlist|tojson }};

// Map
const map = L.map('map', { worldCopyJump:true, preferCanvas:true }).setView([20,0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:6,minZoom:2,attribution:''}).addTo(map);
const markers = new Map(); // k -> {layer, t0, glowUntil}
function k5(s){
  const t5 = Math.floor(new Date((s.timestamp_full||'').replace(' ', 'T')+'Z').getTime()/300000);
  return `${s.callsign}|${s.band}|${s.mode}|${t5}`;
}
function isHot(s){
  const inWL = WATCHLIST.includes(String(s.callsign||'').toUpperCase());
  // MostWanted (nom DXCC exact dans la liste) -> color rouge aussi
  return inWL || (window._MW && window._MW.has(s.dxcc));
}
function upsertMarker(s){
  if(typeof s.lat !== 'number' || typeof s.lon !== 'number') return;
  const k = k5(s);
  if(markers.has(k)) return;
  const hot = isHot(s);
  const color = hot ? '#ef4444' : '#22c55e';
  const m = L.circleMarker([s.lat, s.lon], {radius: hot?7:5, weight:2, color, fillColor:color, fillOpacity:0.95}).addTo(map);
  m.bindPopup(`${s.callsign} — ${s.frequency} — ${s.mode||'?'} — ${s.band||''} — ${s.timestamp||''}Z<br>${s.dxcc||''}`);
  const now = Date.now();
  markers.set(k, {layer:m, t0:now, glowUntil: hot ? now + 10000 : 0});
}
function sweepMarkers(){
  const now = Date.now();
  for(const [k,v] of Array.from(markers.entries())){
    const age = now - v.t0;
    if(age > 15*60*1000){ map.removeLayer(v.layer); markers.delete(k); continue; }
    if(v.glowUntil && now < v.glowUntil){
      const phase = Math.floor((now - v.t0)/300)%2===0 ? 0.35 : 0.95;
      v.layer.setStyle({opacity:phase, fillOpacity:phase});
    }else{
      v.layer.setStyle({opacity:0.95, fillOpacity:0.95});
      v.glowUntil = 0;
    }
  }
}
setInterval(sweepMarkers, 300);

// Charts
let bandChart, modeChart;
function updateCharts(data){
  const byBand={}, byMode={};
  for(const s of data){
    byBand[s.band]= (byBand[s.band]||0)+1;
    const m=(s.mode||'?').toUpperCase(); byMode[m]=(byMode[m]||0)+1;
  }
  const bL=Object.keys(byBand), bV=Object.values(byBand);
  const mL=Object.keys(byMode), mV=Object.values(byMode);
  if(!bandChart){
    bandChart = new Chart(document.getElementById('barChart'), {type:'bar', data:{labels:bL, datasets:[{data:bV, backgroundColor:bL.map(()=>"#6b7280")}]}, options:{plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true}}}});
    modeChart = new Chart(document.getElementById('pieChart'), {type:'pie', data:{labels:mL, datasets:[{data:mV, backgroundColor:mL.map(()=>"#6b7280")}]}, options:{plugins:{legend:{position:'bottom'}}}});
  }else{
    bandChart.data.labels=bL; bandChart.data.datasets[0].data=bV; bandChart.update();
    modeChart.data.labels=mL; modeChart.data.datasets[0].data=mV; modeChart.update();
  }
}

// Watchlist: suppression
async function delCall(call){
  const r = await fetch('/remove_call',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({call})});
  const j = await r.json();
  if(j.ok){ location.reload(); } else { alert("Suppression impossible"); }
}

// DXCC update
document.getElementById('updateDXCC').onclick = async ()=>{
  const btn = document.getElementById('updateDXCC'); btn.disabled=true;
  const r = await fetch('/update_cty'); const j = await r.json();
  document.getElementById('dxccInfo').innerText = j.success ? `DXCC à jour (${j.count} préfixes)` : 'Erreur MAJ DXCC';
  btn.disabled=false;
};

// RSS + MW
async function loadSide(){
  const r1 = await (await fetch('/rss1.json')).json();
  const r2 = await (await fetch('/rss2.json')).json();
  document.getElementById('rss1').innerHTML = r1.map(e=>`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`).join('') || '<li>—</li>';
  document.getElementById('rss2').innerHTML = r2.map(e=>`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`).join('') || '<li>—</li>';
  const mw = await (await fetch('/wanted.json')).json();
  window._MW = new Set(mw.list||[]);
  document.getElementById('mw').innerHTML = (mw.list||[]).map(x=>`<li>${x}</li>`).join('') || '<li>—</li>';
}

// Refresh principal
async function refresh(){
  const data = await (await fetch('/spots.json')).json();
  // table
  let html='';
  for(const s of data){
    const inWL = WATCHLIST.includes(String(s.callsign||'').toUpperCase());
    const hot = inWL || (window._MW && window._MW.has(s.dxcc));
    html += `<tr${hot?' style="color:#f87171;font-weight:600"':''}>
      <td>${s.timestamp||''}</td>
      <td>${s.frequency||''}</td>
      <td>${s.callsign||''}</td>
      <td>${s.dxcc||''}</td>
      <td>${s.band||''}</td>
      <td>${s.mode||'?'}</td>
      <td>${inWL?`<button onclick="delCall('${s.callsign}')">🗑️</button>`:''}</td>
    </tr>`;
    upsertMarker(s);
  }
  document.getElementById('tb').innerHTML = html || '<tr><td colspan="7">Aucun spot</td></tr>';
  updateCharts(data);

  const st = await (await fetch('/stats.json')).json();
  document.getElementById('conn').innerText = st.connected ? 'Connecté' : 'Hors ligne';
  document.getElementById('rcnt').innerText = st.real_spot_count || 0;
  document.getElementById('last').innerText = st.last_update || '—';
  const sol = st.solar;
  document.getElementById('solar').innerText = sol ? `${sol.sfi||'–'}/${sol.kp||'–'}/${sol.sun||'–'}` : '—';
}
setInterval(refresh, 5000);
setInterval(loadSide, 600000);
window.onload = ()=>{ refresh(); loadSide(); };
</script>
</body></html>"""
    return render_template_string(html, version=VERSION, watchlist=WATCHLIST)

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    print("[INFO] Initialisation...")
    load_cty()
    threading.Thread(target=cleanup_spots, daemon=True).start()
    threading.Thread(target=refresh_solar, daemon=True).start()
    threading.Thread(target=simulate_spots, daemon=True).start()
    threading.Thread(target=console_totals, daemon=True).start()
    time.sleep(2)
    threading.Thread(target=cluster_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=8000, debug=False)