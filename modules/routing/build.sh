#!/bin/sh
set -eu
if [ -f /routing/tiles/.aftergrid-ready ]; then
  echo "Existing graph retained"
  exit 0
fi
test ! -e /routing/tiles || { echo "Existing unrecognized tiles directory; inspect manually"; exit 1; }
test -f /routing/region.osm.pbf && test ! -L /routing/region.osm.pbf || { echo "Copy a regional PBF to content/routing/region.osm.pbf before installing"; exit 1; }
tmp=$(mktemp -d /routing/.build-XXXXXX)
trap 'rm -rf "$tmp"' EXIT
/bin/sh /aftergrid/config.sh "$tmp"
valhalla_build_tiles -c /tmp/valhalla.json /routing/region.osm.pbf
find "$tmp" -name '*.gph' -print -quit | grep -q . || { echo "No graph tiles created"; exit 1; }
touch "$tmp/.aftergrid-ready"
mv -T "$tmp" /routing/tiles
trap - EXIT
echo "Local routing graph built"
