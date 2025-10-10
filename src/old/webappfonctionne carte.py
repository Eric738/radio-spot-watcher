#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template_string, jsonify, request
import telnetlib, random, time, threading, requests, re, csv, os, json, socket
from datetime import datetime, timedelta

app = Flask(__name__)

# ---------------------- ÉTAT ET PARAMS ----------------------
spots = []  # {timestamp, timestamp_full, frequency, callsign, dxcc, band, mode, lat, lon}
WATCHLIST = ["FT8WW", "3Y0J"]

DEFAULT_CLUSTER = {"host": "dxcluster.f5len.org", "port": 7373, "login": "F1SMV"}
BACKUP_CLUSTER  = {"host": "dxcluster.ham-radio.ch", "port": 7300, "login": "F1SMV"}

RSS_URL1 = "https://www.dx-world.net/feed/"
RSS_URL2 = "https://feeds.feedburner.com/OnAllBands"
RSS_FALLBACK = "https://www.arrl.org/news/rss"

STATUS = {
    "connected": False,
    "last_error": None,
    "last_update": None,
    "latency_ms": None,      # latence TCP (ms) vers le cluster
    "solar": {"sfi": None, "kp": None, "sunspots": None, "updated": None}
}

CTY_URL  = "https://www.country-files.com/cty/cty.csv"
CTY_FILE = os.path.join(os.path.dirname(__file__), "cty.csv")
PREFIX_TO_COUNTRY = {}
SORTED_PREFIXES   = []

# ---------- Most Wanted (ClubLog) ----------
MOST_WANTED_FILE = os.path.join(os.path.dirname(__file__), "most_wanted.json")
MOST_WANTED = []  # liste d’entités (noms)

# Mapping entité DXCC -> code ISO (flagcdn) + emojis fallback
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

# ---------------------- CENTROÏDES DXCC -> (lat, lon) ----------------------
# NOTE: simplifié. Suffisant pour affichage global. Peut être remplacé plus tard par un parseur cty.csv
# enrichi (si colonnes lat/lon disponibles).
COUNTRY_CENTROIDS = {
    # Rares / Most Wanted
    "Bouvet Island": (-54.42, 3.36),
    "Crozet Island": (-46.41, 51.77),
    "Scarborough Reef": (15.08, 117.75),
    "North Korea": (40.34, 127.51),
    "Palmyra & Jarvis": (5.88, -162.08),
    "Navassa Island": (18.40, -75.01),
    "Prince Edward & Marion": (-46.90, 37.75),
    "South Sandwich": (-57.79, -26.44),
    "Macquarie Island": (-54.62, 158.85),
    "Peter I Island": (-68.77, -90.58),
    "Kure Island": (28.40, -178.30),
    "Heard Island": (-53.10, 73.50),
    "Andaman & Nicobar": (10.3, 92.6),
    "Palestine": (31.9, 35.2),
    "Johnston Island": (16.73, -169.53),
    "Yemen": (15.55, 48.52),
    "Syria": (35.0, 38.9),
    "Bhutan": (27.4, 90.4),
    "Eritrea": (15.18, 39.78),
    "Somalia": (5.15, 46.20),
    "Chad": (15.45, 18.73),
    "Djibouti": (11.83, 42.59),
    "Central African Republic": (6.61, 20.94),
    "Gabon": (-0.80, 11.60),
    "Equatorial Guinea": (1.65, 10.35),
    "Macao": (22.20, 113.55),
    "Sudan": (15.61, 32.53),
    "Oman": (21.47, 55.98),
    "Myanmar": (21.20, 96.9),
    "Iran": (32.42, 53.68),
    "Libya": (27.04, 17.64),
    "Western Sahara": (24.21, -13.70),
    "Guinea": (10.44, -9.31),
    "Benin": (9.31, 2.31),
    "Burundi": (-3.36, 29.92),
    "Laos": (19.86, 102.49),
    "Cocos (Keeling) Islands": (-12.17, 96.84),
    "Aland Islands": (60.23, 20.07),
    "Ceuta & Melilla": (35.29, -2.95),
    "Maldives": (3.2, 73.2),
    "Tonga": (-21.2, -175.2),
    "Tokelau": (-9.20, -171.85),
    "Tuvalu": (-8.52, 179.20),
    "Wallis & Futuna": (-13.30, -176.20),
    "Vanuatu": (-16.28, 167.73),
    "Kiribati": (1.87, -157.37),
    "Samoa": (-13.76, -172.12),
    "Solomon Islands": (-9.65, 160.18),
    "Comoros": (-11.70, 43.25),
    "Sao Tome & Principe": (0.23, 6.61),
    # Commun
    "France": (46.7, 2.3), "Germany": (51.1, 10.3), "England": (52.35, -1.17),
    "Scotland": (56.49, -4.2), "Italy": (42.8, 12.5), "Spain": (40.3, -3.7),
    "Portugal": (39.5, -8.0), "Belgium": (50.8, 4.4), "Netherlands": (52.2, 5.3),
    "United States": (39.8, -98.6), "Canada": (56.1, -106.34), "Japan": (36.2, 138.25),
    "Australia": (-25.0, 133.0), "South Africa": (-30.6, 22.9), "Brazil": (-10.3, -53.1),
    "Argentina": (-38.4, -63.6)
}

