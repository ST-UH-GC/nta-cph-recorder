# nta-cph-recorder — Claude Code Handover

Nordic Transit Art — Copenhagen recorder.
Records Tuesday vehicle positions to `/data/tuesday.jsonl` (JSONL, 30 s snapshots).

---

## Status: INCOMPLETE — waiting for API key

The project structure is fully scaffolded but `gtfs_client.py` has placeholder values.
Do NOT deploy until the API key is confirmed and the feed format is verified.

---

## Monday checklist

### 1. Get API key
- Source: **Rejseplanen Labs** — labs.rejseplanen.dk
- The key was requested ~20 March 2026. Check email / Rejseplanen Labs dashboard.

### 2. Confirm feed format
```bash
# Test with key — check if response is binary (GTFS-RT) or XML (SIRI)
curl -s -H "Authorization: Bearer YOUR_KEY" \
     "https://ENDPOINT_URL" | file -
```
- Binary / "data" / "gzip compressed" → **GTFS-RT** → fill in gtfs_client.py TODOs
- XML → **SIRI-VM** → replace gtfs_client.py with a SIRI client (see note below)

### 3. Fill in gtfs_client.py
Update these lines:
```python
FEED_URL = "https://REAL_ENDPOINT_FROM_REJSEPLANEN_DOCS"
# Auth header — confirm format: Bearer token? API key query param? X-API-Key header?
```

### 4. Inspect vehicle type classification
```bash
# After confirming key + endpoint, run a quick test:
python3 - <<'EOF'
import urllib.request, gzip
from google.transit import gtfs_realtime_pb2
req = urllib.request.Request("FEED_URL", headers={"Authorization": "Bearer KEY", "Accept-Encoding": "gzip"})
raw = urllib.request.urlopen(req).read()
if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(raw)
route_ids = {e.vehicle.trip.route_id for e in feed.entity if e.HasField("vehicle")}
print(sorted(route_ids)[:40])
EOF
```
Update `_classify()` in `gtfs_client.py` based on what you see.

### 5. Set Fly.io secret
```bash
fly secrets set REJSEPLANEN_KEY=your_actual_key --app nta-cph-recorder
```

### 6. Create volume + deploy
```bash
fly volumes create cph_data --app nta-cph-recorder --region arn --size-gb 1
fly deploy --config fly.toml
fly logs --app nta-cph-recorder   # watch for [GTFS] lines
```

---

## If feed is SIRI-VM (not GTFS-RT)

Replace gtfs_client.py entirely with a SIRI client. Basic structure:
```python
import urllib.request, threading, time, xml.etree.ElementTree as ET
import state

SIRI_URL = "https://SIRI_ENDPOINT/VehicleMonitoring"
# SIRI uses SOAP/XML — parse VehicleActivity elements
# Each VehicleActivity has VehicleLocation (Latitude, Longitude), LineRef, VehicleRef
```

---

## Project context

This is part of the **Nordic Transit Art** project — animated dark-map replays of 24h city transit.
- Helsinki: `https://st-uh-gc.github.io/hsl-artsy-replay/replay.html` ✅
- Stockholm: `nta-sto-recorder` on Fly.io, recording Tuesdays → deploy replay after 25 Mar 2026
- Oslo: `nta-osl-recorder` on Fly.io, recording Tuesdays → same
- Copenhagen: this repo — pending API key

JSONL schema (Helsinki-compatible):
```json
{"t": 1773525606, "v": {"vid": [lat, lon, "type", "route_short_name"]}}
```

Recording day: **Tuesday** (Europe/Copenhagen timezone, all day, `wd == 1`).
Output file: `/data/tuesday.jsonl`

---

## File structure

```
state.py         Thread-safe vehicle dict (identical to oslo/stockholm)
recorder.py      30 s JSONL snapshot daemon — Tuesday, Europe/Copenhagen
gtfs_client.py   ⚠️ PLACEHOLDER — complete Monday with real key + endpoint
main.py          FastAPI: /health (vehicle count), /tuesday.jsonl
requirements.txt fastapi, uvicorn, protobuf, gtfs-realtime-bindings, tzdata
Dockerfile       python:3.12-slim, port 8080
fly.toml         app=nta-cph-recorder, region=arn, volume=cph_data→/data
```
