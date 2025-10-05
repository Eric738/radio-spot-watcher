#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template_string, jsonify, request
import telnetlib, random, time, threading, requests, re, csv, os, json
from datetime import datetime, timedelta

app = Flask(__name__)

# ---------------------- ÉTAT ET PARAMS ----------------------
spots = []  # {timestamp, timestamp_full, frequency, callsign, dxcc, band, mode}
WATCHLIST = ["FT8WW", "3Y0J"]

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

# ---------- Most Wanted (ClubLog) ----------
MOST_WANTED_FILE = os.path.join(os.path.dirname(__file__), "most_wanted.json")
MOST_WANTED = []  # liste d’entités (noms)

# Mapping entité DXCC -> code ISO (flagcdn) + emojis fallback (pour PC sans emoji flags)
ISO_CODE_MAP = {
    "Bouvet Island":"bv", "Crozet Island":"tf", "Scarborough Reef":"ph", "North Korea":"kp",
    "Palmyra & Jarvis":"um", "Navassa Island":"um", "Prince Edward & Marion":"za",
    "South Sandwich":"gs", "Macquarie Island":"au", "Peter I Island":"aq", "Kure Island":"um",
    "Heard Island":"hm", "Andaman & Nicobar":"in", "Palestine":"ps", "Johnston Island":"um",
    "Yemen":"ye", "Syria":"sy", "Bhutan":"bt", "Eritrea":"er", "Somalia":"so", "Chad":"td",
    "Djibouti":"dj", "Central African Republic":"cf", "Gabon":"ga", "Equatorial Guinea":"gq",
    "Macao":"mo", "Sudan":"sd", "Oman":"om", "Myanmar":"mm", "Iran":"ir", "Libya":"ly",
    "Western Sahara":"eh", "Guinea":"gn", "Benin":"bj", "Burundi":"bi", "Laos":"la",
    "Cocos (Keeling) Islands":"cc", "Aland Islands":"ax", "Ceuta & Melilla":"es", "Maldives":"mv",
    "Tonga":"to", "Tokelau":"tk", "Tuvalu":"tv", "Wallis & Futuna":"wf", "Vanuatu":"vu",
    "Kiribati":"ki", "Samoa":"ws", "Solomon Islands":"sb", "Comoros":"km", "Sao Tome & Principe":"st",
}
FLAG_EMOJI_MAP = {
    "North Korea":"🇰🇵","Palestine":"🇵🇸","Yemen":"🇾🇪","Syria":"🇸🇾","Bhutan":"🇧🇹","Eritrea":"🇪🇷",
    "Somalia":"🇸🇴","Chad":"🇹🇩","Djibouti":"🇩🇯","Central African Republic":"🇨🇫","Gabon":"🇬🇦",
    "Equatorial Guinea":"🇬🇶","Macao":"🇲🇴","Sudan":"🇸🇩","Oman":"🇴🇲","Myanmar":"🇲🇲","Iran":"🇮🇷",
    "Libya":"🇱🇾","Western Sahara":"🇪🇭","Guinea":"🇬🇳","Benin":"🇧🇯","Burundi":"🇧🇮","Laos":"🇱🇦",
    "Cocos (Keeling) Islands":"🇨🇨","Åland Islands":"🇦🇽","Aland Islands":"🇦🇽","Ceuta & Melilla":"🇪🇸",
    "Maldives":"🇲🇻","Tonga":"🇹🇴","Tokelau":"🇹🇰","Tuvalu":"🇹🇻","Wallis & Futuna":"🇼🇫","Vanuatu":"🇻🇺",
    "Kiribati":"🇰🇮","Samoa":"🇼🇸","Solomon Islands":"🇸🇧","Comoros":"🇰🇲","Sao Tome & Principe":"🇸🇹"
}
MOST_WANTED_DEFAULT = [
  "Bouvet Island","Crozet Island","Scarborough Reef","North Korea","Palmyra & Jarvis",
  "Navassa Island","Prince Edward & Marion","South Sandwich","Macquarie Island",
  "Peter I Island","Kure Island","Heard Island","Andaman & Nicobar","Palestine",
  "Johnston Island","Yemen","Syria","Bhutan","Eritrea","Somalia","Chad","Djibouti",
  "Central African Republic","Gabon","Equatorial Guinea","Macao","Sudan","Oman",
  "Myanmar","Iran","Libya","Western Sahara","Guinea","Benin","Burundi","Laos",
  "Cocos (Keeling) Islands","Aland Islands","Ceuta & Melilla","Maldives","Tonga",
  "Tokelau","Tuvalu","Wallis & Futuna","Vanuatu","Kiribati","Samoa","Solomon Islands",
  "Comoros","Sao Tome & Principe"
]

