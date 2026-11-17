# esp-drone 9d5a4f8 + locSrv (external position) - known good

Built 2026-11-16 with ESP-IDF v5.5.6 for ESP32-S2-Drone V2.0 (B-Cube). Verified on drone 90e5b199a332:
extpos test PASS, link test PASS, flash contents match these files (`verify_flash`, digest matched).

- `bootloader.bin` @0x1000, `partition-table.bin` @0x8000, `ESPDrone.bin` @0x10000 (see `flash_args`)
- `merged-0x0.bin`: the same three parts in one file, flash at 0x0
- `ESPDrone.elf`: symbols for decoding crash backtraces
- `sdkconfig`, `sdkconfig.slunecnice`, `esp-drone-locsrv.patch`: everything needed to rebuild from upstream 9d5a4f8

Flash another drone (backs up its factory image first): `tools/flash_drone.sh`
Manual: `cd` here, then `esptool.py --chip esp32s2 -p /dev/cu.usbserial-0001 -b 115200 write_flash @flash_args`

Firmware boots disarmed: set param `system.forceArm=1` from the host before thrust.
