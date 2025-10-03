#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, render_template_string, jsonify, redirect, url_for
import json, os, re, time, threading, csv, requests, feedparser, random
from datetime import datetime
import telnetlib

# --- Chemins ---
BASE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR  = os.path.join(BASE_DIR, "static")
CONFIG_DIR  = os.path.join(BASE_DIR, "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
DATA_DIR    = os.path.join(BASE_DIR, "data")
DATA_FILE   = os.path.join(DATA_DIR, "cty.csv")

app = Flask(__name__, static_url_path="/static", static_folder=STATIC_DIR)

spots  = []
STATUS = {"connected": False, "last_error": None, "last_update": None, "cty_message": ""}

DEFAULT_CLUSTER = {"host": "dxcluster.f5len.org", "port": 7373, "login": "NOCALL"}
RSS_URL = "https://www.dx-world.net/feed/"

# --- DXCC ---
DXCC_TABLE = {}
FALLBACK_DXCC = {"F":"France","EA":"Spain","DL":"Germany","I":"Italy","G":"United Kingdom","M":"United Kingdom",
    "JA":"Japan","VK":"Australia","ZL":"New Zealand","W":"USA","K":"USA","N":"USA","AA":"USA"}

# Regex tolérant
DX_LINE = re.compile(
    r"^DX de\s+(?P<spotter>[A-Z0-9\-\/]+):\s+(?P<freq>\d+(\.\d+)?)\s+(?P<dx>[A-Z0-9\/]+)\s*(?P<comment>.*)$",
    re.IGNORECASE
)

# ---------------------- Config ----------------------
def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        cfg = {"cluster": DEFAULT_CLUSTER, "callsigns": [], "filters": {"band": "", "mode": ""}}
        save_config(cfg)
        return cfg
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"cluster": DEFAULT_CLUSTER, "callsigns": [], "filters": {"band": "", "mode": ""}}

def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ---------------------- DXCC ----------------------
def update_cty_file():
    url = "https://www.country-files.com/cty/cty.csv"
    os.makedirs(DATA_DIR, exist_ok=True)
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    with open(DATA_FILE, "wb") as f:
        f.write(r.content)

def load_cty():
    global DXCC_TABLE
    try:
        if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) < 1000:
            update_cty_file()
        tmp = {}
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) >= 2:
                    tmp[row[0].upper().strip()] = row[1].strip()
        DXCC_TABLE = tmp
    except Exception:
        DXCC_TABLE = FALLBACK_DXCC.copy()

def dxcc_lookup(call: str) -> str:
    call = call.upper()
    for p in sorted(DXCC_TABLE.keys(), key=lambda x: -len(x)):
        if call.startswith(p):
            return DXCC_TABLE[p]
    return "Inconnu"

# ---------------------- Bande ----------------------
def guess_band(freq_mhz: float) -> str:
    f = freq_mhz
    if 1.8   <= f <= 2.0:     return "160m"
    if 3.5   <= f <= 4.0:     return "80m"
    if 7.0   <= f <= 7.3:     return "40m"
    if 10.1  <= f <= 10.15:   return "30m"
    if 14.0  <= f <= 14.35:   return "20m"
    if 18.068<= f <= 18.168:  return "17m"
    if 21.0  <= f <= 21.45:   return "15m"
    if 24.89 <= f <= 24.99:   return "12m"
    if 28.0  <= f <= 29.7:    return "10m"
    if 50.0  <= f <= 54.0:    return "6m"
    if 70.0  <= f <= 71.0:    return "4m"
    if 144.0 <= f <= 148.0:   return "2m"
    if 430.0 <= f <= 440.0:   return "70cm"
    if 10489 <= f <= 10490:   return "QO-100"
    return "?"

# ---------------------- RSS ----------------------
RSS_CACHE = {"time": 0, "data": []}

def load_rss():
    global RSS_CACHE
    if time.time() - RSS_CACHE["time"] > 600:
        try:
            feed = feedparser.parse(RSS_URL)
            RSS_CACHE = {
                "time": time.time(),
                "data": [{"title": e.title, "link": e.link} for e in feed.entries[:10]]
            }
        except Exception as e:
            RSS_CACHE = {"time": time.time(), "data": [{"title": f"Erreur RSS: {e}", "link": "#"}]}
    return RSS_CACHE["data"]

@app.route("/rss.json")
def rss_json():
    return jsonify(load_rss())

