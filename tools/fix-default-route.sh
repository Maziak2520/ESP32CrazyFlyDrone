#!/bin/bash
# Join drone Wi-Fi AND keep internet via phone USB tethering.
# No sudo needed.
#
# Why: drone AP DHCP hands out router=192.168.43.42, which installs a default
# route via the drone and kills internet. Fix = manual IP on Wi-Fi with EMPTY
# router field. Phone (Pixel 9 Pro / en17) stays default route.
#
# Usage:
#   ./tools/fix-default-route.sh join ESP-DRONE_90E5B199A333 12345678
#   ./tools/fix-default-route.sh status
set -e
DRONE_IP=192.168.43.43

join() {
  local SSID="$1" PASS="$2"
  networksetup -setairportpower en0 on
  networksetup -setairportnetwork en0 "$SSID" "$PASS"
  # override DHCP with manual, router empty -> no default route via drone
  networksetup -setmanual Wi-Fi "$DRONE_IP" 255.255.255.0 ""
  echo "joined $SSID"
  status
}

status() {
  echo "--- Wi-Fi: $(networksetup -getairportnetwork en0)"
  networksetup -getinfo Wi-Fi | grep -E 'IP address|Subnet|Router'
  echo "--- 8.8.8.8 via:"; route -n get 8.8.8.8 | grep -E 'gateway|interface'
  echo "--- drone 192.168.43.42 via:"; route -n get 192.168.43.42 | grep -E 'gateway|interface'
  echo "--- internet:"; ping -c1 -W2 8.8.8.8 | tail -1
  echo "--- drone:";    ping -c1 -W2 192.168.43.42 | tail -1
}

case "${1:-status}" in
  join)   join "$2" "$3" ;;
  status) status ;;
  *) echo "usage: $0 join <ssid> <pass> | status"; exit 1 ;;
esac
