#!/bin/sh
set -eu
test -f /routing/tiles/.aftergrid-ready || { echo "Routing graph not prepared; run Install from AfterGrid"; exit 1; }
/bin/sh /aftergrid/config.sh /routing/tiles
exec valhalla_service /tmp/valhalla.json 2