def centroid_for(country: str):
    """Retourne (lat, lon) approx pour un pays/entité DXCC, sinon (None, None)."""
    if not country:
        return (None, None)
    return COUNTRY_CENTROIDS.get(country, (None, None))

# ---------------------- REGEX CLUSTER ----------------------
DX_PATTERN = re.compile(
    r"^DX de\s+([A-Z0-9/-]+)[>:]?\s+(\d+(?:\.\d+)?)\s+([A-Z0-9/]+)\s*(.*)$",
    re.IGNORECASE
)

# ---------------------- DXCC ----------------------
MIN_CTYSIZE_BYTES = 50_000  # sécurité anti-fichier vide

def load_cty():
    """Charge cty.csv -> map préfixe -> pays. Télécharge si manquant."""
    global PREFIX_TO_COUNTRY, SORTED_PREFIXES
    PREFIX_TO_COUNTRY.clear()
    if not os.path.isfile(CTY_FILE) or os.path.getsize(CTY_FILE) < 200:
        update_cty()

    try:
        with open(CTY_FILE, "r", encoding="utf-8", newline="") as f:
            # Sniffer pour accepter ',' ou ';'
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;")
                delim = dialect.delimiter
            except Exception:
                delim = ","
            reader = csv.reader(f, delimiter=delim)
            for row in reader:
                if len(row) < 2: continue
                p = (row[0] or "").strip().upper()
                c = (row[1] or "").strip()
                if p and c: PREFIX_TO_COUNTRY[p] = c
        # Petit fallback minimal (au cas où)
        PREFIX_TO_COUNTRY.update({
            "F": "France","DL": "Germany","G": "England","M": "England","GM": "Scotland",
            "I": "Italy","EA": "Spain","CT": "Portugal","ON": "Belgium","PA": "Netherlands",
            "K": "United States","W": "United States","N": "United States","VE": "Canada",
            "JA": "Japan","VK": "Australia","ZS": "South Africa","PY": "Brazil","LU": "Argentina",
        })
        SORTED_PREFIXES = sorted(PREFIX_TO_COUNTRY.keys(), key=len, reverse=True)
        print(f"[CTY] {len(PREFIX_TO_COUNTRY)} préfixes chargés (delim='{delim}').")
    except Exception as e:
        print(f"[CTY] Erreur lecture: {e}")
        PREFIX_TO_COUNTRY = {}
        SORTED_PREFIXES   = []

def update_cty():
    """Télécharge la dernière version de cty.csv et recharge la base."""
    try:
        r = requests.get(
            CTY_URL,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"},
            allow_redirects=True,
        )
        r.raise_for_status()
        if len(r.content) < MIN_CTYSIZE_BYTES:
            raise RuntimeError(f"cty.csv trop petit ({len(r.content)} octets)")
        with open(CTY_FILE, "wb") as f:
            f.write(r.content)
        load_cty()
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

