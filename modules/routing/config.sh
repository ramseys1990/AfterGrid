#!/bin/sh
set -eu
# Use native config generator; no remote tile/elevation service.
valhalla_build_config --mjolnir-tile-dir "$1" --mjolnir-concurrency 2 --mjolnir-max-cache-size 134217728 --mjolnir-data-processing-use-admin-db false > /tmp/valhalla-base.json
python3 -c 'import json; p=json.load(open("/tmp/valhalla-base.json")); m=p["mjolnir"]; [m.pop(k,None) for k in ("tile_extract","traffic_extract","admin","timezone","landmarks")]; p["loki"]["actions"]=["route","status"]; p["httpd"]["service"]["timeout_seconds"]=30; print(json.dumps(p))' > /tmp/valhalla.json
