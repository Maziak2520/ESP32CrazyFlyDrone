#!/bin/bash
# Keep internet via phone (Pixel 9 Pro, en17) while Wi-Fi (en0) is joined to the drone AP.
# Drone AP 192.168.43.42/24 must stay reachable; everything else must go via phone.
# Usage: sudo ./tools/fix-default-route.sh [phone_iface] [phone_gw]
set -e
PHONE_IF="${1:-en17}"
PHONE_GW="${2:-$(route -n get default | awk '/gateway/{print $2}')}"
DRONE_IF="en0"

echo "Phone iface: $PHONE_IF gw: $PHONE_GW"

# 1) Make phone first in service order so its default route wins ties
networksetup -ordernetworkservices "Pixel 9 Pro" Wi-Fi >/dev/null

# 2) Split-default routes: 0.0.0.0/1 + 128.0.0.0/1 via phone gateway.
#    Longer prefix than 0.0.0.0/0 -> always beat the drone's default route.
sudo route -qn delete -net 0.0.0.0/1 "$PHONE_GW" 2>/dev/null || true
sudo route -qn delete -net 128.0.0.0/1 "$PHONE_GW" 2>/dev/null || true
sudo route -qn add -net 0.0.0.0/1 "$PHONE_GW"
sudo route -qn add -net 128.0.0.0/1 "$PHONE_GW"

# 3) Pin drone subnet explicitly (in case default route moved to en0)
sudo route -qn delete -net 192.168.43.0/24 2>/dev/null || true
sudo route -qn add -net 192.168.43.0/24 -interface "$DRONE_IF"

echo "--- default:"; route -n get default | grep -E 'gateway|interface'
echo "--- 192.168.43.42:"; route -n get 192.168.43.42 | grep -E 'gateway|interface'
echo "--- internet test:"; ping -c1 -W2 8.8.8.8 | tail -1