# Tables simplifiées pour inférer le mode par fréquence
FT8_WINDOWS = [
    (3.573, 3.575), (7.074, 7.076), (10.136, 10.138),
    (14.074, 14.076), (18.100,18.102), (21.074,21.076),
    (24.915,24.917), (28.074,28.076), (50.313,50.314)
]
CW_HINTS   = [(7.000,7.035), (14.000,14.070), (21.000,21.070)]
SSB_HINTS  = [(7.180,7.300), (14.150,14.350), (21.200,21.450)]

def in_ranges(f, ranges):
    for a,b in ranges:
        if a<=f<=b: return True
    return False

def detect_mode(txt: str, f=None):
    # 1) indices textuels
    if txt:
        t = txt.upper()
        for k in ["FT8","FT4","CW","SSB","FM","DIGI","RTTY","PSK31","JT65","JT9","WSPR","Q65","MSK144","FSK441","USB","LSB"]:
            if k in t: return "SSB" if k in ("USB","LSB") else k
        if "CQ" in t and "FT8" in t: return "FT8"
        if "CQ" in t and "CW" in t: return "CW"
    # 2) par fréquence
    if isinstance(f,(int,float)):
        if in_ranges(f, FT8_WINDOWS): return "FT8"
        if in_ranges(f, CW_HINTS):    return "CW"
        if in_ranges(f, SSB_HINTS):   return "SSB"
        if 14.070 <= f <= 14.073:     return "PSK"
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
    """Purge spots > 15 min (impacte l'affichage carte)."""
    while True:
        cutoff = datetime.utcnow() - timedelta(minutes=15)
        def is_recent(s):
            try:
                ts = datetime.strptime(s.get("timestamp_full",""), "%Y-%m-%d %H:%M:%S")
                return ts >= cutoff
            except Exception:
                return True
        spots[:] = [s for s in spots if is_recent(s)]
        time.sleep(60)

# ---------------------- PROPAGATION & LATENCE ----------------------
HAMQSL_JSON = "https://www.hamqsl.com/solarjson.php"