# ---------------------- REGEX CLUSTER ----------------------
DX_PATTERN = re.compile(
    r"^DX de\s+([A-Z0-9/-]+)[>:]?\s+(\d+(?:\.\d+)?)\s+([A-Z0-9/]+)\s*(.*)$",
    re.IGNORECASE
)

# ---------------------- DXCC ----------------------
def load_cty():
    """Charge cty.csv -> map préfixe -> pays. Télécharge si manquant."""
    global PREFIX_TO_COUNTRY, SORTED_PREFIXES
    PREFIX_TO_COUNTRY.clear()
    if not os.path.isfile(CTY_FILE) or os.path.getsize(CTY_FILE) < 200:
        update_cty()  # tentative de téléchargement

    try:
        with open(CTY_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 2: continue
                p = (row[0] or "").strip().upper()
                c = (row[1] or "").strip()
                if p and c: PREFIX_TO_COUNTRY[p] = c
        SORTED_PREFIXES = sorted(PREFIX_TO_COUNTRY.keys(), key=len, reverse=True)
        print(f"[CTY] {len(PREFIX_TO_COUNTRY)} préfixes chargés.")
    except Exception as e:
        print(f"[CTY] Erreur lecture: {e}")
        PREFIX_TO_COUNTRY = {}
        SORTED_PREFIXES   = []

def update_cty():
    """Télécharge la dernière version de cty.csv et recharge la base."""
    try:
        r = requests.get(CTY_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(CTY_FILE, "wb") as f:
            f.write(r.content)
        # recharge rapide
        tmp = {}
        with open(CTY_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 2: continue
                p = (row[0] or "").strip().upper()
                c = (row[1] or "").strip()
                if p and c: tmp[p] = c
        if tmp:
            global PREFIX_TO_COUNTRY, SORTED_PREFIXES
            PREFIX_TO_COUNTRY = tmp
            SORTED_PREFIXES   = sorted(PREFIX_TO_COUNTRY.keys(), key=len, reverse=True)
        print("[CTY] Mise à jour réussie.")
        return True
    except Exception as e:
        print(f"[CTY] Erreur update: {e}")
        return False

# ---------------------- CALLS ----------------------
def canon_call(cs: str) -> str:
    if not cs:
        return ""
    cs = re.sub(r"\s+", "", cs.upper())
    return re.sub(r"(?:/P|/QRP|/M|/MM|/AM)$", "", cs)

def in_watchlist_norm(cs: str) -> bool:
    cc = canon_call(cs)
    return any(canon_call(x) == cc for x in WATCHLIST)

# ---------------------- DX UTILS ----------------------
def all_candidates(cs: str):
    cs = (cs or "").upper().strip()
    cands = {cs}
    parts = cs.split("/")
    if len(parts) == 2:
        cands |= {parts[0], parts[1]}
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

def guess_band(f: float) -> str:
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
    if 70.0<=f<=71.0: return "4m"
    if 144.0<=f<=148.0: return "2m"
    if 430.0<=f<=440.0: return "70cm"
    if 10489.540<=f<=10489.902: return "QO-100"
    return "?"

def detect_mode(txt: str, f=None):
    if txt:
        t = txt.upper()
        for k in ["FT8","FT4","CW","SSB","FM","DIGI","RTTY","PSK31","JT65","JT9","WSPR","Q65","MSK144","FSK441","USB","LSB"]:
            if k in t: return "SSB" if k in ("USB","LSB") else k
    if f and 14.07<=f<=14.09: return "FT8"
    return "?"

# ---------------------- RSS ----------------------
def load_rss(url):
    try:
        import feedparser
        r = requests.get(url, timeout=12, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        if feed.entries:
            return [{"title": e.title, "link": e.link} for e in feed.entries[:10]]
    except Exception as e:
        print(f"[RSS] {url} -> {e}")
    return [{"title":"Flux RSS indisponible","link":"#"}]

def load_rss_with_fallback():
    d1 = load_rss(RSS_URL1)
    d2 = load_rss(RSS_URL2)
    if len(d2)==1 and d2[0]["link"]=="#":
        d2 = load_rss(RSS_FALLBACK)
    return d1,d2

# ---------------------- CLUBLOG ----------------------
CLUBLOG_URL="https://clublog.org/mostwanted.php"

def fetch_most_wanted_from_clublog(limit=50):
    try:
        r=requests.get(CLUBLOG_URL,timeout=25,headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        html=r.text
        rows=re.findall(r"<tr[^>]*>(.*?)</tr>",html,re.S|re.I)
        entities=[]
        for row in rows:
            cells=re.findall(r"<td[^>]*>(.*?)</td>",row,re.S|re.I)
            if not cells: continue
            for c in cells:
                name=re.sub("<.*?>","",c).strip()
                if len(name)>=3 and not name.isdigit() and "Most Wanted" not in name:
                    entities.append(name); break
        clean=[]
        [clean.append(x) for x in entities if x not in clean]
        return clean[:limit] if clean else None
    except Exception as e:
        print("[ClubLog] Erreur:",e)
        return None

def load_most_wanted():
    if os.path.exists(MOST_WANTED_FILE):
        try: return json.load(open(MOST_WANTED_FILE,encoding="utf-8"))
        except Exception as e: print("[WANTED] cache invalide:",e)
    return MOST_WANTED_DEFAULT

def save_most_wanted(lst):
    try: json.dump(lst,open(MOST_WANTED_FILE,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    except Exception as e: print("[WANTED] save:",e)

def init_most_wanted():
    global MOST_WANTED
    MOST_WANTED = load_most_wanted()
    def weekly():
        while True:
            time.sleep(7*24*3600)  # 1x/semaine
            new = fetch_most_wanted_from_clublog(50)
            if new: save_most_wanted(new); MOST_WANTED[:] = new
    threading.Thread(target=weekly, daemon=True).start()

def flag_png_for(country: str) -> str:
    code = ISO_CODE_MAP.get(country)
    return f"https://flagcdn.com/24x18/{code}.png" if code else ""

def flag_emoji_for(country: str) -> str:
    return FLAG_EMOJI_MAP.get(country, "🌐")

# ---------------------- MAINTENANCE SPOTS ----------------------
def cleanup_spots():
    """Purge spots > 5 min (impacte le halo vert des 'Most Wanted')."""
    while True:
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        def is_recent(s):
            try:
                ts = datetime.strptime(s.get("timestamp_full",""), "%Y-%m-%d %H:%M:%S")
                return ts >= cutoff
            except Exception:
                return True
        spots[:] = [s for s in spots if is_recent(s)]
        time.sleep(60)

# ---------------------- API ----------------------
@app.route("/remove_call", methods=["POST"])
def remove_call():
    incoming = request.json.get("call", "")
    target = canon_call(incoming)
    idx = next((i for i, val in enumerate(WATCHLIST) if canon_call(val) == target), None)
    if idx is not None:
        del WATCHLIST[idx]
        return jsonify({"ok": True, "watchlist": WATCHLIST})
    return jsonify({"ok": False, "watchlist": WATCHLIST}), 404

@app.route("/update_cty")
def update_cty_route():
    ok = update_cty()
    return jsonify({"success": ok, "count": len(PREFIX_TO_COUNTRY)})

@app.route("/dxcc_status.json")
def dxcc_status():
    return jsonify({"prefix_count": len(PREFIX_TO_COUNTRY), "loaded": bool(PREFIX_TO_COUNTRY)})

@app.route("/spots.json")
def spots_json():
    return jsonify(spots)

@app.route("/rss1.json")
def rss1_json():
    d1,_ = load_rss_with_fallback()
    return jsonify(d1)

@app.route("/rss2.json")
def rss2_json():
    _,d2 = load_rss_with_fallback()
    return jsonify(d2)

@app.route("/wanted.json")
def wanted_json():
    active = {}
    for s in spots:
        dxcc = s.get("dxcc") or "?"
        if dxcc in MOST_WANTED and dxcc not in active:
            active[dxcc] = {"callsign": s.get("callsign"), "freq": s.get("frequency")}
    out = []
    for c in MOST_WANTED[:50]:
        out.append({
            "country": c,
            "flag_png": flag_png_for(c),
            "flag_emoji": flag_emoji_for(c),
            "active": c in active,
            "callsign": active.get(c,{}).get("callsign"),
            "freq": active.get(c,{}).get("freq")
        })
    return jsonify({"list": out})

@app.route("/wanted_recent.json")
def wanted_recent():
    """Most Wanted entendus dans les 3 dernières heures (liste triée récents -> anciens)."""
    now = datetime.utcnow()
    recent = []
    for s in spots:
        try:
            ts = datetime.strptime(s["timestamp_full"], "%Y-%m-%d %H:%M:%S")
            if (now - ts) < timedelta(hours=3) and (s["dxcc"] in MOST_WANTED):
                country = s["dxcc"]
                rec = {
                    "timestamp": s["timestamp_full"],
                    "time": ts.strftime("%H:%M"),
                    "callsign": s["callsign"],
                    "dxcc": country,
                    "freq": s["frequency"],
                    "mode": s["mode"],
                    "flag_png": flag_png_for(country),
                    "flag_emoji": flag_emoji_for(country)
                }
                recent.append(rec)
        except Exception:
            pass
    recent.sort(key=lambda x: x["timestamp"], reverse=True)
    return jsonify({"list": recent[:30]})

@app.route("/stats.json")
def stats_json():
    return jsonify({"connected": STATUS["connected"], "last_update": STATUS["last_update"]})

# ---------------------- TELNET ----------------------
def telnet_task(cluster):
    try:
        tn=telnetlib.Telnet(cluster["host"], cluster["port"], timeout=20)
        time.sleep(1)
        tn.write((cluster["login"]+"\n").encode())
        STATUS["connected"]=True
        STATUS["last_error"]=None
    except Exception as e:
        STATUS["connected"]=False
        STATUS["last_error"]=str(e)
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
            _, freq_str, dx, comment = m.groups()
            try:
                f = float(freq_str)
            except Exception:
                continue
            if f > 1000:
                f /= 1000.0
            band = guess_band(f)
            mode = detect_mode(comment, f)
            country = dxcc_from_call(dx)
            now = datetime.utcnow()
            spots.insert(0, {
                "timestamp": now.strftime("%H:%M:%S"),
                "timestamp_full": now.strftime("%Y-%m-%d %H:%M:%S"),
                "frequency": f"{f:.3f} MHz",
                "callsign": (dx or "").upper(),
                "dxcc": country,
                "band": band,
                "mode": mode or "?"
            })
            del spots[300:]
            STATUS["last_update"] = now.strftime("%H:%M:%S")
        except Exception as e:
            STATUS["connected"]=False
            STATUS["last_error"]=str(e)
            break

# ---------------------- SIMULATION (fallback) ----------------------
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
        now = datetime.utcnow()
        spots.insert(0, {
            "timestamp": now.strftime("%H:%M:%S"),
            "timestamp_full": now.strftime("%Y-%m-%d %H:%M:%S"),
            "frequency": f"{f:.3f} MHz",
            "callsign": call,
            "dxcc": dxcc_from_call(call),
            "band": guess_band(f),
            "mode": random.choice(["FT8","FT4","SSB","CW","RTTY"])
        })
        del spots[300:]
        time.sleep(8)

# ---------------------- UI ----------------------
@app.route("/", methods=["GET","POST"])
def index():
    if request.method == "POST":
        new_call = request.form.get("new_call","").upper().strip()
        if new_call and not in_watchlist_norm(new_call):
            WATCHLIST.append(new_call)

    html = """<!DOCTYPE html><html><head>
<meta charset="utf-8"><title>Radio Spot Watcher</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{
  --bg:#181b24; --card:#1f2531; --muted:#cbd5e1; --primary:#60a5fa; --primary-600:#3b82f6; --ok:#22c55e; --err:#ef4444; --amber:#f59e0b;
}
*{box-sizing:border-box} body{background:var(--bg);color:#e5e7eb;font-family:Inter,system-ui,Segoe UI,Arial,sans-serif;margin:0;padding:18px;}
h1{margin:0 0 14px 0;font-weight:800;letter-spacing:.3px;display:flex;align-items:center;gap:10px;}
h1 .pill{font-size:14px;padding:6px 10px;border-radius:999px;background:#121620;color:#9fb3d9}
.card{background:rgba(31,37,49,.85);backdrop-filter:blur(6px);border-radius:16px;padding:12px;box-shadow:0 10px 30px rgba(0,0,0,.25);}
.topband{display:grid;grid-template-columns:1.6fr 1.2fr .9fr;gap:14px;width:100%;}
.top-left{display:flex;flex-direction:column;gap:10px}
.formline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.formline input{padding:9px 10px;border-radius:10px;border:1px solid #2b3342;background:#121620;color:#fff;min-width:230px}
.formline button{padding:9px 12px;border-radius:10px;border:none;background:linear-gradient(135deg,var(--primary),var(--primary-600));color:white;font-weight:700;cursor:pointer;transition:transform .08s ease}
.formline button:hover{transform:translateY(-1px)}
.watchlist{display:flex;flex-wrap:wrap;gap:8px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:#151b26;border:1px solid #2b3342}
.badge button{color:#f87171;background:none;border:none;font-weight:700;cursor:pointer}
.badge button:hover{color:#ef4444}
.graphs{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px}
.graph-card{padding:10px;border:1px solid #2b3342}

.top-mid{display:flex;flex-direction:column;gap:10px}
.kpis{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.kpill{display:flex;gap:8px;align-items:center;padding:8px 12px;border-radius:999px;background:#141a23;border:1px solid #2b3342}
.kpill strong{color:#e5f2ff}
#ctyBtn{padding:8px 10px;border-radius:10px;border:1px solid #365172;background:#142034;color:#dbeafe;cursor:pointer}
#ctyBtn:hover{background:#0f1a2b}
#ctyStatus{margin-left:6px}

.main{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-top:14px}
table{width:100%;border-collapse:collapse}
th,td{padding:9px 10px;text-align:left}
th{background:#232b3a;color:#b7d3ff;position:sticky;top:0}
tbody tr:nth-child(even){background:#18202c}
tbody tr:hover{background:#263247}
td a{color:#9cc7ff;text-decoration:none;font-weight:700}
td a:hover{color:white;text-decoration:underline}
select{background:#121620;color:#fff;border:1px solid #2b3342;border-radius:10px;padding:6px}

.section-title{margin:6px 0 8px 0;color:#dbeafe;font-weight:800}
.wanted-item{display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-bottom:1px solid #101521}
.wanted-item.active{background:rgba(34,197,94,0.13);color:#86efac;border-radius:8px}
.wanted-name{display:flex;gap:8px;align-items:center;font-weight:700}
.wanted-spot{font-size:.92rem;opacity:.95}
img.flag{width:24px;height:18px;border-radius:3px;vertical-align:middle}
.rss a{color:#e5e7eb;text-decoration:none}
.rss a:hover{color:#bcd7ff;text-decoration:underline}

/* Néon rétro pour Most Wanted récents */
.neon{font-weight:700}
.neon.green{color:#4ade80;text-shadow:0 0 8px rgba(34,197,94,.9)}
.neon.amber{color:#facc15;text-shadow:0 0 8px rgba(245,158,11,.9)}
.neon.gray{color:#94a3b8}
</style>
</head><body>
<h1>📡 Radio Spot Watcher <span id="conn" class="pill">(connexion…)</span></h1>

<!-- BANDEAU DASHBOARD -->
<div class="topband">
  <!-- left: add/watchlist + graphs -->
  <div class="top-left card">
    <div class="formline">
      <form method="POST" style="display:flex;gap:8px;flex-wrap:wrap">
        <input name="new_call" placeholder="Ajouter un indicatif à surveiller">
        <button>➕ Ajouter</button>
      </form>
      <label>Filtrer :
        <select id="bandFilter" onchange="applyFilter()">
          <option value="">Toutes</option>
          <option>160m</option><option>80m</option><option>40m</option><option>30m</option>
          <option>20m</option><option>17m</option><option>15m</option><option>12m</option>
          <option>10m</option><option>6m</option><option>4m</option><option>2m</option>
          <option>70cm</option><option>QO-100</option>
        </select>
      </label>
    </div>
    <div class="watchlist">
      {% for c in watchlist %}
        <span class="badge">{{ c }} <button title="Supprimer" onclick='removeCall({{ c|tojson }})'>🗑️</button></span>
      {% endfor %}
    </div>
    <div class="graphs">
      <div class="card graph-card"><canvas id="barChart"></canvas></div>
      <div class="card graph-card"><canvas id="pieChart"></canvas></div>
    </div>
  </div>

  <!-- middle: badges + DXCC update -->
  <div class="top-mid card">
    <div class="kpis">
      <div class="kpill">🌐 DXCC : <strong id="dxccCount">—</strong></div>
      <div class="kpill">🟢 Cluster : <strong id="conn2">Hors ligne</strong></div>
      <div class="kpill">⏱️ Dernière MAJ : <strong id="lastUpd">—</strong></div>
    </div>
    <div>
      <button id="ctyBtn">🔄 Mettre à jour DXCC</button>
      <span id="ctyStatus"></span>
    </div>
  </div>

  <!-- right: Most Wanted entendus 3h -->
  <div class="card" id="recentWanted" style="overflow:auto;max-height:320px;">
    <div class="section-title">💡 Most Wanted entendus (3 dernières heures)</div>
    <div id="recentList"><div>Chargement…</div></div>
  </div>
</div>

<!-- PRINCIPAL -->
<div class="main">
  <div class="card">
    <table>
      <thead><tr><th>Heure</th><th>Fréq</th><th>Indicatif</th><th>DXCC</th><th>Bande</th><th>Mode</th></tr></thead>
      <tbody id="tb"><tr><td colspan="6">Chargement...</td></tr></tbody>
    </table>
  </div>

  <div>
    <div class="card">
      <div class="section-title">🌎 Most Wanted DXCC (ClubLog Top 50)</div>
      <div id="wantedList"><div>Chargement…</div></div>
    </div>

    <div class="card rss" style="margin-top:12px;">
      <h3 class="section-title">📰 DX-World</h3>
      <ul id="rsslist1"><li>Chargement…</li></ul>
    </div>
    <div class="card rss" style="margin-top:12px;">
      <h3 class="section-title">📰 OnAllBands (fallback ARRL)</h3>
      <ul id="rsslist2"><li>Chargement…</li></ul>
    </div>
  </div>
</div>

<script>
let bandFilter="",bandChart,pieChart;

function applyFilter(){bandFilter=document.getElementById("bandFilter").value;}

function inWatchlist(c){return {{ watchlist|tojson }}.includes(String(c||"").toUpperCase());}

async function removeCall(call){
  const res = await fetch('/remove_call',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({call})});
  if(res.ok){location.reload();} else {alert("Impossible de supprimer "+call);}
}

async function refreshDXCCCount(){
  const j = await (await fetch('/dxcc_status.json')).json();
  document.getElementById('dxccCount').textContent = j.prefix_count || 0;
}

document.getElementById('ctyBtn').onclick=async()=>{
  const btn=document.getElementById('ctyBtn');btn.disabled=true;btn.textContent='⏳ Mise à jour...';
  try{
    const res=await fetch('/update_cty');
    const j=await res.json();
    await refreshDXCCCount();
    const el=document.getElementById('ctyStatus');
    if(j.success){el.textContent='🟢 DXCC à jour'; el.style.color='#22c55e';}
    else{el.textContent='🔴 Échec MAJ (voir logs)'; el.style.color='#ef4444';}
  }catch(e){
    const el=document.getElementById('ctyStatus'); el.textContent='🔴 ERREUR réseau'; el.style.color='#ef4444';
  }finally{
    btn.disabled=false;btn.textContent='🔄 Mettre à jour DXCC';
  }
};

function updateCharts(spots){
  const counts={};
  for(const s of spots){ if(s.band && (!bandFilter||s.band==bandFilter)) counts[s.band]=(counts[s.band]||0)+1; }
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
    const css=inWatchlist(s.callsign)?' style="color:#facc15;font-weight:800;"':'';
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
  const conn=document.getElementById('conn'); const conn2=document.getElementById('conn2');
  conn.innerText=st.connected?"🟢 Connecté":"🔴 Hors ligne";
  conn2.innerText=st.connected?"Connecté":"Hors ligne";
  document.getElementById('lastUpd').innerText = st.last_update || '—';
}

async function loadRSS(){
  const d1=await (await fetch('/rss1.json')).json();
  const d2=await (await fetch('/rss2.json')).json();
  document.getElementById('rsslist1').innerHTML=d1.map(e=>`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`).join('');
  document.getElementById('rsslist2').innerHTML=d2.map(e=>`<li><a href="${e.link}" target="_blank">${e.title}</a></li>`).join('');
}

async function loadWanted(){
  const data = await (await fetch('/wanted.json')).json();
  const list = data.list || [];
  let html='';
  for(const it of list){
    const cls = it.active ? 'wanted-item active' : 'wanted-item';
    const flagImg = it.flag_png ? `<img class="flag" src="${it.flag_png}" onerror="this.style.display='none'">` : '';
    const flagEmoji = `<span style="margin-left:6px">${it.flag_emoji||'🌐'}</span>`;
    const left = `<div class="wanted-name">${flagImg}${flagEmoji}<span>${it.country}</span></div>`;
    const right = it.active ? `<span class="wanted-spot">🟢 ${it.callsign} @ ${it.freq}</span>` : `<span class="wanted-spot" style="opacity:.6">(no spot)</span>`;
    html += `<div class="${cls}">${left}${right}</div>`;
  }
  document.getElementById('wantedList').innerHTML = html || '<div>Aucune donnée</div>';
}

// 🔆 Most Wanted entendus dans les 3 dernières heures (néon rétro)
async function loadRecentWanted(){
  const data = await (await fetch('/wanted_recent.json')).json();
  const list = data.list || [];
  let html='';
  const now = new Date();
  for(const it of list){
    const ageMin = (now - new Date(it.timestamp.replace(' ', 'T')+'Z')) / 60000;
    const neonClass = ageMin < 15 ? 'neon green' : ageMin < 180 ? 'neon amber' : 'neon gray';
    const flagImg = it.flag_png ? `<img class="flag" src="${it.flag_png}" onerror="this.style.display='none'">` : '';
    const flagEmoji = `<span style="margin-left:6px">${it.flag_emoji||'🌐'}</span>`;
    html += `<div class="${neonClass}" style="padding:4px 0;">
      ${flagImg}${flagEmoji} ${it.dxcc} — <b>${it.callsign}</b> — ${it.freq} — ${it.mode} — ${it.time}Z
    </div>`;
  }
  document.getElementById('recentList').innerHTML = html || '<div class="neon gray">Aucun DX rare signalé</div>';
}

setInterval(refresh,5000);
setInterval(loadRSS,600000);
setInterval(loadWanted,20000);
setInterval(loadRecentWanted,60000);
window.onload=()=>{ refresh(); loadRSS(); loadWanted(); refreshDXCCCount(); loadRecentWanted(); };
</script>
</body></html>"""
    return render_template_string(html, watchlist=WATCHLIST)

# ---------------------- BOOT ----------------------
if __name__ == "__main__":
    load_cty()
    init_most_wanted()
    threading.Thread(target=cleanup_spots, daemon=True).start()
    threading.Thread(target=telnet_task, args=(DEFAULT_CLUSTER,), daemon=True).start()

    # Fallback simulation si pas de connexion après 10s
    def delayed_sim():
        time.sleep(10)
        if not STATUS["connected"]:
            print("[INFO] Cluster injoignable, simulation activée.")
            threading.Thread(target=simulate_spots, daemon=True).start()
    threading.Thread(target=delayed_sim, daemon=True).start()

    app.run(host="0.0.0.0", port=8000, debug=False) 