# ---------------------- Telnet ----------------------
def telnet_task(host, port, login):
    global spots, STATUS
    try:
        print(f"[TELNET] Connexion à {host}:{port}…")
        tn = telnetlib.Telnet(host, port, timeout=15)
        tn.write((login + "\n").encode())
        STATUS.update({"connected": True, "last_error": None})
        print(f"[TELNET] Connecté en tant que {login}")
    except Exception as e:
        STATUS.update({"connected": False, "last_error": str(e)})
        print("[TELNET] Erreur connexion:", e)
        threading.Thread(target=simulate_spots, daemon=True).start()
        return

    while True:
        try:
            raw = tn.read_until(b"\n", timeout=30).decode(errors="ignore").strip()
            if not raw:
                continue
            print("[TELNET RAW]", raw)
            m = DX_LINE.match(raw)
            if not m:
                continue

            freq = float(m.group("freq"))
            if freq > 1000: freq = freq/1000.0
            dx  = m.group("dx").upper()
            com = (m.group("comment") or "").strip()

            spots.insert(0, {
                "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
                "frequency": f"{freq:.3f} MHz",
                "callsign": dx,
                "dxcc": dxcc_lookup(dx),
                "band": guess_band(freq),
                "mode": com if com else "?"
            })
            spots = spots[:200]
            STATUS["last_update"] = datetime.utcnow().strftime("%H:%M:%S")
        except Exception as e:
            STATUS.update({"connected": False, "last_error": str(e)})
            print("[TELNET ERR]", e)
            break

# ---------------------- Simulation ----------------------
CALLSIGNS_SIMU = ["FT8WW","3Y0J","K1ABC","F5LEN","JA1NUT","PY0F","VK0DS"]
def simulate_spots():
    global spots
    print("[SIMU] Mode simulation activé")
    while True:
        f = random.uniform(14.0,14.35)
        call = random.choice(CALLSIGNS_SIMU)
        spots.insert(0,{
            "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            "frequency": f"{f:.3f} MHz",
            "callsign": call,
            "dxcc": "Simulation","band": guess_band(f),"mode":"FT8"})
        spots = spots[:200]
        time.sleep(10)

def start_bg():
    cfg = load_config()
    cluster = cfg.get("cluster", DEFAULT_CLUSTER)
    threading.Thread(target=telnet_task,
                     args=(cluster["host"], cluster["port"], cluster["login"]),
                     daemon=True).start()

# ---------------------- API ----------------------
@app.route("/spots.json")
def spots_json():
    return jsonify(spots)

@app.route("/update_cty")
def update_cty():
    try:
        update_cty_file()
        load_cty()
        STATUS["cty_message"] = "✅ cty.csv mis à jour avec succès"
    except Exception as e:
        STATUS["cty_message"] = f"❌ Erreur mise à jour : {e}"
    return redirect(url_for("index"))

@app.route("/del/<call>")
def del_call(call):
    cfg = load_config()
    wl = set(cfg.get("callsigns", []))
    if call in wl:
        wl.remove(call)
        cfg["callsigns"] = sorted(wl)
        save_config(cfg)
        print(f"[WATCHLIST] Supprimé: {call}")
    return redirect(url_for("index"))