def refresh_solar():
    while True:
        try:
            r = requests.get(HAMQSL_JSON, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
            if r.ok:
                j = r.json()
                sfi = j.get("solar",{}).get("solarf", None)
                kp  = j.get("geomag",{}).get("kpindex", None)
                ss  = j.get("solar",{}).get("sunspots", None)
                STATUS["solar"] = {
                    "sfi": int(float(sfi)) if sfi not in (None,"") else None,
                    "kp":  int(float(kp))  if kp  not in (None,"") else None,
                    "sunspots": int(float(ss)) if ss not in (None,"") else None,
                    "updated": datetime.utcnow().strftime("%H:%M")
                }
        except Exception as e:
            print("[SOLAR] Erreur:", e)
        time.sleep(3*3600)  # toutes les 3h

def measure_latency(host, port, timeout=2.0):
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return int((time.perf_counter() - t0) * 1000)
    except Exception:
        return None

def latency_loop():
    while True:
        ms = measure_latency(DEFAULT_CLUSTER["host"], DEFAULT_CLUSTER["port"])
        STATUS["latency_ms"] = ms
        time.sleep(300)

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
    """Most Wanted entendus dans les 3 dernières heures."""
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
    return jsonify({
        "connected": STATUS["connected"],
        "last_update": STATUS["last_update"],
        "latency_ms": STATUS["latency_ms"],
        "solar": STATUS["solar"],
    })

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
            raw = tn.read_until(b"\\n", timeout=30).decode(errors="ignore").strip()
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
            lat, lon = centroid_for(country)
            now = datetime.utcnow()
            spots.insert(0, {
                "timestamp": now.strftime("%H:%M:%S"),
                "timestamp_full": now.strftime("%Y-%m-%d %H:%M:%S"),
                "frequency": f"{f:.3f} MHz",
                "callsign": (dx or "").upper(),
                "dxcc": country,
                "band": band,
                "mode": mode or "?",
                "lat": lat, "lon": lon
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
        country = dxcc_from_call(call)
        lat, lon = centroid_for(country)
        now = datetime.utcnow()
        spots.insert(0, {
            "timestamp": now.strftime("%H:%M:%S"),
            "timestamp_full": now.strftime("%Y-%m-%d %H:%M:%S"),
            "frequency": f"{f:.3f} MHz",
            "callsign": call,
            "dxcc": country,
            "band": guess_band(f),
            "mode": random.choice(["FT8","FT4","SSB","CW","RTTY"]),
            "lat": lat, "lon": lon
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
<link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css">
<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
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

/* Carte Leaflet */
#map{width:100%;height:320px;border-radius:12px;border:1px solid #2b3342}
.leaflet-container{background:#0b1220}
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
      <label>Filtrer bande :
        <select id="bandFilter" onchange="applyFilter()">
          <option value="">Toutes</option>
          <option>160m</option><option>80m</option><option>40m</option><option>30m</option>
          <option>20m</option><option>17m</option><option>15m</option><option>12m</option>
          <option>10m</option><option>6m</option><option>4m</option><option>2m</option>
          <option>70cm</option><option>QO-100</option>
        </select>
      </label>
      <label>Filtrer mode :
        <select id="modeFilter" onchange="applyFilter()">
          <option value="">Tous</option>
        </select>
      </label>
    </div>
    <div class="watchlist">
      {% for c in watchlist %}
        <span class="badge">{{ c }} <button type="button" title="Supprimer" onclick='removeCall(event, {{ c|tojson }})'>🗑️</button></span>
      {% endfor %}
    </div>
    <div class="graphs">
      <div class="card graph-card"><canvas id="barChart"></canvas></div>
      <div class="card graph-card"><canvas id="pieChart"></canvas></div>
    </div>
  </div>

  <!-- middle: badges + DXCC update + PROP -->
  <div class="top-mid card">
    <div class="kpis" id="kpiRow">
      <div class="kpill">🌐 DXCC : <strong id="dxccCount">—</strong> <span id="dxccToday" style="margin-left:6px;opacity:.8"></span></div>
      <div class="kpill">🟢 Cluster : <strong id="conn2">Hors ligne</strong> <span id="latency" style="margin-left:6px;opacity:.8"></span></div>
      <div class="kpill">☀️ SFI: <strong id="sfi">—</strong>  |  🌪️ Kp: <strong id="kp">—</strong>  |  🌞 <strong id="sun">—</strong></div>
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
      <div class="section-title">🌎 Carte des spots (15 min)</div>
      <div id="map"></div>
    </div>

    <div class="card" style="margin-top:12px;">
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
let bandFilter="", modeFilter="", bandChart, pieChart;

// ------ Leaflet Map ------
const map = L.map('map', { worldCopyJump: true, preferCanvas: true, zoomControl: true }).setView([20, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 6, minZoom: 2, attribution: '' }).addTo(map);

// Store markers by key
const spotMarkers = new Map(); // key -> {marker, t, mw, baseOpacity}
let blinkPhase = false;

function applyFilter(){
  bandFilter = document.getElementById("bandFilter").value;
  modeFilter = document.getElementById("modeFilter").value;
}

function inWatchlist(c){return {{ watchlist|tojson }}.includes(String(c||"").toUpperCase());}

async function removeCall(ev, call){
  if(ev){ ev.preventDefault(); ev.stopPropagation(); }
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
  for(const s of spots){
    if(s.band && (!bandFilter||s.band==bandFilter) && (!modeFilter||s.mode==modeFilter)) {
      counts[s.band]=(counts[s.band]||0)+1;
    }
  }
  const labels=Object.keys(counts),values=Object.values(counts);
  const colors=labels.map(l=>({"160m":"#78350f","80m":"#7c3aed","40m":"#22c55e","30m":"#06b6d4","20m":"#3b82f6","17m":"#0ea5e9","15m":"#f472b6","12m":"#f59e0b","10m":"#fb923c","6m":"#10b981","4m":"#14b8a6","2m":"#ec4899","70cm":"#bef264","QO-100":"#ef4444"}[l]||"#9ca3af"));
  if(!bandChart){bandChart=new Chart(document.getElementById('barChart'),{type:'bar',data:{labels,datasets:[{data:values,backgroundColor:colors}]},options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});}
  else{bandChart.data.labels=labels;bandChart.data.datasets[0].data=values;bandChart.data.datasets[0].backgroundColor=colors;bandChart.update();}
  if(!pieChart){pieChart=new Chart(document.getElementById('pieChart'),{type:'pie',data:{labels,datasets:[{data:values,backgroundColor:colors}]},options:{plugins:{legend:{position:'bottom'}}}});}
  else{pieChart.data.labels=labels;pieChart.data.datasets[0].data=values;pieChart.data.datasets[0].backgroundColor=colors;pieChart.update();}
}

function updateModeOptions(spots){
  const set = new Set();
  for(const s of spots){
    const m = (s.mode||'').toUpperCase();
    if(m && m !== '?') set.add(m);
  }
  const modes = Array.from(set).sort();
  const sel = document.getElementById('modeFilter');
  const current = sel.value;
  sel.innerHTML = '<option value=\"\">Tous</option>' + modes.map(m=>`<option value=\"${m}\">${m}</option>`).join('');
  if(current && modes.includes(current)) sel.value = current;
  else if(current) sel.value = '';
}

function spotKey(s){ 
  const t = Math.floor(new Date((s.timestamp_full||'').replace(' ', 'T')+'Z').getTime()/300000); // 5 min bucket
  return `${s.callsign}|${s.band}|${s.mode}|${t}`;
}

function isMostWanted(s, mwSet){ 
  return mwSet.has(s.dxcc) || mwSet.has(s.callsign);
}

function updateMap(spots, mostWantedSet){
  const now = Date.now();
  // Add/update markers
  for(const s of spots){
    if(bandFilter && s.band!==bandFilter) continue;
    if(modeFilter && (s.mode||'')!==modeFilter) continue;
    if(typeof s.lat !== 'number' || typeof s.lon !== 'number') continue;
    const key = spotKey(s);
    if(!spotMarkers.has(key)){
      const mw = isMostWanted(s, mostWantedSet);
      const marker = L.circleMarker([s.lat, s.lon], {radius: mw?7:5, weight: mw?2:1, opacity:1, fillOpacity:0.9}).addTo(map);
      marker.bindPopup(`${s.callsign} — ${s.frequency} — ${s.mode||'?'} — ${s.band||''} — ${s.timestamp||''}Z<br>${s.dxcc||''}`);
      spotMarkers.set(key, {marker, t: now, mw, baseOpacity: 1});
    }
  }
  // Fade & purge
  for(const [k, v] of Array.from(spotMarkers.entries())){
    const age = now - v.t;
    if(age > 15*60*1000){ // 15 min
      map.removeLayer(v.marker); spotMarkers.delete(k); continue;
    }
    if(age > 5*60*1000){
      const f = 1 - (age - 5*60*1000)/(10*60*1000); // 1→0 sur 10 min
      const o = Math.max(0.25, f);
      v.baseOpacity = o;
      v.marker.setStyle({opacity:o, fillOpacity:o});
    }
  }
}

// Blink loop for Most Wanted (toggle opacity between base and base*0.25)
setInterval(()=>{
  blinkPhase = !blinkPhase;
  for(const v of spotMarkers.values()){
    if(!v.mw) continue;
    const o = blinkPhase ? Math.max(0.25, v.baseOpacity*0.25) : v.baseOpacity;
    v.marker.setStyle({opacity:o, fillOpacity:o});
  }
}, 800);

async function refresh(){
  const d=await (await fetch('/spots.json')).json();

  updateModeOptions(d);

  let r='';
  const dxccToday = new Set();
  for(const s of d){
    if(bandFilter && s.band!==bandFilter) continue;
    if(modeFilter && (s.mode||'')!==modeFilter) continue;
    const css=inWatchlist(s.callsign)?' style=\"color:#facc15;font-weight:800;\"':'';
    r+=`<tr${css}>
      <td>${s.timestamp||''}</td>
      <td>${s.frequency||''}</td>
      <td><a href=\"https://www.qrz.com/db/${s.callsign}\" target=\"_blank\">${s.callsign||''}</a></td>
      <td>${s.dxcc||''}</td>
      <td>${s.band||''}</td>
      <td>${s.mode||'?'}</td>
    </tr>`;
    if(s.dxcc && s.dxcc!=='?') dxccToday.add(s.dxcc);
  }
  document.getElementById('tb').innerHTML=r||'<tr><td colspan=\"6\">Aucun spot</td></tr>';
  updateCharts(d);

  // Stats
  const st=await (await fetch('/stats.json')).json();
  const conn=document.getElementById('conn'); const conn2=document.getElementById('conn2');
  conn.innerText=st.connected?\"🟢 Connecté\":\"🔴 Hors ligne\";
  conn2.innerText=st.connected?\"Connecté\":\"Hors ligne\";
  document.getElementById('lastUpd').innerText = st.last_update || '—';
  document.getElementById('latency').innerText = st.latency_ms?`(${st.latency_ms} ms)`:'';
  // Solar badges
  if(st.solar){
    document.getElementById('sfi').innerText = st.solar.sfi ?? '—';
    document.getElementById('kp').innerText  = st.solar.kp  ?? '—';
    document.getElementById('sun').innerText = st.solar.sunspots ?? '—';
  }
  // DXCC today (approx) – simple indicateur
  document.getElementById('dxccToday').innerText = dxccToday.size ? `(↑ ${dxccToday.size} aujourd’hui)` : '';

  // Update map with Most Wanted knowledge
  const wanted = await (await fetch('/wanted.json')).json();
  const mwSet = new Set((wanted.list||[]).map(x=>x.country));
  updateMap(d, mwSet);
}

async function loadRSS(){
  const d1=await (await fetch('/rss1.json')).json();
  const d2=await (await fetch('/rss2.json')).json();
  document.getElementById('rsslist1').innerHTML=d1.map(e=>`<li><a href=\"${e.link}\" target=\"_blank\">${e.title}</a></li>`).join('');
  document.getElementById('rsslist2').innerHTML=d2.map(e=>`<li><a href=\"${e.link}\" target=\"_blank\">${e.title}</a></li>`).join('');
}

async function loadWanted(){
  const data = await (await fetch('/wanted.json')).json();
  const list = data.list || [];
  let html='';
  for(const it of list){
    const cls = it.active ? 'wanted-item active' : 'wanted-item';
    const flagImg = it.flag_png ? `<img class=\"flag\" src=\"${it.flag_png}\" onerror=\"this.style.display='none'\">` : '';
    const flagEmoji = `<span style=\"margin-left:6px\">${it.flag_emoji||'🌐'}</span>`;
    const left = `<div class=\"wanted-name\">${flagImg}${flagEmoji}<span>${it.country}</span></div>`;
    const right = it.active ? `<span class=\"wanted-spot\">🟢 ${it.callsign} @ ${it.freq}</span>` : `<span class=\"wanted-spot\" style=\"opacity:.6\">(no spot)</span>`;
    html += `<div class=\"${cls}\">${left}${right}</div>`;
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
    const flagImg = it.flag_png ? `<img class=\"flag\" src=\"${it.flag_png}\" onerror=\"this.style.display='none'\">` : '';
    const flagEmoji = `<span style=\"margin-left:6px\">${it.flag_emoji||'🌐'}</span>`;
    html += `<div class=\"${neonClass}\" style=\"padding:4px 0;\">
      ${flagImg}${flagEmoji} ${it.dxcc} — <b>${it.callsign}</b> — ${it.freq} — ${it.mode} — ${it.time}Z
    </div>`;
  }
  document.getElementById('recentList').innerHTML = html || '<div class=\"neon gray\">Aucun DX rare signalé</div>';
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
    threading.Thread(target=latency_loop, daemon=True).start()
    threading.Thread(target=refresh_solar, daemon=True).start()

    # Fallback simulation si pas de connexion après 10s
    def delayed_sim():
        time.sleep(10)
        if not STATUS["connected"]:
            print("[INFO] Cluster injoignable, simulation activée.")
            threading.Thread(target=simulate_spots, daemon=True).start()
    threading.Thread(target=delayed_sim, daemon=True).start()

    app.run(host="0.0.0.0", port=8000, debug=False)
