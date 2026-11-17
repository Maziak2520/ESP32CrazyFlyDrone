#!/usr/bin/env bash
# Flash a saved firmware release onto an ESP32-S2-Drone, backing up its factory flash first.
# Usage: tools/flash_drone.sh [release_dir] [port]
# 115200 baud only: this board's CP2102 fails at 460800/921600 ("Invalid head of packet").
set -euo pipefail
cd "$(dirname "$0")/.."
REL=${1:-firmware/release/esp-drone-9d5a4f8-locsrv}
PORT=${2:-/dev/cu.usbserial-0001}
ESPTOOL=("$PWD/.venv/bin/esptool.py" --chip esp32s2 -p "$PORT" -b 115200)

(cd "$REL" && shasum -a 256 -c SHA256SUMS)

MAC=$("${ESPTOOL[@]}" read_mac | awk '/^MAC:/{print $2; exit}' | tr -d ':')
[ -n "$MAC" ] || { echo "could not read MAC" >&2; exit 1; }
BK="firmware-backup/esp32s2-drone-$MAC-factory.bin"
if [ -s "$BK" ]; then
  echo "factory backup exists: $BK (not overwriting)"
else
  echo "backing up 4 MB factory flash to $BK (~6 min)"
  "${ESPTOOL[@]}" read_flash 0 0x400000 "$BK"
  shasum -a 256 "$BK" | tee "$BK.sha256"
fi

(cd "$REL" && "${ESPTOOL[@]}" write_flash @flash_args && "${ESPTOOL[@]}" verify_flash @flash_args)
echo "DONE $MAC. Power-cycle the drone (USB + battery out) before use."
