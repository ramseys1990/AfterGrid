#!/bin/sh
set -eu
. /aftergrid/slot.sh
target=$1
case "$target" in tiles) source=region.osm.pbf;; tiles-next) source=incoming.osm.pbf;; *) exit 1;; esac
active=$(selected_slot)
ready_slot "$active" && test "$active" != "$target" || { echo "Cannot archive the selected graph"; exit 1; }
ready_slot "$target" || { echo "Inactive graph is not prepared"; exit 1; }
test -f "/routing/$source" && test ! -L "/routing/$source" || { echo "Inactive source missing; inspect archives manually"; exit 1; }
# Move rather than copy or delete. Source goes first, so an interrupted
# archive cannot make the slot eligible for a new download until graph moves.
python3 - "$target" "$source" <<'PY'
import os, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone
root=Path("/routing")
target,source=sys.argv[1:]
archive=root/"archives"
if archive.is_symlink(): raise SystemExit("Invalid archive directory")
archive.mkdir(mode=0o700,exist_ok=True)
folder=Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")+target+"-",dir=archive))
os.rename(root/source,folder/source)
try:
    os.rename(root/target,folder/target)
except Exception:
    if not (root/source).exists():
        os.rename(folder/source,root/source)
    raise
print("Retained inactive dataset and graph in "+str(folder))
PY
