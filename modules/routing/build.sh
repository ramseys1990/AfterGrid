#!/bin/sh
set -eu
. /aftergrid/slot.sh
case "${1:-initial}" in
  initial)
    active=$(selected_slot)
    if ready_slot "$active"; then echo "Existing selected graph retained"; exit 0; fi
    test "$active" = tiles || { echo "Selected alternate graph missing; inspect retained data"; exit 1; }
    source=/routing/region.osm.pbf
    target=tiles ;;
  candidate)
    test "$(selected_slot)" = tiles && ready_slot tiles || { echo "Select and retain original graph before preparing candidate"; exit 1; }
    source=/routing/incoming.osm.pbf
    target=tiles-next ;;
  *) exit 1 ;;
esac
test ! -e "/routing/$target" && test ! -L "/routing/$target" || { echo "Graph slot occupied; never overwrite a retained graph"; exit 1; }
test -f "$source" && test ! -L "$source" || { echo "Required local PBF missing"; exit 1; }
# Conservative minimum only; native build size depends on the road network.
bytes=$(stat -c %s "$source")
free_kb=$(df -Pk /routing | awk 'END {print $4}')
test "$bytes" -gt 0 && test "$free_kb" -gt "$((3 * bytes / 1024 + 524288))" || { echo "Insufficient graph build headroom (3x PBF plus 512 MiB minimum)"; exit 1; }
tmp=$(mktemp -d /routing/.build-XXXXXX)
trap 'rm -rf "$tmp"' EXIT
/bin/sh /aftergrid/config.sh "$tmp"
# Bound native build duration below the Compose worker timeout.
timeout --kill-after=10s 1500s valhalla_build_tiles -c /tmp/valhalla.json "$source"
find "$tmp" -name '*.gph' -print -quit | grep -q . || { echo "No graph tiles created"; exit 1; }
touch "$tmp/.aftergrid-ready"
# Never replace a nonempty graph directory; only the worker builds graphs.
mv -T "$tmp" "/routing/$target"
trap - EXIT
echo "Local routing graph prepared in $target"
