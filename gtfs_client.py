"""
Copenhagen transit vehicle positions client.

# ============================================================
# TODO — COMPLETE THIS FILE ON MONDAY WHEN API KEY ARRIVES
# ============================================================
#
# Provider: Rejseplanen Labs (labs.rejseplanen.dk)
#
# STEP 1: Confirm the feed format.
#   Rejseplanen may offer one of:
#     A) GTFS-RT VehiclePositions protobuf  ← this file assumes A
#     B) SIRI-VM (XML) VehicleMonitoring    ← requires a different client
#
#   Test with:
#     curl -H "Authorization: Bearer YOUR_KEY" \
#          "https://ENDPOINT_URL" | file -
#   If it prints "data" or "gzip" it's likely protobuf/binary → GTFS-RT (A).
#   If it prints "XML" → SIRI (B), replace this file with a SIRI client.
#
# STEP 2: Fill in the real endpoint URL and auth header below.
#
# STEP 3: Determine vehicle type classification.
#   Inspect a sample of route_id values from the feed:
#     - If NeTEx format (e.g. "MOVIA:Line:123") → classify by operator prefix
#     - If short integer (e.g. "123") → look up route_type field or line table
#   Known Copenhagen operators (NeTEx):
#     MOVIA / MVT  → bus
#     METRO        → metro (M1, M2, M3 Cityringen, M4 Orientkaj)
#     DSB          → S-tog (suburban rail)
#     NT / NT:*    → local rail
#     HUR / HTX    → harbour bus / water bus
#
# STEP 4: Update bounding box if needed.
#   Current box: lat 55.50–55.85, lon 12.10–12.80
#   This covers Greater Copenhagen incl. Malmö bridge end.
#   Tighten if feed returns vehicles from all of Denmark.
#
# ============================================================

import gzip
import threading
import time
import urllib.request
import urllib.error

from google.transit import gtfs_realtime_pb2
import state

INTERVAL = 30

# Greater Copenhagen bounding box (adjust after feed inspection)
LAT_MIN, LAT_MAX = 55.50, 55.85
LON_MIN, LON_MAX = 12.10, 12.80

# TODO: replace with real endpoint from Rejseplanen Labs dashboard
FEED_URL = "https://PLACEHOLDER.rejseplanen.dk/gtfs-rt/vehicle-positions"

# TODO: replace with your actual API key (set as Fly secret: fly secrets set REJSEPLANEN_KEY=...)
import os
API_KEY = os.environ.get("REJSEPLANEN_KEY", "")


def _classify(route_id: str) -> str:
    """
    TODO: implement once feed format is confirmed.
    Placeholder: classify by NeTEx operator prefix (guessed — verify against real data).
    """
    if not route_id or ":" not in route_id:
        return "bus"

    operator = route_id.split(":")[0].upper()

    if operator in ("METRO", "CPH_METRO"):
        return "metro"
    if operator in ("DSB", "SBAN", "SNTOG"):
        return "train"
    if operator in ("HUR", "HTX", "HAVNEBUSS"):
        return "ferry"
    # MOVIA and unknown → bus
    return "bus"


def _fetch_and_update() -> int:
    if not API_KEY:
        print("[GTFS] WARNING: REJSEPLANEN_KEY not set — skipping fetch")
        return 0

    try:
        req = urllib.request.Request(
            FEED_URL,
            headers={
                # TODO: confirm correct auth header format with Rejseplanen Labs docs
                "Authorization": f"Bearer {API_KEY}",
                "Accept-Encoding": "gzip",
                "User-Agent": "nta-cph-recorder/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        print(f"[GTFS] HTTP {e.code}: {e.reason}")
        return 0
    except Exception as e:
        print(f"[GTFS] Fetch error: {e}")
        return 0

    # Decompress if gzip
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)

    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(raw)
    except Exception as e:
        print(f"[GTFS] Parse error: {e}")
        return 0

    seen: set = set()

    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        veh = entity.vehicle
        if not veh.HasField("position"):
            continue

        lat = veh.position.latitude
        lon = veh.position.longitude

        if lat == 0.0 and lon == 0.0:
            continue
        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            continue

        vid = veh.vehicle.id or entity.id
        if not vid:
            continue

        route_id = veh.trip.route_id or ""
        vtype = _classify(route_id)
        route = route_id.split(":")[-1].split("_")[0] if route_id else ""

        seen.add(vid)
        state.update_vehicle(vid, {
            "lat":   round(lat, 6),
            "lon":   round(lon, 6),
            "type":  vtype,
            "route": route,
        })

    # Remove vehicles gone from feed
    for gone in set(state.get_all_vehicles().keys()) - seen:
        state.remove_vehicle(gone)

    return len(seen)


def _poll_loop() -> None:
    print(f"[GTFS] Starting poll loop (every {INTERVAL}s)")
    backoff = 5
    while True:
        try:
            n = _fetch_and_update()
            print(f"[GTFS] {n} vehicles in state")
            backoff = 5
        except Exception as e:
            print(f"[GTFS] Unexpected error: {e} — retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        time.sleep(INTERVAL)


def start_gtfs_thread() -> None:
    threading.Thread(target=_poll_loop, daemon=True).start()
