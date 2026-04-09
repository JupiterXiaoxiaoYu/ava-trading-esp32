#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cmake -S "$ROOT_DIR" -B "$ROOT_DIR/build" >/dev/null
cmake --build "$ROOT_DIR/build" --target verify_screenshot_feed -j4 >/dev/null

cd "$ROOT_DIR"

has_single_screen=0
for arg in "$@"; do
  if [[ "$arg" == "--screen" ]]; then
    has_single_screen=1
    break
  fi
done

if [[ "$has_single_screen" -eq 1 ]]; then
  ./bin/verify_screenshot_feed "$@"
  exit 0
fi

extra_args=("$@")
mapfile -t SCREENS < <(./bin/verify_screenshot_feed --list-screens)
for screen in "${SCREENS[@]}"; do
  echo "[gate] verifying screen: $screen"
  ./bin/verify_screenshot_feed --screen "$screen" "${extra_args[@]}"
done
