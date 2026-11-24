#!/bin/sh
# Sourced only from reviewed routing scripts. Slots are fixed, not user paths.
selected_slot() {
  if [ -L /routing/active-slot ]; then
    echo "Refusing symlink selector" >&2; return 1
  fi
  if [ -e /routing/active-slot ]; then
    test -f /routing/active-slot || return 1
    slot=$(cat /routing/active-slot)
  else
    slot=tiles
  fi
  case "$slot" in tiles|tiles-next) printf '%s\n' "$slot";; *) echo "Invalid graph selector" >&2; return 1;; esac
}
ready_slot() {
  case "$1" in tiles|tiles-next) ;; *) return 1;; esac
  test ! -L "/routing/$1" && test -d "/routing/$1" &&
    test ! -L "/routing/$1/.aftergrid-ready" && test -f "/routing/$1/.aftergrid-ready"
}
