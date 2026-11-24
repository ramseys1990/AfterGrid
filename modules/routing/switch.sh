#!/bin/sh
set -eu
. /aftergrid/slot.sh
action=$1
target=$2
case "$target" in tiles|tiles-next) ;; *) exit 1;; esac
active=$(selected_slot)
ready_slot "$target" || { echo "Requested graph is not prepared"; exit 1; }
case "$action" in
  check)
    ready_slot "$active" && test "$active" != "$target" || { echo "Both distinct graph slots must be ready"; exit 1; }
    ;;
  select)
    tmp=$(mktemp /routing/.selector-XXXXXX)
    trap 'rm -f "$tmp"' EXIT
    printf '%s\n' "$target" > "$tmp"
    mv -T "$tmp" /routing/active-slot
    trap - EXIT
    echo "Selected $target"
    ;;
  *) exit 1;;
esac
