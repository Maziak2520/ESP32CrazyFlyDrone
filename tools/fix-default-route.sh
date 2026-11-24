#!/bin/bash
# Keep internet via phone USB tethering while Wi-Fi (en0) is joined to the drone AP.
# Drone AP = 192.168.43.0/24, gw 192.168.43.1. macOS installs drone default route on join.
# Fix: split-default 0.0.0.0/1 + 128.0.0.0/1 via phone gateway (longer prefix than /0,
# always wins), drone subnet pinned to en0.
#
# Usage: sudo ./tools/fix-default-route.sh [phone_iface]
# Run AFTER joining the drone Wi-Fi.
set -e
PHONE_IF="${1:-en17}"
DRONE_IF="en0"

PHONE_IP=$(ipconfig getifaddr "$PHONE_IF") || { echo "no IP on $PHONE_IF - tethering off?"; exit 1; }
PHONE_GW=$(ipconfig getpacket "$PHONE_IF" | awk -F': ' '/^router/{print $2}' | tr -d '(),' | head -1)
[ -n "$PHONE_GW" ] || { echo "no gateway in DHCP on $PHONE_IF"; exit 1; }
echo "Phone: $PHONE_IF ip=$PHONE_IP gw=$PHONE_GW"

networksetup -ordernetworkservices "Pixel 9 Pro" Wi-Fi >/dev/null 2>&1 || true

sudo route -qn delete -net 0.0.0.0/1 2>/dev/null || true
sudo route -qn delete -net 128.0.0.0/1 2>/dev/null || true
# Clear any drone default route that steals 8.8.8.8 etc. (only while we re-add ours)
sudo route -qn delete default 2>/dev/null || true
sudo route -qn add -net 0.0.0.0/1 "$PHONE_GW"
sudo route -qn add -net 128.0.0.0/1 "$PHONE_GW"

sudo route -qn delete -net 192.168.43.0/24 2>/dev/null || true
sudo route -qn add -net 192.168.43.0/24 -interface "$DRONE_IF"

echo "--- 8.8.8.8 via:"; route -n get 8.8.8.8 | grep -E 'gateway|interface'
echo "--- drone via:";   route -n get 192.168.43.42 | grep -E 'gateway|interface'
echo "--- internet:";    ping -c1 -W2 8.8.8.8 | tail -1
echo "--- drone:";       ping -c1 -W2 192.168.43.42 | tail -1
