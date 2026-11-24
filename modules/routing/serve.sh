#!/bin/sh
set -eu
. /aftergrid/slot.sh
active=$(selected_slot)
ready_slot "$active" || { echo "Selected routing graph not prepared"; exit 1; }
/bin/sh /aftergrid/config.sh "/routing/$active"
echo "Serving graph slot $active"
exec valhalla_service /tmp/valhalla.json 2
