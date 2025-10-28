Radio Spot Watcher — v2.84 stable

Radio Spot Watcher is a real-time dashboard for amateur radio operators.

It connects to a DX cluster (telnet), parses live spots, displays active calls with band / mode / DXCC info, shows rare DX targets, and builds quick stats.

The goal:

- See who’s on the air right now.
- Spot rare DXCC entities in seconds.
- Highlight stations you personally care about.
- Watch band activity trends at a glance.

This README documents version v2.84 "stable".

✨ Key Features

1. DX Cluster Connection

- Automatic telnet connection to a DX cluster (default: dxfun.com:8000).
- Auto-reconnect if the session drops.
- Connection status indicator:
   - Green = connected
   - Red = offline
- Active cluster host/port is shown in the header.

2. Live Spots Table

- Incoming spots are shown immediately.
- Typical columns:
   - UTC time
   - Frequency
   - Call (spotted callsign)
   - Mode (SSB / CW / FT8 / etc.)
   - Band (20m / 6m / 2m / QO-100 / etc.)
   - DXCC (country / entity)
   - Grid (locator if provided)
   - Spotter (who reported the spot)
- Newest spots appear at the top.
- Callsigns are clickable (QRZ lookups).
- If a call is in your watchlist, that row is visually highlighted.

3. Band / Mode Filters

- Dropdown "Band": All / 160m / 80m / ... / 6m / 2m / 70cm / QO-100.
- Dropdown "Mode": All / SSB / CW / FT8 / etc.
- Filters apply instantly to the spot table without a full reload.

4. Watchlist (calls under surveillance)

- You can add callsigns you want to watch.
- The watchlist is rendered in the header UI as badges.
- Each badge shows a trash icon to remove that callsign.
- When a watched callsign appears in the live spot stream:
   - Its row gets a strong visual highlight.
   - You can’t miss it.

(Older popup-style input is being phased out in favor of inline entry.)

5. Most Wanted DXCC

- Displays a curated list of the most wanted DXCC entities / rare islands.
- Two-column layout of "cards".
- The plan is to display:
   - Entity name,
   - DXCC / reference,
   - A small flag or island identifier icon.
- Purpose: instantly know if something from the "top wanted" list just showed up.

6. Map View

- Leaflet map shows recent spots.
- Each spot is plotted using approximate coordinates (DXCC country position, grid locator, etc.).
- Marker color depends on band (e.g. 20m / 40m / 6m get different colors).
- The map panel can be vertically resized / arranged with the stats panel.

7. Live Stats

- Quick bar charts / histograms for "spots per band" over the recent window.
- Simple analytics panel ("which band is hottest right now").
- Updates continuously as new spots come in.

8. DX News (RSS Feed)

- Recent DX-related headlines / expedition alerts are fetched from an RSS feed.
- Displayed in a small panel.
- The RSS text color is adapted for dark or light themes to remain legible.

9. Theming and UI

- Two visual directions are supported:
   - Dark ops-style theme (black / dark gray background, green/yellow accents).
   - Light modern theme (pale gray + bluish accents).
- Colors for "watched calls" rows, RSS headlines, etc. are centralized in CSS.
- The idea is: you can restyle the app (dark vs light) without touching the Python logic.

10. Header Status Bar

At the top of the UI:

- Software version (example: "Radio Spot Watcher v2.84 stable").
- Cluster status and hostname:port.
- Total number of spots received.
- Spots received in the last 5 minutes.
- Last update timestamp.
- Band / Mode selectors.
- Watchlist zone.

This acts like a radio operator’s console dashboard.

🧠 Architecture Overview

Backend

- Language: Python 3.11+.
- Framework: Flask.
- The app opens a telnet socket to the DX cluster.
- Each incoming line is parsed using regular expressions.
- Spots are stored in memory using a bounded deque (FIFO with max len).
- Stats (e.g. per band) are computed live.
- The “Most Wanted DXCC” list is loaded from a small JSON structure; it can be refreshed or modified.
- The backend exposes several JSON endpoints ("/spots.json", "/status.json", "/wanted.json", "/rss.json", etc.) for the front-end to poll.

Frontend

- HTML is assembled in Python and served as one page.
- CSS is embedded (dark or light theme depending on build).
- JavaScript runs in the browser to:
   - poll JSON endpoints,
   - repaint the spots table,
   - refresh the map markers,
   - update charts,
   - manage the watchlist,
   - apply band/mode filters instantly.

Process management

- A helper script "start.sh":
   - Activates the Python venv,
   - Kills any process already using port 8000,
   - Starts the Flask server on "0.0.0.0:8000".
- Reconnect logic is included: if the DX cluster drops, the app tries again automatically.

Storage

- No external database.
- State is primarily in memory.
- A future enhancement is to persist "watchlist", color themes, and cluster preferences to a local JSON file (e.g. "config.json") so they survive restarts.

🛠 Install (Raspberry Pi / Debian)

1. System packages:

sudo apt update
sudo apt install -y python3 python3-venv python3-pip telnet

2. Clone repo:

git clone https://github.com/<your-account>/radio-spot-watcher.git
cd radio-spot-watcher

3. Create & activate venv:

python3 -m venv venv
source venv/bin/activate
pip install flask requests

4. Run:

./start.sh

5. Open in a browser:

   - http://127.0.0.1:8000
   - or http://<your-pi-ip>:8000 on your LAN

🔄 Cluster fallback
If "dxfun.com:8000" becomes unreachable, the app will attempt to connect to an alternate cluster automatically and reflect that in the header status (still "Connected" if success, otherwise "Offline").

🔧 Customization

Callsign for cluster login

Inside the Python code there’s a "CALLSIGN" (or similar) variable that’s used when logging into the DX cluster.
Replace it with your personal callsign.

Color accents

Look for the CSS section in the generated HTML:

- ".row-watch" or similar → highlight color for watched calls.
- ".rss-item" → feed text color.
- Theme vars like "--bg", "--text", etc. control global palette in the light theme build.

Most Wanted DXCC list / flags

The “Most Wanted DXCC” section is populated from a data structure containing:

- entity label,
- optional DXCC ref,
- target flag / icon,
- display order.
Editing that structure customizes which rare entities are shown first.

📌 Roadmap

Short term:

1. Inline watchlist editor in the header
(text field + [+] button + trash icons per callsign).
2. Restore per-entity flags in the “Most Wanted DXCC” grid.
3. Improve RSS readability (bright color on dark backgrounds).
4. Allow saving user preferences (theme, watchlist) in a local JSON file.
5. Let the user pick a color palette (dark / light / accent color).

Mid-term:

- Manual cluster selector from UI.
- Band-color legend & toggle on the map.
- Compact layout mode for small screens.

Long-term:

- CSV export of recent spots.
- Distance/range filtering using locators.
- Optional audio/visual alert on watched calls.

📜 License

This is hobbyist ham radio software.Designed by **F1SMV (Eric) and developed by ChatGPT5**
Interface and improvements inspired by modern DX dashboards (ClubLog, DXHeat).
Responsive and clear design for use on PC, tablet, or mobile.
Personal use is fine.
If you redistribute or fork publicly, please credit the original author and keep the version notice.

📣 Reporting issues

When you open an issue, please include:

- Screenshot of the top status bar (to capture version + cluster state),
- Explanation (“RSS feed unreadable”, “No map markers on 2m”, etc.),
- Steps to reproduce if possible.

73! 