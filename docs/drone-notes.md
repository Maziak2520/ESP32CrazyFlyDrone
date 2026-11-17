# ESP32-S2-Drone V2.0 (B-Cube) - working notes

Source: bcuberc.com product page + Espressif ESP-Drone docs
(https://docs.espressif.com/projects/espressif-esp-drone/en/latest/). Checked 2026-11-16.

## Hardware
- MCU: ESP32-S2-WROVER (single-core, Wi-Fi 2.4 GHz b/g/n). **No Bluetooth** on ESP32-S2.
- IMU: MPU6050. Optional add-ons: PMW3901+VL53L1X (position hold), MS5611 (height hold), HMC5883 (compass).
- Battery: 1S LiPo 3.7 V, 300-800 mAh. Never above 4.2 V.
- Firmware preinstalled (Espressif esp-drone, Crazyflie port, GPL-3.0).

## Unit #1 (observed 2026-11-16 via USB boot log)
- Chip: ESP32-S2FNR2 rev v1.0, 4 MB embedded flash, 2 MB PSRAM. AP MAC 90:e5:b1:99:a3:33, STA MAC ...:32.
- USB = CP2102 USB-UART bridge -> `/dev/cu.usbserial-0001`. 115200 reliable; 460800/921600 fail
  ("Invalid head of packet (0xFF)"). esptool auto-reset via DTR/RTS works.
- Firmware: project `ESPDrone`, "ESPlane 2.0", app version `cbe4e80-dirty` (vendor build,
  source not published), built Jul 3 2025, ESP-IDF v5.0.8.
- Factory flash backup: `firmware-backup/esp32s2-drone-90e5b199a333-factory.bin` (4 MB, gitignored,
  sha256 in `.sha256`). Restore: `esptool --port /dev/cu.usbserial-0001 --baud 115200 write-flash 0 <bin>`.
- SSID `ESP-DRONE_90E5B199A333`, pass `12345678`, UDP server port 2390.
- **ESP-NOW enabled** in firmware (esp-now 2.5.2) - possible drone-to-drone / host-dongle link for swarm.
- Sensors: MPU6050 OK. VL53L1X, PMW3901, Z-down ToF = FAIL (not fitted; no flow deck).
- Estimator: complementary. Self-test passed, "Ready to fly" ~6.5 s after boot.
- Serial console prints only at boot. Tools: `.venv` from `/usr/bin/python3` (cflib fork, pyserial, esptool 4.x).
- **Do not reset via RTS/EN while the drone is powered.** 2nd RTS reset left MPU6050 I2C stuck ->
  `E SENSORS: MPU6050 I2C connection [FAIL]` -> `rst:0x3 RTC_SW_SYS_RST` boot loop every ~2.5 s.
  Recover with full power cycle (USB + battery out). Firmware reboots itself when IMU missing.
- Partition table: nvs 0x9000, phy_init 0xf000, single `factory` app 0x10000 (1 MB). No OTA slots.

## Extension headers (from Espressif V1.2 schematic; B-Cube V2.0 not confirmed)
Source: `vendor/esp-drone/hardware/ESP32_S2_Drone_V1_2/SCH_Mainboard_ESP32_S2_Drone_V1_2.pdf`. 2x 8-pin 2.54 mm.
| Pin | J3 (I2C/buzzer) | J4 (SPI/I2C1, flow deck) |
| --- | --- | --- |
| 1 | VDD33 (3.3 V) | SPI_CS0 GPIO34 |
| 2 | I2C0_SDA GPIO11 (MPU6050 bus) | SPI_MOSI GPIO35 |
| 3 | I2C0_SCL GPIO10 | SPI_CLK GPIO36 |
| 4 | GND | SPI_MISO GPIO37 |
| 5 | AUX_SCL (MPU6050 aux master) | GND |
| 6 | AUX_SDA | I2C1_SDA GPIO40 (VL53L1X) |
| 7 | BUZ_2 GPIO38 | I2C1_SCL GPIO41 |
| 8 | BUZ_1 GPIO39 | EXT_IO1 GPIO1 (also BOOT button) |
J4 has no power pin: a deck on J4 alone needs 3.3 V from J3 pin 1.

## Link
| Layer | Value |
| --- | --- |
| Physical | Drone = Wi-Fi AP, client = STA |
| SSID / pass | `ESP-Drone_XXXXXX` / `12345678` |
| Transport | UDP, drone `192.168.43.42:2390`, client local port 2399 |
| Protocol | CRTP (Crazyflie) + 1 trailing checksum byte = sum(bytes) % 256 |

CRTP header byte = `port<<4 | 0b11<<2 | channel`. Ports: 0 console, 2 param, 3 commander
(roll/pitch/yaw/thrust), 5 log, 7 generic setpoint, 13 platform, 15 link.

## Clients
- Phone: "ESP-Drone" app (iOS App Store / Android APK from Espressif docs).
- PC: cfclient fork `https://github.com/qljz1993/crazyflie-clients-python`, URI `udp://192.168.43.42`.
- Python lib: cflib fork `https://github.com/qljz1993/crazyflie-lib-python`, branch `esp-drone`
  (`esplane` no longer exists), commit a430283, cloned to `vendor/` (gitignored), installed editable.
  Local patch `tools/cflib-udp-macos.patch` (re-apply with `git apply` after re-clone):
  1. `sendto()` on connected UDP socket -> `OSError: [Errno 56] Socket is already connected` on macOS; use `send()`.
  2. Drone only transmits while it hears from host (like CF radio acks). Unpatched driver stops sending
     after connect -> log stream dies ~2.4 s in. Patch: 20 ms recv timeout, send CRTP null on timeout.
     Before: 24 then 0 samples/3 s; after: 30/30 at 10 Hz.
- cflib test: `.venv/bin/python tools/drone_link_test.py [--no-thrust]` (connect, params, logs, setpoints).
- Log block payload max ~26 bytes: split blocks (8 floats fails `add_config`).
- `motor.m*` log goes STALE under emergency stop; use `pwm.m*_pwm` for real output.
- `stabilizer.stop` param = emergency stop latch. Observed latched =1 after a thrust pulse while board
  was inverted (roll ~178 deg); then PWM stays 0 although `stabilizer.thrust` follows commands. Clears on reboot.
- `sys.canfly`=0 on USB power (likely charging/USB check).
- Raw probe (stdlib only, no motor commands): `/usr/bin/python3 -I tools/drone_probe.py`.
  Firmware ignores CRTP null (0xFF); use link echo (0xFC) for liveness. Param TOC: 183 params, crc 0xa6ac266c.

## Mac network setup (verified 2026-11-16)
- Internet via Pixel 9 Pro USB tethering (CDC-NCM, no driver; Settings > Network & internet >
  Hotspot & tethering > USB tethering). Service "Pixel 9 Pro" (en16) moved to top of service order.
  Previous order saved in `/tmp/service_order_before.txt` (Wi-Fi was first).
- Wi-Fi en0 joins drone: `networksetup -setairportnetwork en0 ESP-DRONE_90E5B199A333 12345678` -> 192.168.43.43.
  Default route stays on en16.
- macOS Local Network privacy: uv-downloaded `.venv` python gets `OSError: [Errno 65] No route to host`
  to 192.168.43.42; `/usr/bin/python3` and `ping` work. For cflib, build venv from `/usr/bin/python3`.

## LEDs
- Tail green fast blink = client connected.
- Head red blink = battery low.

## Swarm implications (open questions)
- Every drone is its own AP with the same IP 192.168.43.42. One PC Wi-Fi card joins one drone only.
- Swarm options: (a) firmware change to STA mode, all drones join one router, unique IPs;
  (b) ESP-NOW (already in firmware) from an ESP32 USB dongle on host, MAC-addressed, no AP;
  (c) one USB Wi-Fi dongle per drone (does not scale). Evaluate (a) vs (b). Verify STA support in
  `components/drivers/general/wifi/wifi_esp32.c` of espressif/esp-drone.
- Re-flashing needs ESP-IDF (docs reference release v4.4) over USB.
- No onboard absolute positioning: swarm formation needs external positioning
  (flow deck gives only relative hold, drift accumulates).

## External position (camera) - tested 2026-11-16
- Test: `.venv/bin/python tools/extpos_test.py` (Kalman estimator at runtime, fake positions on CRTP port 6,
  no thrust). Result FAIL: estimate drifts identically with none / `send_extpos` / `send_extpose`
  (-4.1, +5.9, -1.6 m after 6 s in all three). Vendor firmware ignores port 6. No `locSrv` param, no `ext_pos` log.
- Upstream espressif/esp-drone (9d5a4f8, 2026-10-26, ESP-IDF release/v5.5 or v6.1, S2 supported) has
  `modules/src/crtp_localization_service.c` (extpos -> `estimatorEnqueuePosition`) and `peer_localization.c`,
  but `locSrvInit()` is commented out in `modules/src/comm.c:61` and the .c is not in
  `components/core/crazyflie/CMakeLists.txt`. Fix = custom build: add file(s) to CMake, call `locSrvInit()`.
- Kalman with no position input drifts metres within seconds at rest: camera dropout must trigger landing fast.
- Camera-only positioning (no flow board) is viable once extpos works; height from one overhead camera is
  noisy -> add VL53L1X or 2nd camera if needed.

## Flow + height sensors to buy (2026-11-17, nothing bought)
- No drop-in board exists: Espressif's position-hold extension board was never sold; generic PMW3901+VL53L0X
  combo boards have reversed pin order vs drone header (esp-drone issue #93). Use two breakouts + wires.
- Firmware expects (upstream Kconfig, target ESP32_S2_DRONE_V1_2; V2.0 header unverified, check by continuity):
  - PMW3901 on SPI: MISO GPIO37, MOSI GPIO35, CLK GPIO36, CS GPIO34 (`flowdeck_v1v2.c`, CONFIG_SPI_PIN_CS0).
  - VL53L1X on I2C1: SDA GPIO40, SCL GPIO41 (`zranger2.c`, I2C1_DEV). Must be L1X (4 m), not L0X.
  - Both 3.3 V from VDD33. Both mount underneath facing floor. Flow axis orientation may need firmware flip.
- Mounting vs battery underneath (untested): (1) sensors taped flat to underside of battery holder, wires
  around; (2) battery to top (velcro/band, Crazyflie layout), sensors on board underside; (3) small bracket
  beside battery, clear of props. Keep level, near centre, 4-5 mm landing legs so lenses never touch floor.
  Optical cones: PMW3901 42 deg, VL53L1X 27 deg - nothing (battery edge, legs, wires) in view.
- Bitcraze Flow deck v2 (checked 2026-11-17 vs schematic flow-deck-v2-reva.pdf): 21x28x4 mm, 1.6 g, PMW3901 +
  VL53L1X. Fits electrically, not mechanically: CF headers 2x10 at 2.0 mm pitch vs drone 2x8 CON8 2.54 mm.
  Hand-wire 9 lines (2 mm male pins into deck sockets, wires to drone header):
  L1 VCC -> 3.3V, L10 GND -> GND, L4 SDA -> GPIO40, L5 SCL -> GPIO41, L8 IO_3 (=PMW CS) -> GPIO34,
  R3 SCK -> GPIO36, R4 MISO -> GPIO37, R5 MOSI -> GPIO35, R9 VCOM -> 3.3V (feeds TLV70218 1.8 V LDO for
  PMW3901, input 2-5.5 V; or VBAT). Unused: UARTs, IO_1/2/4, WKUP, VUSB, OW (DS28E05; esp-drone probes
  sensors directly in sensors_mpu6050_hm5883L_ms5611.c, no 1-wire detection). XSHUT pulled up on deck.
  Axis flip in flowdeck_v1v2.c matches CF mounting; check direction if deck rotated.
  User reports drone header also 2.0 mm pitch. Direct plug still NOT possible: pin order differs
  (esp-drone hardware.rst V1.2 header: L CS0/MOSI/CLK/MISO/GND/I2C1_SDA/I2C1_SCL/EXT_IO1,
  R VDD33/I2C0_SDA/I2C0_SCL/GND/AUX_SCL/AUX_SDA/BUZ2/BUZ1). Deck VCC would land on CS0, deck GND off header.
  Use 2.0 mm female-female jumper wires (or small adapter PCB). Do not use I2C0 (MPU6050 bus).
- NOT compatible: UART/MSP modules (Holybro PMW3901, Matek 3901-L0X, B-Cube INAV optical flow module).
- Parts: Pimoroni PIM453 PMW3901 breakout (SPI, 24x24x5 mm, ~5 g, 6 mA, white LEDs) + Pololu 3415 VL53L1X
  (13x18x2 mm, 0.5 g, 2.6-5.5 V, I2C pull-ups to VIN) or any VL53L1X breakout.
- Shops (stock seen 2026-11-17): PIM453 at Mouser (stock 34-135) or shop.pimoroni.com/en-eu; VL53L1X at
  dratek.cz (243 Kc, 149 in stock, verify page is L1X), TME (POLOLU-3415). botland.cz Pololu 3415 out of stock.
  Avoid makerklang.shop (-42%, fake urgency).

## Swarm without external positioning (analysis 2026-11-17, untested)
- IMU only: measured start positions do not help. No velocity/height measurement -> drift ~0.5-1+ m within
  seconds (Kalman test: metres in 6 s at rest), height follows battery sag. Safe only: synchronized short
  hops (1-2 s), spins, LED shows, tethered/rig demos.
- Flow deck (PMW3901 + VL53L1X) per drone + measured start grid = dead reckoning in shared frame.
  Error grows with distance flown (est. few % - 10%, unverified). Enough for short scripted choreography
  with >= 1-2 m spacing; no correction once drifted. Cheapest real swarm step.
- ESP-NOW RSSI between drones: metres error, not usable for spacing.
- Relative sensing between drones (from general knowledge, unverified):
  - UWB peer ranging (TWR, DW1000/DW3000): ~10 cm distance, no direction. Relative x,y observable only
    with own velocity (flow deck) + height + heading exchanged over radio, EKF per pair. TU Delft MAVLab
    did this on Crazyflies. Easiest HW: Qorvo DWM1001C/DWM3001C (own MCU, ranging over UART). Pairs =
    N(N-1)/2 -> fine for ~5-10 drones. No anchors, no shared room frame (formation only, drifts as a whole).
  - Side ToF (VL53L1X x4, like CF multi-ranger): ~4 m, 27 deg cone, detects but cannot identify -> collision
    avoidance only.
  - IR LED beacon + photodiode ring (bearing + rough range from intensity): DIY, cm-dm, sunlight-sensitive.
  - Wi-Fi FTM drone-to-drone (S2 supports): ~1-2 m, too coarse. Ultrasonic: prop noise, weight. Onboard
    camera: S2 too weak.

## Camera choice (2026-11-16, not bought/tested)
- Needs: global shutter (no rolling-shutter skew), >= 60 fps, manual exposure ~1-2 ms, UVC on macOS.
- Pixel budget: ~3 m wide area, tag must be >= ~20 px across. 1920 px -> 4 cm tag ~25 px; 1280 px -> ~17 px
  (need 5-6 cm tag or smaller area).
- Pick: Arducam AR0234 USB3 global shutter (B0495, 1920x1200, up to 80 fps at 960x600, M12 95 deg, ~$140).
  Budget: Arducam OV9281 USB2 mono global shutter (B0332, 1280x800 @120 fps, ~$63; known macOS
  AVFoundation freeze, see wpilibsuite/allwpilib#7960).
- Lens specs (datasheets, 2026-11-17):
  - AR0234 B0495: EFL 3.6 mm, F3.0, FOV 95 D / 82 H / 66 V, 3% distortion, IR-cut, manual focus
    (factory 2 m-inf; refocus for 1-2 m). 1/2.6", 3 um px. YUY2: 1920x1200 @50 fps, 960x600 @80 fps (USB3 only).
  - OV9281 B0332: FOV 70 H (EFL not stated; ~2.7-2.8 mm computed from 1/4" 3.84 mm width), M12 P0.5,
    no IR filter (IR markers possible). 120 fps only in MJPG; YUY2 1280x800 = 10 fps.
- Floor coverage at 2.7 m mount: AR0234 ~4.7 x 3.5 m, OV9281 ~3.8 x 2.4 m. Drone at 1 m altitude sees
  ~63% of that. 4 cm tag at floor: AR0234 ~16 px, OV9281 ~13 px -> use bigger tags or narrower lens.
- Prototype pipeline first with Mac/phone camera at 30 fps before buying.

## Indoor radio positioning without height / flow sensors (analysis 2026-11-16, untested)
- Feasible in principle: absolute 3D position at high rate replaces both sensors. Kalman takes x,y,z from
  radio, velocity derived from position + IMU. Bitcraze flies Crazyflie + Loco deck alone (no flow/ToF).
- Requirement for control: ~10 cm accuracy, >= 20-50 Hz, shared room frame. Only UWB meets it.

| Option | Accuracy | Rate | Verdict |
| --- | --- | --- | --- |
| Wi-Fi RSSI | 2-5 m | low | useless for flight |
| Wi-Fi FTM / 802.11mc RTT (ESP32-S2 supports) | ~1-2 m indoor | few Hz per AP | too coarse; logging only |
| BLE AoA | n/a | n/a | ESP32-S2 has no BLE |
| UWB TDoA (DW1000, Bitcraze LPS) | ~10 cm xy, z worse | 100+ Hz | only viable radio option |
| UWB RTLS kit (Qorvo DWM1001/MDEK) | ~10 cm xy | ~10 Hz | works via host extpos, marginal rate |

- UWB TDoA3: tags only listen -> unlimited drones, fits swarm. TWR mode limits tag count.
- Z without ToF: from UWB only, needs anchors at two heights (4 near floor, 4 near ceiling, 8 total).
  z noise worst near floor -> rougher takeoff/landing. VL53L1X (~2 g, cheap) still worth adding later.
- Cost: Bitcraze Loco anchors ~8x + deck per drone (EUR 1000+). DIY: DW1000 modules + Bitcraze
  lps-node-firmware is STM32-based; DWM3000 not compatible with LPS protocol.
- Firmware work: port Crazyflie `locodeck.c` + `lpsTdoa3Tag.c` + libdw1000 to esp-drone (SPI + IRQ on
  deck header, same FreeRTOS). Those are the blocks currently `#if 0` in our build. Medium effort.
  Shortcut: standalone UWB tag computes position, host forwards via extpos (same path as camera).
- Anchor setups ranked (2026-11-17, unverified figures): (1) Bitcraze Loco TDoA3 = best (rate, unlimited
  tags), needs DW1000 driver port. (2) DWM1001/DWM3001C anchors + tag on drone, tag computes position,
  UART to ESP32-S2 or host extpos; ~10 Hz, rate splits across tags -> few drones, Kalman must bridge gaps.
  (3) Optical anchors: Bitcraze Lighthouse (2x SteamVR 2.0 base stations), mm accuracy, unlimited drones,
  but deck = photodiodes + FPGA, hard port; also `#if 0` in our build.
- Cheapest DWM kit (prices/specs checked 2026-11-17, nothing bought):
  - MDEK1001 (12-board kit) is EOL. DWM1001-DEV still sold, $29.50 (Qorvo store/DigiKey). DWM1001 = only
    Qorvo part with ready RTLS firmware (PANS: anchors, tags, listener). DWM3001CDK $29.50 = SDK/TWR demos, no
    ready network. Ai-Thinker BU03 ($11) = bare DW3000 RF, needs own driver; not a kit.
  - Plan: 4-6x DWM1001-DEV as anchors (USB powered) + 1x DWM1001-DEV listener on Mac USB + bare DWM1001C
    module (~$17-20 resellers) per drone. ~$150 infra + ~$20/drone.
  - Drone side: tag needs only 3.3 V + GND (positions read by listener -> extpos over Wi-Fi). Later option:
    read `dwm_loc_get` over header SPI (GPIO 34-37 per Espressif V1.2 docs; V2.0 unverified).
  - DWM1001C: 19.1 x 26.2 x 2.6 mm, 2.8-3.6 V (NOT direct 1S, 4.2 V), RX 134 mA / TX 82 mA. Accuracy
    <15 cm 2D, <30 cm 3D (Qorvo). Weight not in datasheet (reseller says 9.8 g, doubtful) -> weigh.
    DWM1001-DEV is 62 x 43 mm, 3.6-5.5 V -> too big/wrong voltage for drone.
  - Board 3.3 V LDO = SGM2205 (800 mA rated). ESP32-S2 Wi-Fi peaks ~300 mA + DWM 134 mA -> fits on paper.
  - Open: payload (weigh drone + thrust test), whether bare DWM1001C ships with PANS (else SWD flash),
    antenna keep-out away from LiPo/motors, PANS tag count at 10 Hz.
- UWB 3.5-6.5 GHz: no conflict with 2.4 GHz Wi-Fi/ESP-NOW link. Added mass must fit 1S payload.
- Decision: camera extpos first (hardware we have, firmware path in progress). UWB = upgrade if camera
  coverage/occlusion/latency fails. Same extpos plumbing serves both.

## Custom firmware (flashed 2026-11-16) - extpos PASS
- Source: `vendor/esp-drone` = espressif/esp-drone 9d5a4f8 + `firmware/esp-drone-locsrv.patch`
  (CMake adds crtp_localization_service.c + peer_localization.c; `locSrvInit()` enabled; Lighthouse/LPS
  handlers `#if 0`; debug.h -> debug_cf.h; cfassert.h; GCC 14 quatdecompress fix).
- Config overlay `firmware/sdkconfig.slunecnice`: TARGET_ESP32_S2_DRONE_V1_2 + MOTOR_BRUSHED_715 (vendor PID
  190/440/2.6 and thrustBase 42000/thrustMin 8000 match this). Vendor param values: `firmware-backup/vendor-params.json`.
- Toolchain: ESP-IDF v5.5.6 at `~/esp/esp-idf` (cmake/ninja via `idf_tools.py install cmake ninja`).
  Build: `. ~/esp/esp-idf/export.sh && cd vendor/esp-drone && idf.py build`.
  Flash: `cd build && ../../../.venv/bin/esptool.py --chip esp32s2 -p /dev/cu.usbserial-0001 -b 115200 write_flash @flash_args`.
  Image 0xDDED0, 13% free of 1 MB app partition.
- Result: boots clean, same SSID, 187 params (adds `locSrv.*`, log `ext_pos.X/Y/Z`). `tools/extpos_test.py` PASS
  (estimate = sent position, err 0.000 m).
- **Boots disarmed** (upstream 1982d8c): `sys.armed` never set; motors only with param `system.forceArm=1`
  (runtime, resets on boot). `drone_link_test.py` arms/disarms around pulse. Pulse 12000 -> pwm 9.3k-14.7k.
  **The phone app will likely not spin motors** on this firmware (it does not set forceArm) - untested.
- cflib on py3.9 may print `Fatal Python error: _enter_buffered_busy` / exit 134 at shutdown (daemon thread);
  results printed before it are valid.

## Height control without sensor (2026-11-17)
- `tools/hover.py`: auto take-off (thrust ramp until accelerometer sees lift-off = hover thrust), then pilot
  holds height with LEFT STICK (centre = hover thrust + damping, +-12 %), A = auto landing, B = kill.
  `--sim` offline checks, `--dry` real drone disarmed/thrust 0. Logs `logs/hover-*.csv`.
- Fully automatic hold rejected: 1-D sim shows accelerometer-only hold climbs 2-4.5 m in 3 s from a
  0.005 g bias or 3 % hover-thrust error. Real hold needs VL53L1X (firmware supports, J4 I2C1 + J3 3.3 V) or camera.
- Dry run on drone: ground vz_est +-0.003 m/s with motors off (threshold 0.15). Not yet flown.
- First flights 2026-11-17 (logs/hover-20261117-1253*.csv): lifts off ~54.5k, hover est ~49.5k, battery sags
  3.8 -> 3.2 V under load. Pilot held stick down (hover est too high). Landing (A) stalled: full damping
  cancelled the descent -> now damping only brakes descents > 0.5 m/s, gain ramps 0.92 -> 0.82, and stick
  centre learns toward the pilot's average (LEARN_S 6 s, +-12 %).
- Roll trim +2.0 drifted right ~1 m/s while roll held +2.0 -> setpoint sign opposite to bench offset; trim now -2.0.
  D-pad trim works in hover.py too (saved to tools/fly_trim.json). Not yet flight-verified.

## Status
- [x] USB serial works, boot self-test passed, factory flash backed up (2026-11-16)
- [x] Wi-Fi AP up on USB power, Mac joined, probe echo 10/10 (2026-11-16)
- [x] Battery: on 1S, 3.86 V. Level = roll ~2 deg, battery pack facing down.
- [x] cflib full chain (2026-11-16): params, logs 10 Hz, setpoint 12000 -> pwm max 17404 -> 0 on zero; e-stop stays 0
- [x] Custom firmware with extpos flashed + verified (2026-11-16)
- [ ] cfclient connects, attitude live
- [x] Motors soldered; per-motor test `tools/motor_test.py [ratio] [on_s]` (e.g. 6500 3): all 4 spin,
  directions correct per user (2026-11-17). `tools/motor_spin.py N` = spin one until `touch /tmp/motor_stop`.
- [ ] Stick directions in `tools/fly.py` bench-verified (no props)
- [ ] Props installed (A/B)
- [x] Motor directions fixed (all were CW; M1+M3 wires swapped). Target from above: M1 CCW/B, M2 CW/A, M3 CCW/B, M4 CW/A.
- Level offset (2026-11-17): flat drone reads roll +1.94, pitch +0.50; 180 deg turn on floor changed it only +-0.17,
  so offset is in the drone (mounting). `tools/fly.py` trim: default roll +2.0, D-pad 0.5 deg steps, saved to
  `tools/fly_trim.json`. Trim sign not yet flight-verified.