# ---------------------- Page ----------------------
@app.route("/", methods=["GET","POST"])
def index():
    cfg = load_config()

    if request.method == "POST":
        new_call = request.form.get("new_call", "").upper().strip()
        if new_call:
            wl = set(cfg.get("callsigns", []))
            if new_call not in wl:
                wl.add(new_call)
                cfg["callsigns"] = sorted(wl)
                save_config(cfg)
                print(f"[WATCHLIST] Ajouté: {new_call}")

    watchlist = cfg.get("callsigns", [])
    cty_msg = STATUS.get("cty_message","")

    html="""<!DOCTYPE html><html><head>
<meta charset="utf-8">
<link rel="stylesheet" href="/static/style.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
/* Tableau */
table { width:100%; border-collapse:collapse; margin-top:10px; font-size:14px; }
th, td { padding:8px 10px; text-align:left; }
th { background:#1f2937; color:#93c5fd; }
tr:nth-child(even) { background:#111827; }
tr:nth-child(odd)  { background:#0f1115; }
tr:hover { background:#374151; }

/* Watchlist highlight */
tr.watch td, tr.watch a { color:#facc15 !important; font-weight:700; }
tr.watch td:nth-child(3)::before { content:"🔔 "; }

/* Normal rows */
tr.normal td, tr.normal a { color:#e5e7eb !important; }

/* Badges état */
.badge { display:inline-block; padding:3px 8px; border-radius:8px; font-size:12px; margin-right:6px; }
.badge.ok { background:#065f46; color:#d1fae5; }
.badge.err{ background:#7f1d1d; color:#fecaca; }

/* Couleurs par bande */
.band-20m { color:#60a5fa; font-weight:600; }
.band-40m { color:#34d399; font-weight:600; }
.band-15m { color:#f472b6; font-weight:600; }
.band-10m { color:#f59e0b; font-weight:600; }
.band-2m  { color:#c084fc; font-weight:600; }
.band-70cm{ color:#a3e635; font-weight:600; }
.band-QO-100{ color:#f87171; font-weight:600; }
</style></head><body>
  <h1>📡 Radio Spot Watcher</h1>

  {% if cty_msg %}
    <div class="badge {{ 'ok' if '✅' in cty_msg else 'err' }}">{{ cty_msg }}</div>
  {% endif %}

  <form method="POST">
    <input name="new_call" placeholder="FT8WW">
    <button>➕ Ajouter</button>
  </form>

  <h2>🔍 Watchlist</h2>
  <ul>
  {% for call in watchlist %}
    <li>{{ call }} <a href="/del/{{ call }}"><button>❌</button></a></li>
  {% endfor %}
  {% if not watchlist %}<li><i>Vide</i></li>{% endif %}
  </ul>

  <a href="/update_cty"><button>🔄 Mettre à jour cty.csv</button></a>

  <label>Filtre bande:
    <select id="bandFilter" onchange="applyFilter()">
      <option value="">Toutes</option>
      <option>160m</option><option>80m</option><option>40m</option><option>30m</option>
      <option>20m</option><option>17m</option><option>15m</option><option>12m</option>
      <option>10m</option><option>6m</option><option>4m</option><option>2m</option>
      <option>70cm</option><option>QO-100</option>
    </select>
  </label>

  <div id="layout">
    <div id="maincol">
      <table>
        <tr><th>Heure</th><th>Fréq</th><th>Indicatif</th><th>DXCC</th><th>Bande</th><th>Mode</th></tr>
        <tbody id="tb"><tr><td colspan="6">Chargement...</td></tr></tbody>
      </table>
    </div>

    <div>
      <div id="rssbox">
        <h3>📰 DX News</h3>
        <ul id="rsslist"><li class="muted">Chargement...</li></ul>
      </div>

      <div id="bandchartbox">
        <h3>📊 Band Activity</h3>
        <canvas id="bandChart"></canvas>
      </div>
    </div>
  </div>

<script>
const WATCHLIST = {{ watchlist|tojson }};
let bandFilter="";
let bandChart;

function applyFilter(){bandFilter=document.getElementById('bandFilter').value;}
function inWatchlist(call){return WATCHLIST.includes(String(call||"").toUpperCase());}

function updateChart(spots){
  const counts={};
  for(const s of spots){ if(s.band) counts[s.band]=(counts[s.band]||0)+1; }
  const labels=Object.keys(counts);
  const values=Object.values(counts);
  if(!bandChart){
    const ctx=document.getElementById('bandChart').getContext('2d');
    bandChart=new Chart(ctx,{type:'bar',data:{labels:labels,datasets:[{label:'Spots par bande',data:values,backgroundColor:'#3b82f6'}]},options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});
  }else{
    bandChart.data.labels=labels;
    bandChart.data.datasets[0].data=values;
    bandChart.update();
  }
}

async function refresh(){
  const d=await (await fetch('/spots.json')).json();
  let r='';
  for(const s of d){
    if(bandFilter && s.band!==bandFilter) continue;
    const css=inWatchlist(s.callsign)?'watch':'normal';
    const bandClass=s.band?('band-'+s.band):'';
    r+=`<tr class="${css}">
          <td>${s.timestamp||''}</td>
          <td>${s.frequency||''}</td>
          <td><a href="https://www.qrz.com/db/${s.callsign}" target="_blank">${s.callsign||''}</a></td>
          <td>${s.dxcc||''}</td>
          <td class="${bandClass}">${s.band||''}</td>
          <td>${s.mode||''}</td>
        </tr>`;
  }
  document.getElementById('tb').innerHTML=r||'<tr><td colspan="6">Aucun spot</td></tr>';
  updateChart(d);
}

async function loadRSS(){
  const d=await (await fetch('/rss.json')).json();
  let r='';for(const e of d){r+=`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`;}
  document.getElementById('rsslist').innerHTML=r;
}

setInterval(refresh,5000);
setInterval(loadRSS,600000);
window.onload=()=>{refresh();loadRSS();};
</script>
</body></html>"""
    return render_template_string(html, watchlist=watchlist, cty_msg=cty_msg)

# ---------------------- Boot ----------------------
if __name__ == "__main__":
    load_cty()
    start_bg()
    app.run(host="0.0.0.0", port=8000, debug=False)
