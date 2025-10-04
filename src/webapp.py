#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template_string, jsonify, request
import telnetlib, random, time, threading, requests, re, csv, os
from datetime import datetime
from collections import Counter

app = Flask(__name__)

# ---------------------- Paramètres ----------------------
spots = []
WATCHLIST = ["FT8WW", "3Y0J"]
START_TIME = datetime.utcnow()

DEFAULT_CLUSTER = {"host": "dxcluster.f5len.org", "port": 7373, "login": "F1SMV"}
BACKUP_CLUSTER  = {"host": "dxcluster.ham-radio.ch", "port": 7300, "login": "F1SMV"}

RSS_URL1 = "https://www.dx-world.net/feed/"
RSS_URL2 = "https://feeds.feedburner.com/OnAllBands"
RSS_FALLBACK = "https://www.arrl.org/news/rss"

STATUS = {"connected": False, "last_error": None, "last_update": None}

CTY_URL  = "https://www.country-files.com/cty/cty.csv"
CTY_FILE = os.path.join(os.path.dirname(__file__), "cty.csv")
PREFIX_TO_COUNTRY = {}
SORTED_PREFIXES   = []

# ---------------------- Regex DX universelle ----------------------
# Couvre: "DX de XX: 14074.0 CALL ..." ou "DX de XX> 14074.0 CALL ..."
DX_PATTERN = re.compile(
    r"^DX de\s+([A-Z0-9/-]+)[>:]?\s+(\d+(?:\.\d+)?)\s+([A-Z0-9/]+)\s*(.*)$",
    re.IGNORECASE
)

# ---------------------- DXCC ----------------------
def load_cty():
    """Charge cty.csv -> map préfixe -> pays (longest prefix match)."""
    global PREFIX_TO_COUNTRY, SORTED_PREFIXES
    PREFIX_TO_COUNTRY.clear()
    if not os.path.isfile(CTY_FILE):
        print("[CTY] cty.csv introuvable (pas bloquant).")
        SORTED_PREFIXES = []
        return
    try:
        with open(CTY_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0].startswith("#"):
                    continue
                prefix  = row[0].strip().upper()
                country = row[1].strip() if len(row) > 1 else "?"
                if prefix:
                    PREFIX_TO_COUNTRY[prefix] = country
        SORTED_PREFIXES = sorted(PREFIX_TO_COUNTRY.keys(), key=len, reverse=True)
        print(f"[CTY] {len(PREFIX_TO_COUNTRY)} préfixes chargés.")
    except Exception as e:
        print(f"[CTY] Erreur lecture: {e}")
        PREFIX_TO_COUNTRY = {}
        SORTED_PREFIXES   = []

