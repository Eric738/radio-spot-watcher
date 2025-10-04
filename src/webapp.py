 #!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template_string, jsonify, request
import telnetlib, feedparser, random, time, threading, requests, re
from datetime import datetime
from collections import Counter

app = Flask(__name__)

# ---------------------- Paramètres ----------------------
spots = []
WATCHLIST = ["FT8WW", "3Y0J"]
START_TIME = datetime.utcnow()

DEFAULT_CLUSTER = {"host": "dxcluster.f5len.org", "port": 7373, "login": "F1SMV"}  # ✅ Ton indicatif
BACKUP_CLUSTER  = {"host": "dxcluster.ham-radio.ch", "port": 7300, "login": "F1SMV"}

RSS_URL1 = "https://www.dx-world.net/feed/"
RSS_URL2 = "https://www.amsat.org/feed"

STATUS = {"connected": False, "last_error": None, "last_update": None}
DXCC_LIST = ["France","Germany","USA","Japan","Spain","Italy","UK","Australia"]

# Regex pour analyser les lignes DX
DX_PATTERN = re.compile(r"^DX de\s+([A-Z0-9/]+):\s+(\d+\.\d+)\s+([A-Z0-9/]+)", re.IGNORECASE)

# ---------------------- Fonctions ----------------------
def guess_band(freq_mhz: float) -> str:
    f = freq_mhz
    if 1.8   <= f <= 2.0: return "160m"
    if 3.5   <= f <= 4.0: return "80m"
    if 7.0   <= f <= 7.3: return "40m"
    if 10.1  <= f <= 10.15: return "30m"
    if 14.0  <= f <= 14.35: return "20m"
    if 18.068<= f <= 18.168: return "17m"
    if 21.0  <= f <= 21.45: return "15m"
    if 24.89 <= f <= 24.99: return "12m"
    if 28.0  <= f <= 29.7:  return "10m"
    if 50.0  <= f <= 54.0:  return "6m"
    if 70.0  <= f <= 71.0:  return "4m"
    if 144.0 <= f <= 148.0: return "2m"
    if 430.0 <= f <= 440.0: return "70cm"
    if 10489.540 <= f <= 10489.902: return "QO-100"
    return "?"

def load_rss(url):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        feed = feedparser.parse(r.text)
        return [{"title": e.title, "link": e.link} for e in feed.entries[:10]]
    except Exception as e:
        print(f"[RSS] Erreur sur {url}: {e}")
        return [{"title": f"Flux indisponible ({url})", "link": "#"}]

@app.route("/rss1.json")
def rss1_json(): return jsonify(load_rss(RSS_URL1))

@app.route("/rss2.json")
def rss2_json(): return jsonify(load_rss(RSS_URL2))

@app.route("/spots.json")
def spots_json(): return jsonify(spots)

@app.route("/stats.json")
def stats_json():
    dxccs = [s["dxcc"] for s in spots if s.get("dxcc")]
    top5 = Counter(dxccs).most_common(5)
    uptime = (datetime.utcnow() - START_TIME).seconds // 60
    return jsonify({
        "total_spots": len(spots),
        "uptime": uptime,
        "top5": top5,
        "connected": STATUS["connected"]
    })

# ---------------------- Telnet ----------------------
def telnet_task(cluster):
    """Connexion au cluster et réception des spots DX"""
    global STATUS
    try:
        print(f"[TELNET] Connexion à {cluster['host']}:{cluster['port']}…")
        tn = telnetlib.Telnet(cluster["host"], cluster["port"], timeout=15)
        time.sleep(1)
        tn.write((cluster["login"] + "\n").encode())
        STATUS["connected"] = True
        STATUS["last_error"] = None
        print("[TELNET] Connecté avec succès ✅")
    except Exception as e:
        STATUS["connected"] = False
        STATUS["last_error"] = str(e)
        print(f"[TELNET] Erreur: {e}")
        if cluster == DEFAULT_CLUSTER:
            print("[TELNET] Tentative sur cluster de secours…")
            telnet_task(BACKUP_CLUSTER)
        else:
            print("[TELNET] Échec → passage en mode simulation")
            threading.Thread(target=simulate_spots, daemon=True).start()
        return

    while True:
        try:
            raw = tn.read_until(b"\n", timeout=30).decode(errors="ignore").strip()
            if not raw:
                continue
            m = DX_PATTERN.match(raw)
            if not m:
                continue  # ignore les lignes non conformes
            spotter, freq_str, dx = m.groups()
            try:
                freq = float(freq_str)
            except ValueError:
                continue
            if freq > 1000:
                freq /= 1000.0
            spots.insert(0, {
                "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
                "frequency": f"{freq:.3f} MHz",
                "callsign": dx,
                "dxcc": random.choice(DXCC_LIST),
                "band": guess_band(freq),
                "mode": "Cluster"
            })
            del spots[300:]
            STATUS["last_update"] = datetime.utcnow().strftime("%H:%M:%S")
        except Exception as e:
            STATUS["connected"] = False
            STATUS["last_error"] = str(e)
            print(f"[TELNET] Erreur lecture: {e}")
            break

