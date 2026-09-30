#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  install) python3 -m pip install --user -e . ;;
  clean) rm -rf build dist ./*.egg-info __pycache__ ;;
  *) printf 'Usage: %s {install|clean}\n' "$0" >&2; exit 2 ;;
esac