def update_cty():
    """Télécharge la dernière version de cty.csv et recharge la base."""
    try:
        r = requests.get(CTY_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(CTY_FILE, "wb") as f:
            f.write(r.content)
        load_cty()
        return True
    except Exception as e:
        print(f"[CTY] Erreur update: {e}")
        return False

def all_candidates(cs: str):
    cs = (cs or "").upper().strip()
    cands = {cs}
    parts = cs.split("/")
    if len(parts) == 2:
        cands.add(parts[0])  # ex: EA8 pour EA8/ON4ZZZ
        cands.add(parts[1])  # ex: ON4ZZZ
    for su in ("/P", "/QRP", "/M", "/MM", "/AM"):
        if cs.endswith(su):
            cands.add(cs[:-len(su)])
    return list(cands)

def dxcc_from_call(call: str) -> str:
    if not PREFIX_TO_COUNTRY:
        return "?"
    for cand in all_candidates(call):
        for pref in SORTED_PREFIXES:
            if cand.startswith(pref):
                return PREFIX_TO_COUNTRY.get(pref, "?")
    return "?"

# ---------------------- Bande & Mode ----------------------
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

def detect_mode(text: str, freq: float = None) -> str:
    if text:
        t = text.upper()
        keys = ["FT8","FT4","Q65","MSK144","FSK441","JT65","JT9","WSPR","RTTY","PSK31","PSK","SSTV","CW","SSB","AM","FM","DIGI","USB","LSB"]
        for k in keys:
            if k in t:
                return "SSB" if k in ("USB","LSB") else k
    if freq and 14.07 <= freq <= 14.09:
        return "FT8"
    return "?"

# ---------------------- RSS (tolérant si feedparser absent) ----------------------
def load_rss(url):
    try:
        try:
            import feedparser  # lazy import pour ne pas faire planter l'appli si non installé
        except Exception:
            return [{"title": "Installez feedparser (pip install feedparser)", "link": "#"}]
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"}
        r = requests.get(url, timeout=10, headers=headers)
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        if not feed.entries:
            raise Exception("Aucune entrée RSS")
        return [{"title": e.title, "link": e.link} for e in feed.entries[:10]]
    except Exception as e:
        print(f"[RSS] Erreur sur {url}: {e}")
        return [{"title": "Flux RSS indisponible", "link": "#"}]

def load_rss_with_fallback():
    d1 = load_rss(RSS_URL1)
    d2 = load_rss(RSS_URL2)
    if len(d2) == 1 and d2[0].get("link") == "#":
        d2 = load_rss(RSS_FALLBACK)
    return d1, d2

# ---------------------- API ----------------------
@app.route("/remove_call", methods=["POST"])
def remove_call():
    call = request.json.get("call", "").upper()
    if call in WATCHLIST:
        WATCHLIST.remove(call)
    return jsonify({"watchlist": WATCHLIST})

@app.route("/rss1.json")
def rss1_json():
    d1, _ = load_rss_with_fallback()
    return jsonify(d1)

@app.route("/rss2.json")
def rss2_json():
    _, d2 = load_rss_with_fallback()
    return jsonify(d2)

@app.route("/update_cty")
def update_cty_route():
    ok = update_cty()
    return jsonify({"success": ok, "count": len(PREFIX_TO_COUNTRY)})

@app.route("/dxcc_status.json")
def dxcc_status():
    return jsonify({"prefix_count": len(PREFIX_TO_COUNTRY), "loaded": bool(PREFIX_TO_COUNTRY)})

@app.route("/spots.json")
def spots_json(): return jsonify(spots)

@app.route("/stats.json")
def stats_json():
    dxccs = [s["dxcc"] for s in spots if s.get("dxcc")]
    top5  = Counter(dxccs).most_common(5)
    uptime = (datetime.utcnow() - START_TIME).seconds // 60
    return jsonify({
        "total_spots": len(spots),
        "uptime": uptime,
        "top5": top5,
        "connected": STATUS["connected"]
    })

# ---------------------- Telnet + Fallback ----------------------
def telnet_task(cluster):
    global STATUS
    try:
        tn = telnetlib.Telnet(cluster["host"], cluster["port"], timeout=15)
        time.sleep(1)
        tn.write((cluster["login"] + "\n").encode())
        STATUS["connected"]  = True
        STATUS["last_error"] = None
    except Exception as e:
        STATUS["connected"]  = False
        STATUS["last_error"] = str(e)
        if cluster == DEFAULT_CLUSTER:
            telnet_task(BACKUP_CLUSTER)
        else:
            threading.Thread(target=simulate_spots, daemon=True).start()
        return

    while True:
        try:
            raw = tn.read_until(b"\n", timeout=30).decode(errors="ignore").strip()
            if not raw or not raw.startswith("DX de "):
                continue
            m = DX_PATTERN.match(raw)
            if not m:
                continue
            spotter, freq_str, dx, comment = m.groups()
            try:
                freq = float(freq_str)
            except ValueError:
                continue
            if freq > 1000:
                freq /= 1000.0

            band    = guess_band(freq)
            mode    = detect_mode((comment or "") + " " + raw, freq=freq)
            country = dxcc_from_call(dx)

            spots.insert(0, {
                "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
                "frequency": f"{freq:.3f} MHz",
                "callsign": dx.upper(),
                "dxcc": country,
                "band": band,
                "mode": mode
            })
            del spots[300:]
            STATUS["last_update"] = datetime.utcnow().strftime("%H:%M:%S")
        except Exception as e:
            STATUS["connected"]  = False
            STATUS["last_error"] = str(e)
            break

def simulate_spots():
    demo_calls = ["FT8WW","3Y0J","EA8/ON4ZZZ","DL1ABC","F4ABC","PY0F","VK0DS","A45XR"]
    while True:
        f = random.choice([
            random.uniform(14.0, 14.35),
            random.uniform(7.02, 7.08),
            random.uniform(21.01, 21.09),
            random.uniform(10489.540, 10489.902),
        ])
        call = random.choice(demo_calls)
        spots.insert(0, {
            "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
            "frequency": f"{f:.3f} MHz",
            "callsign": call,
            "dxcc": dxcc_from_call(call),
            "band": guess_band(f),
            "mode": random.choice(["FT8","FT4","SSB","CW","RTTY"])
        })
        del spots[300:]
        time.sleep(8)

# ---------------------- Interface ----------------------
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
.container{display:flex;gap:20px;align-items:flex-start;}
.left{flex:2}
.right{flex:1}
.card{background:#1f2937;border-radius:12px;padding:12px;box-shadow:0 4px 10px rgba(0,0,0,.35);}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0;}
.stat{background:#111827;border-radius:10px;padding:10px;text-align:center;}
.stat h2{margin:0;color:#60a5fa;}
.stat p{margin:4px 0 0;color:#d1d5db;}
th,td{padding:8px 10px;text-align:left;}
th{background:#374151;color:#93c5fd;}
tr:nth-child(even){background:#1a1d25;}
tr:hover{background:#2563eb33;}
td a{color:#60a5fa;text-decoration:none;font-weight:600;}
td a:hover{color:#93c5fd;}
select{background:#1f2937;color:#fff;border:1px solid #374151;border-radius:6px;padding:4px;margin-left:8px;}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:10px;background:#1f2937;margin:3px;}
.badge button{color:#f87171;background:none;border:none;font-weight:bold;cursor:pointer;}
.badge button:hover{color:#ef4444;}
</style></head><body>
<h1>📡 Radio Spot Watcher <span id="conn" style="font-size:16px;color:#f87171;">(connexion…)</span></h1>

<div class="card" style="margin-bottom:10px;">
  <form method="POST" style="margin-bottom:8px;">
    <input name="new_call" placeholder="Ajouter un indicatif à surveiller" style="padding:6px;border-radius:6px;border:1px solid #374151;background:#111827;color:white;">
    <button style="padding:6px 10px;border-radius:6px;border:none;background:#2563eb;color:white;">➕ Ajouter</button>
  </form>
  <div>Watchlist:
    {% for c in watchlist %}
      <span class="badge">{{ c }} <button title="Supprimer" onclick="removeCall('{{ c }}')">🗑️</button></span>
    {% endfor %}
  </div>
  <div style="margin-top:8px;">
    <button id="ctyBtn" style="padding:6px 10px;border-radius:6px;border:none;background:#374151;color:white;">🔄 Mettre à jour DXCC</button>
    <span id="ctyStatus" class="badge">chargement…</span>
  </div>
</div>

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

<div class="container" style="margin-top:10px;">
  <div class="left card">
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr><th>Heure</th><th>Fréq</th><th>Indicatif</th><th>DXCC</th><th>Bande</th><th>Mode</th></tr></thead>
      <tbody id="tb"><tr><td colspan="6">Chargement...</td></tr></tbody>
    </table>
  </div>
  <div class="right">
    <div class="card rss">
      <h3>📰 DX-World</h3>
      <ul id="rsslist1"><li>Chargement…</li></ul>
    </div>
    <div class="card rss" style="margin-top:12px;">
      <h3>📰 OnAllBands (fallback ARRL)</h3>
      <ul id="rsslist2"><li>Chargement…</li></ul>
    </div>
    <div class="card" style="margin-top:12px;">
      <h3>📊 Band Activity</h3>
      <canvas id="barChart"></canvas><br>
      <canvas id="pieChart"></canvas>
    </div>
  </div>
</div>

<script>
let bandFilter="",bandChart,pieChart;
function applyFilter(){bandFilter=document.getElementById("bandFilter").value;}
function inWatchlist(c){return {{ watchlist|tojson }}.includes(String(c||"").toUpperCase());}

async function removeCall(call){
  await fetch('/remove_call',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({call})});
  // Mise à jour visuelle immédiate
  location.reload();
}

document.getElementById('ctyBtn').onclick=async()=>{
  const btn=document.getElementById('ctyBtn');btn.disabled=true;btn.textContent='⏳ Mise à jour...';
  const res=await fetch('/update_cty'); const j=await res.json();
  const el=document.getElementById('ctyStatus');
  if(j.success){el.textContent=`🟢 ${j.count} préfixes`; el.style.color='#34d399';}
  else {el.textContent='🔴 erreur'; el.style.color='#f87171';}
  btn.disabled=false;btn.textContent='🔄 Mettre à jour DXCC';
};

async function dxccState(){
  try{
    const st=await (await fetch('/dxcc_status.json')).json();
    const el=document.getElementById('ctyStatus');
    el.textContent=st.loaded?`🟢 ${st.prefix_count} préfixes`:'🔴 non chargé';
    el.style.color=st.loaded?'#34d399':'#f87171';
  }catch(e){}
}

function updateCharts(spots){
  const counts={}; for(const s of spots){ if(s.band && (!bandFilter||s.band==bandFilter)) counts[s.band]=(counts[s.band]||0)+1; }
  const labels=Object.keys(counts),values=Object.values(counts);
  const colors=labels.map(l=>({"160m":"#78350f","80m":"#7c3aed","40m":"#22c55e","30m":"#06b6d4","20m":"#3b82f6","17m":"#0ea5e9","15m":"#f472b6","12m":"#f59e0b","10m":"#fb923c","6m":"#10b981","4m":"#14b8a6","2m":"#ec4899","70cm":"#bef264","QO-100":"#ef4444"}[l]||"#9ca3af"));
  if(!bandChart){bandChart=new Chart(document.getElementById('barChart'),{type:'bar',data:{labels,datasets:[{data:values,backgroundColor:colors}]},options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});}
  else{bandChart.data.labels=labels;bandChart.data.datasets[0].data=values;bandChart.data.datasets[0].backgroundColor=colors;bandChart.update();}
  if(!pieChart){pieChart=new Chart(document.getElementById('pieChart'),{type:'pie',data:{labels,datasets:[{data:values,backgroundColor:colors}]},options:{plugins:{legend:{position:'bottom'}}}});}
  else{pieChart.data.labels=labels;pieChart.data.datasets[0].data=values;pieChart.data.datasets[0].backgroundColor=colors;pieChart.update();}
}

async function refresh(){
  const d=await (await fetch('/spots.json')).json();
  let r='';
  for(const s of d){
    if(bandFilter && s.band!==bandFilter) continue;
    const css=inWatchlist(s.callsign)?' style="color:#facc15;font-weight:700;"':'';
    r+=`<tr${css}>
      <td>${s.timestamp||''}</td>
      <td>${s.frequency||''}</td>
      <td><a href="https://www.qrz.com/db/${s.callsign}" target="_blank">${s.callsign||''}</a></td>
      <td>${s.dxcc||''}</td>
      <td>${s.band||''}</td>
      <td>${s.mode||'?'}</td>
    </tr>`;
  }
  document.getElementById('tb').innerHTML=r||'<tr><td colspan="6">Aucun spot</td></tr>';
  updateCharts(d);

  const st=await (await fetch('/stats.json')).json();
  document.getElementById('totalSpots').innerText=st.total_spots;
  document.getElementById('uptime').innerText=st.uptime;
  document.getElementById('top5').innerText=st.top5.map(x=>x[0]+"("+x[1]+")").join(", ")||"–";
  document.getElementById('conn').innerText=st.connected?"🟢 Connecté":"🔴 Hors ligne";
  document.getElementById('conn').style.color=st.connected?"#34d399":"#f87171";
}

async function loadRSS(){
  const d1=await (await fetch('/rss1.json')).json();
  const d2=await (await fetch('/rss2.json')).json();
  document.getElementById('rsslist1').innerHTML=d1.map(e=>`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`).join('');
  document.getElementById('rsslist2').innerHTML=d2.map(e=>`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`).join('');
}

setInterval(refresh,5000);
setInterval(loadRSS,600000);
window.onload=()=>{dxccState(); refresh(); loadRSS();};
</script>
</body></html>"""
    return render_template_string(html, watchlist=WATCHLIST)

# ---------------------- Boot ----------------------
if __name__ == "__main__":
    load_cty()

    # Démarre le Telnet
    threading.Thread(target=telnet_task, args=(DEFAULT_CLUSTER,), daemon=True).start()

    # Si le cluster ne répond pas dans 10 s, lance la simulation
    def delayed_simulation():
        time.sleep(10)
        if not STATUS["connected"]:
            print("[INFO] Cluster injoignable, démarrage en mode simulation.")
            threading.Thread(target=simulate_spots, daemon=True).start()
    threading.Thread(target=delayed_simulation, daemon=True).start()

    app.run(host="0.0.0.0", port=8000, debug=False) 