# ---------------------- Simulation ----------------------
def simulate_spots():
    print("[SIMU] Mode simulation activé")
    while True:
        f = random.uniform(14.0,14.35)
        call = random.choice(["FT8WW","3Y0J","K1ABC","F5LEN","PY0F","VK0DS"])
        spots.insert(0, {
            "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            "frequency": f"{f:.3f} MHz",
            "callsign": call,
            "dxcc": random.choice(DXCC_LIST),
            "band": guess_band(f),
            "mode": "FT8"
        })
        del spots[300:]
        time.sleep(10)

def start_telnet():
    threading.Thread(target=telnet_task, args=(DEFAULT_CLUSTER,), daemon=True).start()

# ---------------------- Interface Web ----------------------
@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        new_call = request.form.get("new_call","").upper().strip()
        if new_call and new_call not in WATCHLIST:
            WATCHLIST.append(new_call)

    html = """<!DOCTYPE html><html><head>
<meta charset="utf-8"><title>Radio Spot Watcher</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body{background:#0f1115;color:#e5e7eb;font-family:Inter,Arial,sans-serif;margin:0;padding:20px;}
h1{color:#3b82f6;margin-bottom:10px;}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin:20px 0;}
.stat{background:#1f2937;border-radius:10px;padding:12px;text-align:center;}
.stat h2{margin:0;color:#60a5fa;}
.stat p{margin:5px 0 0;color:#d1d5db;}
.table-card{background:#1f2937;padding:12px;border-radius:12px;}
th,td{padding:8px 10px;text-align:left;}
th{background:#374151;color:#93c5fd;}
tr:nth-child(even){background:#1a1d25;}
tr:hover{background:#2563eb33;}
td a{color:#60a5fa;font-weight:600;text-decoration:none;}
td a:hover{color:#93c5fd;}
.watch{color:#facc15 !important;font-weight:700;}
.rss h3{color:white;margin-bottom:6px;}
.rss a{color:white;text-decoration:none;}
</style></head><body>
<h1>📡 Radio Spot Watcher <span id="conn" style="font-size:16px;color:#f87171;">(connexion…)</span></h1>

<form method="POST">
  <input name="new_call" placeholder="Ajouter un indicatif" style="padding:5px;border-radius:6px;border:1px solid #374151;background:#111827;color:white;">
  <button style="padding:5px 10px;border-radius:6px;border:none;background:#2563eb;color:white;">➕ Ajouter</button>
</form>
<ul>{% for c in watchlist %}<li>{{ c }}</li>{% endfor %}</ul>

<div class="stats">
  <div class="stat"><h2 id="totalSpots">0</h2><p>Total spots</p></div>
  <div class="stat"><h2 id="uptime">0</h2><p>Uptime (min)</p></div>
  <div class="stat"><h2 id="top5">–</h2><p>Top DXCC</p></div>
</div>

<label>Filtrer par bande :
<select id="bandFilter" onchange="applyFilter()">
  <option value="">Toutes</option>
  <option>160m</option><option>80m</option><option>40m</option><option>30m</option>
  <option>20m</option><option>17m</option><option>15m</option><option>12m</option>
  <option>10m</option><option>6m</option><option>4m</option><option>2m</option>
  <option>70cm</option><option>QO-100</option>
</select></label>

<div style="display:flex;gap:20px;align-items:flex-start;">
  <div style="flex:2" class="table-card">
    <table style="width:100%;border-collapse:collapse;">
      <tr><th>Heure</th><th>Fréq</th><th>Indicatif</th><th>DXCC</th><th>Bande</th><th>Mode</th></tr>
      <tbody id="tb"><tr><td colspan="6">Chargement...</td></tr></tbody>
    </table>
  </div>
  <div style="flex:1;">
    <div class="rss"><h3>📰 DX World</h3><ul id="rsslist1"><li>Chargement...</li></ul></div>
    <div class="rss"><h3>🛰️ AMSAT</h3><ul id="rsslist2"><li>Chargement...</li></ul></div>
    <div><canvas id="barChart"></canvas><canvas id="pieChart"></canvas></div>
  </div>
</div>

<script>
let bandFilter="",bandChart,pieChart;
function applyFilter(){bandFilter=document.getElementById("bandFilter").value;}
function inWatchlist(c){return {{ watchlist|tojson }}.includes(String(c||"").toUpperCase());}

function updateCharts(spots){
  const counts={}; for(const s of spots){ if(s.band && (!bandFilter||s.band==bandFilter)) counts[s.band]=(counts[s.band]||0)+1; }
  const labels=Object.keys(counts),values=Object.values(counts);
  const colors=labels.map(l=>({"160m":"#78350f","80m":"#7c3aed","40m":"#22c55e","30m":"#06b6d4","20m":"#3b82f6","17m":"#0ea5e9","15m":"#f472b6","12m":"#f59e0b","10m":"#fb923c","6m":"#10b981","2m":"#ec4899","70cm":"#bef264","QO-100":"#ef4444"}[l]||"#9ca3af"));
  if(!bandChart){bandChart=new Chart(document.getElementById('barChart'),{type:'bar',data:{labels,datasets:[{data:values,backgroundColor:colors}]},options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});}else{bandChart.data.labels=labels;bandChart.data.datasets[0].data=values;bandChart.update();}
  if(!pieChart){pieChart=new Chart(document.getElementById('pieChart'),{type:'pie',data:{labels,datasets:[{data:values,backgroundColor:colors}]}});}else{pieChart.data.labels=labels;pieChart.data.datasets[0].data=values;pieChart.update();}
}

async function refresh(){
  const d=await (await fetch('/spots.json')).json();
  let r=''; for(const s of d){if(bandFilter&&s.band!==bandFilter)continue;const css=inWatchlist(s.callsign)?'watch':'';r+=`<tr class="${css}"><td>${s.timestamp}</td><td>${s.frequency}</td><td><a href="https://www.qrz.com/db/${s.callsign}" target="_blank">${s.callsign}</a></td><td>${s.dxcc}</td><td>${s.band}</td><td>${s.mode}</td></tr>`;}
  document.getElementById('tb').innerHTML=r||'<tr><td colspan="6">Aucun spot</td></tr>';
  updateCharts(d);
  const stats=await (await fetch('/stats.json')).json();
  document.getElementById('totalSpots').innerText=stats.total_spots;
  document.getElementById('uptime').innerText=stats.uptime;
  document.getElementById('top5').innerText=stats.top5.map(x=>x[0]+"("+x[1]+")").join(", ")||"–";
  document.getElementById('conn').innerText=stats.connected?"🟢 Connecté":"🔴 Hors ligne";
  document.getElementById('conn').style.color=stats.connected?"#4ade80":"#f87171";
}

async function loadRSS(){
  const d1=await (await fetch('/rss1.json')).json();
  const d2=await (await fetch('/rss2.json')).json();
  document.getElementById('rsslist1').innerHTML=d1.map(e=>`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`).join('');
  document.getElementById('rsslist2').innerHTML=d2.map(e=>`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`).join('');
}

setInterval(refresh,5000);
setInterval(loadRSS,600000);
window.onload=()=>{refresh();loadRSS();};
</script></body></html>"""
    return render_template_string(html, watchlist=WATCHLIST)

# ---------------------- Boot ----------------------
if __name__ == "__main__":
    threading.Thread(target=start_telnet, daemon=True).start()
    app.run(host="0.0.0.0", port=8000, debug=False)