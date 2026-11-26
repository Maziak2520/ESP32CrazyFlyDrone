#!/usr/bin/env python3
"""Generate printable 2-page A4 landscape course infographic PDF for ESP32-S2 Crazyflie Drone build.

Output: docs/course-drone-build-infographic.pdf
Usage:  python3 tools/build_course_pdf.py
"""
import math
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

W, H = landscape(A4)  # 841.89 x 595.27 pt

# Palette (high-contrast, print-friendly)
NAVY = colors.HexColor("#0F172A")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748B")
LIGHT_BG = colors.HexColor("#F8FAFC")
CARD_BG = colors.HexColor("#FFFFFF")
BORDER = colors.HexColor("#CBD5E1")

BLUE = colors.HexColor("#1D4ED8")
BLUE_BG = colors.HexColor("#EFF6FF")
TEAL = colors.HexColor("#0F766E")
TEAL_BG = colors.HexColor("#F0FDFA")
GREEN = colors.HexColor("#15803D")
GREEN_BG = colors.HexColor("#F0FDF4")
AMBER = colors.HexColor("#B45309")
AMBER_BG = colors.HexColor("#FFFBEB")
RED = colors.HexColor("#B91C1C")
RED_BG = colors.HexColor("#FEF2F2")
PURPLE = colors.HexColor("#6D28D9")
PURPLE_BG = colors.HexColor("#F5F3FF")
CODE_BG = colors.HexColor("#F1F5F9")


def rrect(c, x, y, w, h, r=6, fill=None, stroke=None, lw=1):
    c.saveState()
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, fill=1 if fill is not None else 0, stroke=1 if stroke is not None else 0)
    c.restoreState()


def text(c, x, y, s, font="Helvetica", size=8, color=NAVY, align="left"):
    c.saveState()
    c.setFont(font, size)
    c.setFillColor(color)
    if align == "center":
        c.drawCentredString(x, y, s)
    elif align == "right":
        c.drawRightString(x, y, s)
    else:
        c.drawString(x, y, s)
    c.restoreState()


def wrap_lines(c, s, font, size, max_w):
    words = s.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if c.stringWidth(test, font, size) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def paragraph(c, x, y, s, font="Helvetica", size=7.4, color=SLATE, max_w=200, leading=9.4):
    for line in wrap_lines(c, s, font, size, max_w):
        text(c, x, y, line, font=font, size=size, color=color)
        y -= leading
    return y


def draw_header(c, page_num, subtitle):
    rrect(c, 18, H - 54, W - 36, 40, r=6, fill=NAVY, stroke=None)
    text(c, 28, H - 31, "ESP32-S2 OPEN-SOURCE DRONE LAB  •  FROM BARE PCB TO 0.50 m LASER HOVER",
         font="Helvetica-Bold", size=12.5, color=colors.white)
    text(c, 28, H - 45, subtitle, font="Helvetica", size=8.5, color=colors.HexColor("#93C5FD"))
    rrect(c, W - 185, H - 47, 157, 26, r=5, fill=GREEN, stroke=None)
    text(c, W - 106.5, H - 32, "COURSE MISSION OBJECTIVE", font="Helvetica-Bold", size=6.5,
         color=colors.HexColor("#DCFCE7"), align="center")
    text(c, W - 106.5, H - 42, "Gamepad Flight + 0.50 m Hover & Land", font="Helvetica-Bold", size=7.8,
         color=colors.white, align="center")


def draw_footer(c, page_num):
    c.saveState()
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.7)
    c.line(18, 22, W - 18, 22)
    c.restoreState()
    text(c, 20, 11, "Repository: https://github.com/Maziak2520/ESP32CrazyFlyDrone   •   Hardware: B-Cube ESP32-S2-Drone V2.0 + MPU6050 + CJMCU-531 (VL53L1X) + Stadia BLE Controller",
         font="Helvetica", size=7, color=MUTED)
    text(c, W - 20, 11, f"Page {page_num} of 2", font="Helvetica-Bold", size=7.5, color=SLATE, align="right")


def draw_arch_bar(c, x, y, w, h):
    rrect(c, x, y, w, h, r=6, fill=BLUE_BG, stroke=colors.HexColor("#BFDBFE"), lw=1)
    text(c, x + 10, y + h - 13, "SYSTEM ARCHITECTURE", font="Helvetica-Bold", size=7.5, color=BLUE)
    text(c, x + 10, y + 6, "Internet stays on Phone USB Tethering (en16) while Mac Wi-Fi (en0) joins Drone AP:",
         font="Helvetica", size=7, color=SLATE)

    nodes = [
        (x + 295, "1. Stadia Gamepad", "Bluetooth LE (SDL2)", PURPLE, PURPLE_BG),
        (x + 425, "2. Mac Host (.venv)", "tools/fly.py + cflib", BLUE, colors.white),
        (x + 565, "3. ESP32-S2 Drone AP", "UDP 192.168.43.42:2390", TEAL, TEAL_BG),
        (x + 700, "4. Onboard Sensors", "MPU6050 + VL53L1X", GREEN, GREEN_BG),
    ]
    for i, (nx, title, sub, col, bg) in enumerate(nodes):
        rrect(c, nx, y + 4, 102, h - 8, r=4, fill=bg, stroke=col, lw=1)
        text(c, nx + 51, y + h - 13, title, font="Helvetica-Bold", size=7.2, color=col, align="center")
        text(c, nx + 51, y + 7, sub, font="Helvetica", size=6.5, color=SLATE, align="center")
        if i < len(nodes) - 1:
            ax1 = nx + 103
            ax2 = nodes[i + 1][0] - 2
            my = y + h / 2
            c.saveState()
            c.setStrokeColor(SLATE)
            c.setLineWidth(1.2)
            c.line(ax1, my, ax2, my)
            c.line(ax2 - 4, my + 3, ax2, my)
            c.line(ax2 - 4, my - 3, ax2, my)
            c.restoreState()


def draw_step_card(c, x, y, w, h, num, title, badge, badge_col, badge_bg,
                   why, cmd, pitfall, tip, verify):
    rrect(c, x, y, w, h, r=6, fill=CARD_BG, stroke=BORDER, lw=1)
    # Top accent bar
    rrect(c, x, y + h - 22, w, 22, r=6, fill=badge_bg, stroke=badge_col, lw=1)
    # Number circle
    c.saveState()
    c.setFillColor(badge_col)
    c.circle(x + 13, y + h - 11, 7.5, fill=1, stroke=0)
    c.restoreState()
    text(c, x + 13, y + h - 13.8, str(num), font="Helvetica-Bold", size=8, color=colors.white, align="center")
    text(c, x + 24, y + h - 14, title, font="Helvetica-Bold", size=7.8, color=NAVY)
    text(c, x + w - 6, y + h - 14, badge, font="Helvetica-Bold", size=6.0, color=badge_col, align="right")

    cy = y + h - 33
    # Why / Theory
    text(c, x + 8, cy, "WHY:", font="Helvetica-Bold", size=6.8, color=badge_col)
    cy = paragraph(c, x + 30, cy, why, font="Helvetica", size=6.8, color=SLATE, max_w=w - 36, leading=8.4)

    # Command box
    cy -= 2
    cmd_lines = cmd.split("\n")
    box_h = 7 + len(cmd_lines) * 8.0
    rrect(c, x + 7, cy - box_h + 6, w - 14, box_h, r=3, fill=CODE_BG, stroke=BORDER, lw=0.6)
    ty = cy - 2.5
    for cl in cmd_lines:
        text(c, x + 10, ty, cl, font="Courier-Bold", size=6.1, color=NAVY)
        ty -= 8.0
    cy -= box_h + 4

    # Pitfall box
    pit_lines = wrap_lines(c, "PITFALL: " + pitfall, "Helvetica", 6.5, w - 22)
    p_h = 6 + len(pit_lines) * 7.8
    rrect(c, x + 7, cy - p_h + 6, w - 14, p_h, r=3, fill=AMBER_BG, stroke=colors.HexColor("#FDE68A"), lw=0.6)
    ty = cy - 2.5
    for pl in pit_lines:
        text(c, x + 11, ty, pl, font="Helvetica", size=6.5, color=AMBER)
        ty -= 7.8
    cy -= p_h + 4

    # What to observe / Lab note box
    tip_lines = wrap_lines(c, "OBSERVE: " + tip, "Helvetica", 6.5, w - 22)
    t_h = 6 + len(tip_lines) * 7.8
    rrect(c, x + 7, cy - t_h + 6, w - 14, t_h, r=3, fill=LIGHT_BG, stroke=BORDER, lw=0.5)
    ty = cy - 2.5
    for tl in tip_lines:
        text(c, x + 11, ty, tl, font="Helvetica", size=6.5, color=SLATE)
        ty -= 7.8

    # Verify gate pinned to bottom
    ver_lines = wrap_lines(c, verify, "Helvetica-Bold", 6.6, w - 30)
    v_h = 8 + len(ver_lines) * 7.8
    vy = y + 5
    rrect(c, x + 7, vy, w - 14, v_h, r=3, fill=GREEN_BG, stroke=colors.HexColor("#86EFAC"), lw=0.8)
    rrect(c, x + 11, vy + v_h - 11, 7, 7, r=1, fill=colors.white, stroke=GREEN, lw=1)
    ty = vy + v_h - 9.5
    for vl in ver_lines:
        text(c, x + 22, ty, vl, font="Helvetica-Bold", size=6.6, color=GREEN)
        ty -= 7.8


def build_page1(c):
    c.saveState()
    c.setFillColor(LIGHT_BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.restoreState()

    draw_header(c, 1, "PAGE 1: 7-STEP ITERATIVE ENGINEERING ROADMAP & VERIFICATION GATES (MOTORS OFF -> FLASH -> SOLDER -> TRIM -> 0.50 m HOVER)")
    draw_arch_bar(c, 18, H - 92, W - 36, 32)

    steps = [
        (1, "USB Backup & Wi-Fi Probe", "NO MOTORS", BLUE, BLUE_BG,
         "Connect to bare board before soldering motors. Save factory 4 MB flash image (vendor source is closed) and prove two-way CRTP UDP link.",
         "esptool.py -p /dev/cu.usbserial-0001 \\\n  -b 115200 read_flash 0 0x400000 bk.bin\n/usr/bin/python3 -I tools/drone_probe.py",
         "ESP32-S2 has NO Bluetooth. CP2102 corrupts at 460800+ baud (use 115200). Firmware ignores 0xFF null probe (use 0xFC echo).",
         "Tail green LED blinks fast when UDP link is alive; head red LED indicates low battery.",
         "CHECK: 4 MB backup saved; join ESP-DRONE_*, probe prints 'echo 10/10, 183 params'."),
        (2, "cflib Telemetry & Link Patch", "BENCH TEST", BLUE, BLUE_BG,
         "Stream 10-50 Hz attitude/battery logs and send test thrust pulses with motors detached to verify the full flight-controller loop.",
         "/usr/bin/python3 -m venv .venv\n.venv/bin/pip install -e \\\n  vendor/crazyflie-lib-python\n.venv/bin/python tools/drone_link_test.py",
         "1) macOS UDP sendto() fails with Errno 56 -> patch to send(). 2) Logs die after 2.4 s without 20 ms null keepalive. 3) Upside-down pulse latches stabilizer.stop=1!",
         "Under emergency stop, motor.m* logs freeze stale while pwm.m*_pwm shows true motor output (0).",
         "CHECK: Board flat (battery down, roll ~2 deg): pwm hits 17404 -> 0, RESULT: PASS."),
        (3, "Firmware Upgrade (locSrv)", "ESP-IDF v5.5", PURPLE, PURPLE_BG,
         "Why reflash? tools/extpos_test.py failed because upstream comm.c:61 had '//locSrvInit();' commented out! Enable it & flash release image.",
         "./tools/flash_drone.sh\n.venv/bin/python tools/extpos_test.py",
         "New firmware boots DISARMED for safety (requires system.forceArm=1). Never RTS-reset via USB while powered or MPU6050 I2C locks in boot loop.",
         "flash_drone.sh automatically backs up each new drone's 4 MB factory flash by MAC before writing.",
         "CHECK: 187 params (adds locSrv); extpos_test.py error = 0.000 m, RESULT: PASS."),
        (4, "Solder Motors & Spin Check", "PROPS", TEAL, TEAL_BG,
         "Solder 4 brushed 715 motors. Spin M1..M4 one by one at 10% power to verify corner mapping and CW/CCW rotation before fitting A/B props.",
         ".venv/bin/python tools/motor_test.py 6500 3\n# Single motor spin until stopped:\n.venv/bin/python tools/motor_spin.py 1",
         "Our first test had ALL 4 motors spinning CW -> drone couldn't lift! Diagonal pairs MUST counter-rotate: swap wires on M1 & M3.",
         "Install Prop B on CCW motors (M1, M3) and Prop A on CW motors (M2, M4) so all 4 push air DOWN.",
         "CHECK: Top view: M1(FR)=CCW/Prop B, M2(RR)=CW/Prop A, M3(RL)=CCW/Prop B, M4(FL)=CW/Prop A."),
        (5, "Gamepad & 3-Layer Trim", "CALIBRATE", TEAL, TEAL_BG,
         "Pair Stadia BLE controller. Cancel mounting tilt (~2 deg) so the drone lifts straight up instead of sliding sideways at 1 m/s.",
         ".venv/bin/python tools/gamepad_check.py 10\n.venv/bin/python tools/calibrate_level.py",
         "Floor contact != motor plane: rest drone on 4 equal supports under motor pods and rotate 0/90/180/270 deg so floor slope cancels.",
         "In flight, accelerometer feels thrust along body axis (blind to tilt); learn_trim() absorbs steady right-stick corrections into fly_trim.json.",
         "CHECK: fit spread < 0.3 deg; fly_trim.json saved; D-pad nudges 0.25 deg + in-flight stick learning."),
        (6, "Wire VL53L1X Laser Sensor", "I2C1 + 3V3", AMBER, AMBER_BG,
         "1-D physics sim proved accelerometer-only height hold runs away to 3-4 m in 3 s from 0.005 g bias. Add downward VL53L1X laser ranger (40 Hz).",
         "# Verify sensor detected at boot:\n.venv/bin/python tools/fly.py --seconds 2",
         "Left header J4 has NO 3.3V pin! Wire VCC->J3 Pin 1 (3V3), GND->J4 Pin 5, SDA->J4 Pin 6 (SDA1), SCL->J4 Pin 7 (SCL1). Peel yellow lens film!",
         "Firmware only probes VL53L1X once at power-on boot. Always power-cycle battery after touching sensor wires.",
         "CHECK: deck.bcZRanger2 = 1 at boot; lifting drone by hand updates live z=0.20m -> 0.65m."),
        (7, "0.50 m DJI Hover & Auto-Land", "FINAL MISSION", GREEN, GREEN_BG,
         "Closed-loop laser PID holds 0.50 m with tilt-thrust compensation (1/cos R*cos P), adaptive hover thrust, terrain-following & 0.25 m floor pause.",
         ".venv/bin/python tools/hover.py --sim\n.venv/bin/python tools/fly.py --sim\n.venv/bin/python tools/fly.py",
         "When loaded vbat drops < 3.38V (LOW-BAT!), hover needs ~56k+ thrust -> big tilts clip motors at 100% PWM. Fly on charged battery (>4.05V rest).",
         "Every flight saves full 50 Hz telemetry to logs/fly-YYYYMMDD-HHMMSS.csv for post-flight analysis.",
         "FINAL ACHIEVEMENT: Hold A (1 s) -> auto-takeoff to 0.50 m hover -> RT/LT climb/descend -> X lands!"),
    ]

    # Row 1: Steps 1..4 (4 cards across)
    margin = 18
    gap = 8
    w4 = (W - 2 * margin - 3 * gap) / 4.0
    h_row1 = 218
    y_row1 = H - 98 - h_row1
    for i in range(4):
        s = steps[i]
        draw_step_card(c, margin + i * (w4 + gap), y_row1, w4, h_row1, *s)

    # Row 2: Steps 5..7 (3 wider cards across)
    w3 = (W - 2 * margin - 2 * gap) / 3.0
    h_row2 = 214
    y_row2 = 28
    for i in range(3):
        s = steps[4 + i]
        draw_step_card(c, margin + i * (w3 + gap), y_row2, w3, h_row2, *s)

    draw_footer(c, 1)


def draw_rot_arc(c, cx, cy, r, ccw, col):
    """Draw a vector curved rotation arc with arrowhead around motor center."""
    c.saveState()
    c.setStrokeColor(col)
    c.setFillColor(col)
    c.setLineWidth(1.3)
    c.arc(cx - r, cy - r, cx + r, cy + r, startAng=25, extent=130)
    # Arrowhead at end of arc
    ang = math.radians(155 if ccw else 25)
    ax = cx + r * math.cos(ang)
    ay = cy + r * math.sin(ang)
    p = c.beginPath()
    if ccw:
        p.moveTo(ax - 2, ay - 4)
        p.lineTo(ax - 3, ay + 2)
        p.lineTo(ax + 3, ay + 1)
    else:
        p.moveTo(ax + 2, ay - 4)
        p.lineTo(ax - 3, ay + 1)
        p.lineTo(ax + 3, ay + 2)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()


def draw_drone_diagram(c, x, y, w, h):
    rrect(c, x, y, w, h, r=6, fill=CARD_BG, stroke=BORDER, lw=1)
    rrect(c, x, y + h - 22, w, 22, r=6, fill=TEAL_BG, stroke=TEAL, lw=1)
    text(c, x + 10, y + h - 14, "1. TOP-DOWN MOTOR & PROPELLER MAP (QUAD_FORMATION_X)", font="Helvetica-Bold", size=8.2, color=TEAL)

    cx, cy = x + w * 0.50, y + h * 0.51
    # Front arrow
    c.saveState()
    c.setStrokeColor(RED)
    c.setFillColor(RED)
    c.setLineWidth(2)
    c.line(cx, cy + 32, cx, cy + 68)
    p = c.beginPath()
    p.moveTo(cx, cy + 74)
    p.lineTo(cx - 5, cy + 65)
    p.lineTo(cx + 5, cy + 65)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()
    text(c, cx, cy + 84, "FRONT (Camera Connector)", font="Helvetica-Bold", size=7, color=RED, align="center")
    text(c, cx, cy - 86, "TAIL (PCB Wi-Fi Antenna)", font="Helvetica-Bold", size=6.8, color=SLATE, align="center")

    # X arms
    arm = 52
    c.saveState()
    c.setStrokeColor(SLATE)
    c.setLineWidth(4)
    c.line(cx - arm, cy - arm, cx + arm, cy + arm)
    c.line(cx - arm, cy + arm, cx + arm, cy - arm)
    c.restoreState()

    # Center PCB
    rrect(c, cx - 26, cy - 30, 52, 60, r=4, fill=NAVY, stroke=SLATE, lw=1.2)
    text(c, cx, cy + 12, "ESP32-S2", font="Helvetica-Bold", size=6.5, color=colors.white, align="center")
    text(c, cx, cy + 2, "MPU6050", font="Helvetica", size=6, color=colors.HexColor("#93C5FD"), align="center")
    text(c, cx, cy - 8, "Battery Down", font="Helvetica-Oblique", size=5.5, color=colors.HexColor("#CBD5E1"), align="center")
    # J4 / J3 headers on PCB
    rrect(c, cx - 23, cy - 22, 6, 32, r=1, fill=AMBER, stroke=None)
    text(c, cx - 15, cy - 19, "J4", font="Helvetica-Bold", size=5.5, color=AMBER)
    rrect(c, cx + 17, cy - 22, 6, 32, r=1, fill=BLUE, stroke=None)
    text(c, cx + 11, cy - 19, "J3", font="Helvetica-Bold", size=5.5, color=colors.HexColor("#60A5FA"))
    # USB-C on right edge
    rrect(c, cx + 23, cy + 8, 6, 14, r=1, fill=colors.HexColor("#94A3B8"), stroke=NAVY, lw=0.6)
    text(c, cx + 31, cy + 13, "USB-C", font="Helvetica-Bold", size=5.8, color=SLATE)

    # 4 Motors: (dx, dy, name, dir_str, ccw, prop, col, bg)
    motors = [
        (+arm, +arm, "M1 (GPIO5)", "CCW", True,  "PROP B", BLUE, BLUE_BG),
        (+arm, -arm, "M2 (GPIO6)", "CW",  False, "PROP A", AMBER, AMBER_BG),
        (-arm, -arm, "M3 (GPIO3)", "CCW", True,  "PROP B", BLUE, BLUE_BG),
        (-arm, +arm, "M4 (GPIO4)", "CW",  False, "PROP A", AMBER, AMBER_BG),
    ]
    for dx, dy, mname, rot, is_ccw, prop, col, bg in motors:
        mx, my = cx + dx, cy + dy
        c.saveState()
        c.setFillColor(bg)
        c.setStrokeColor(col)
        c.setLineWidth(1.6)
        c.circle(mx, my, 24, fill=1, stroke=1)
        c.restoreState()
        draw_rot_arc(c, mx, my, 27, is_ccw, col)
        text(c, mx, my + 8, mname, font="Helvetica-Bold", size=6.5, color=NAVY, align="center")
        text(c, mx, my - 1, f"({rot})", font="Helvetica-Bold", size=7.5, color=col, align="center")
        text(c, mx, my - 11, prop, font="Helvetica-Bold", size=6.8, color=GREEN if "B" in prop else PURPLE, align="center")

    # Bottom rule note
    rrect(c, x + 8, y + 6, w - 16, 28, r=4, fill=AMBER_BG, stroke=colors.HexColor("#FDE68A"), lw=0.7)
    text(c, x + 12, y + 23, "Golden Rule: Diagonal motors MUST spin the same way (M1+M3 = CCW/Prop B; M2+M4 = CW/Prop A).",
         font="Helvetica-Bold", size=6.3, color=AMBER)
    text(c, x + 12, y + 12, "If any motor spins the wrong way in 'tools/motor_test.py 6500 3', swap its two soldered motor wires.",
         font="Helvetica", size=6.3, color=SLATE)


def draw_wiring_diagram(c, x, y, w, h):
    rrect(c, x, y, w, h, r=6, fill=CARD_BG, stroke=BORDER, lw=1)
    rrect(c, x, y + h - 22, w, 22, r=6, fill=PURPLE_BG, stroke=PURPLE, lw=1)
    text(c, x + 10, y + h - 14, "2. B-CUBE V2.0 HEADER PINOUT (J4 vs J3) & VL53L1X LASER WIRING", font="Helvetica-Bold", size=8.2, color=PURPLE)

    text(c, x + 10, y + h - 34, "Counting Pin 1 = TOP (near Front / Camera connector) down to Pin 8 = BOTTOM (near Tail antenna):",
         font="Helvetica", size=6.8, color=SLATE)

    j4_pins = [
        ("1", "CS0",  "GPIO34 (SPI CS)", False),
        ("2", "SI",   "GPIO35 (MOSI)",   False),
        ("3", "CLK",  "GPIO36 (SCLK)",   False),
        ("4", "SO",   "GPIO37 (MISO)",   False),
        ("5", "GND",  "GROUND",          True),
        ("6", "SDA1", "GPIO40 (I2C1)",   True),
        ("7", "SCL1", "GPIO41 (I2C1)",   True),
        ("8", "IO1",  "GPIO1 (EXT_IO1)", False),
    ]
    j3_pins = [
        ("1", "3V3",  "3.3V SUPPLY",     True),
        ("2", "SDA0", "GPIO11 (MPU6050)", False),
        ("3", "SCL0", "GPIO10 (MPU6050)", False),
        ("4", "GND",  "GROUND",          False),
        ("5", "ASCL", "MPU6050 AUX_SCL", False),
        ("6", "ASDA", "MPU6050 AUX_SDA", False),
        ("7", "B2",   "GPIO38 (Buzzer-)", False),
        ("8", "B1",   "GPIO39 (Buzzer+)", False),
    ]

    top_y = y + h - 52
    row_h = 15.5
    text(c, x + 12, top_y + 4, "LEFT HEADER (J4 - near buttons)", font="Helvetica-Bold", size=7, color=NAVY)
    for i, (pin, lbl, desc, used) in enumerate(j4_pins):
        py = top_y - (i + 1) * row_h
        rrect(c, x + 10, py, 118, row_h - 1.5, r=2,
              fill=GREEN_BG if used else CODE_BG,
              stroke=GREEN if used else BORDER, lw=1 if used else 0.5)
        text(c, x + 14, py + 4, f"Pin {pin}: {lbl}", font="Helvetica-Bold", size=6.6, color=GREEN if used else NAVY)
        text(c, x + 62, py + 4, desc, font="Helvetica", size=6.1, color=SLATE)

    mx = x + 138
    text(c, mx + 2, top_y + 4, "RIGHT HEADER (J3 - near USB-C)", font="Helvetica-Bold", size=7, color=NAVY)
    for i, (pin, lbl, desc, used) in enumerate(j3_pins):
        py = top_y - (i + 1) * row_h
        rrect(c, mx, py, 118, row_h - 1.5, r=2,
              fill=RED_BG if used else CODE_BG,
              stroke=RED if used else BORDER, lw=1 if used else 0.5)
        text(c, mx + 4, py + 4, f"Pin {pin}: {lbl}", font="Helvetica-Bold", size=6.6, color=RED if used else NAVY)
        text(c, mx + 50, py + 4, desc, font="Helvetica", size=6.1, color=SLATE)

    sx = x + 266
    text(c, sx, top_y + 4, "CJMCU-531 (VL53L1X) MODULE", font="Helvetica-Bold", size=7, color=PURPLE)
    sensor_map = [
        ("VCC",   "Brown -> J3 Pin 1 (3V3)",     RED,    RED_BG),
        ("GND",   "Red -> J4 Pin 5 (GND)",       SLATE,  CODE_BG),
        ("SCL",   "Orange -> J4 Pin 7 (SCL1)",   AMBER,  AMBER_BG),
        ("SDA",   "Yellow -> J4 Pin 6 (SDA1)",   GREEN,  GREEN_BG),
        ("GPIO1", "Leave unconnected",           MUTED,  LIGHT_BG),
        ("XSHUT", "Leave open (10k pull-up)",    MUTED,  LIGHT_BG),
    ]
    for i, (spin, target, col, bg) in enumerate(sensor_map):
        py = top_y - (i + 1) * 19.5
        rrect(c, sx, py, w - 274, 17.5, r=3, fill=bg, stroke=col, lw=0.9)
        text(c, sx + 5, py + 5.5, spin, font="Helvetica-Bold", size=7, color=col)
        text(c, sx + 40, py + 5.5, target, font="Helvetica-Bold", size=6.4, color=NAVY)

    rrect(c, x + 8, y + 6, w - 16, 40, r=4, fill=RED_BG, stroke=colors.HexColor("#FECACA"), lw=0.8)
    text(c, x + 13, y + 34, "CRITICAL WIRING & MOUNTING CHECKS:", font="Helvetica-Bold", size=6.8, color=RED)
    text(c, x + 13, y + 24, "1. J4 has NO 3.3V pin! You MUST take 3V3 from Right Header J3 Pin 1, and GND/SDA1/SCL1 from Left Header J4 Pins 5, 6, 7.",
         font="Helvetica", size=6.5, color=NAVY)
    text(c, x + 13, y + 14, "2. Peel the yellow protective Kapton film off the VL53L1X optical window & tie wires clear of the 27 deg downward laser cone.",
         font="Helvetica", size=6.5, color=NAVY)


def draw_gamepad_cockpit(c, x, y, w, h):
    rrect(c, x, y, w, h, r=6, fill=CARD_BG, stroke=BORDER, lw=1)
    rrect(c, x, y + h - 22, w, 22, r=6, fill=BLUE_BG, stroke=BLUE, lw=1)
    text(c, x + 10, y + h - 14, "3. DJI-STYLE GAMEPAD FLIGHT COCKPIT  (.venv/bin/python tools/fly.py)", font="Helvetica-Bold", size=8.2, color=BLUE)

    controls = [
        ("Hold A (1.0 s)", "ARM & AUTO-TAKEOFF", "Unlocks motors & climbs smoothly to 0.50 m laser hover.", GREEN, GREEN_BG),
        ("RT or Left Stick UP", "CLIMB (+0.50 m/s)", "Climbs while held; release = locks & holds current height!", BLUE, BLUE_BG),
        ("LT or Left Stick DOWN", "DESCEND (-0.40 m/s)", "Descends while held; stops automatically at 0.25 m safety floor.", BLUE, BLUE_BG),
        ("LB / RB Bumpers", "HEIGHT TRIM -/+10 cm", "Clicks target hover altitude down/up by 0.10 m (0.20..2.00 m).", TEAL, TEAL_BG),
        ("X Button (or Hold Down)", "AUTO-LAND & DISARM", "At 0.25 m floor pause (or any height), smoothly lands & disarms.", PURPLE, PURPLE_BG),
        ("Right Stick (X / Y)", "ROLL & PITCH STEERING", "Tilts drone left/right/forward/back with 1/(cos R*cos P) lift boost.", NAVY, CODE_BG),
        ("Left Stick (Left/Right)", "YAW ROTATION", "Rotates heading counter-clockwise / clockwise (up to 90 deg/s).", NAVY, CODE_BG),
        ("D-Pad (Up/Down/L/R)", "0.25 deg TILT TRIM", "Nudges trim toward push direction + auto stick learning.", AMBER, AMBER_BG),
        ("B Button (Any Time)", "EMERGENCY KILL", "Cuts all 4 motors to 0 immediately & disarms.", RED, RED_BG),
    ]

    cy = y + h - 42
    row_h = 20.5
    for btn, action, desc, col, bg in controls:
        rrect(c, x + 8, cy, 98, row_h - 2.5, r=3, fill=bg, stroke=col, lw=0.9)
        text(c, x + 57, cy + 5.5, btn, font="Helvetica-Bold", size=6.7, color=col, align="center")
        text(c, x + 112, cy + 9.5, action, font="Helvetica-Bold", size=6.8, color=NAVY)
        text(c, x + 112, cy + 1.5, desc, font="Helvetica", size=6.3, color=SLATE)
        cy -= row_h


def draw_physics_box(c, x, y, w, h):
    rrect(c, x, y, w, h, r=6, fill=CARD_BG, stroke=BORDER, lw=1)
    rrect(c, x, y + h - 22, w, 22, r=6, fill=GREEN_BG, stroke=GREEN, lw=1)
    text(c, x + 10, y + h - 14, "4. FLIGHT TELEMETRY, BATTERY PHYSICS & TROUBLESHOOTING GUIDE", font="Helvetica-Bold", size=8.2, color=GREEN)

    items = [
        ("Why Steering on a Low Battery Drops Altitude (Mixer Saturation):",
         "A 1S LiPo starts at ~4.18 V at rest and drops ~0.5 V under load. When loaded vbat > 3.40 V, hover needs ~49,000-52,000 thrust (~78% PWM), leaving plenty of headroom. Once loaded vbat falls below 3.38 V (LOW-BAT!), hover needs 56,000-59,500 (~92%+ PWM). Rolling/pitching adds +8,000 to two motors (which clip at the 65,535 ceiling) and subtracts -8,000 from the opposite two motors — reducing total lift! Solution: fly.py warns at <3.92 V rest / <3.38 V load, scales max tilt to 65%, and auto-lands at <3.26 V."),
        ("Why Tilt-Thrust Compensation (1 / (cos(roll) * cos(pitch))) Is Needed:",
         "Tilting by 15 deg roll + 12 deg pitch tilts the thrust vector away from vertical, losing ~5.5% of vertical lift (~2,800 thrust) and angling the laser beam (distance = z / (cos R * cos P)). Both hover.py and fly.py multiply laser distance by cos R*cos P and boost thrust by 1/(cos R*cos P)."),
        ("How Smooth Terrain-Following Works Over a Table Edge:",
         "If the drone flies over a 60 cm table while hovering at 1.00 m, laser z_m jumps from 1.00 m to 0.40 m in 20 ms while accelerometer vertical speed is ~0. The controller resets z_ref to 0.40 m (avoiding a 100% throttle spike) and slews smoothly at 0.50 m/s up to 1.00 m above the table."),
        ("Quick Diagnostic Checklist When Something Misbehaves:",
         "• Drone prints 'z=NO_LASER' or 'bcZRanger2=0': Re-seat the 4 sensor wires (J3-1, J4-5,6,7) and POWER-CYCLE the drone (sensor only inits at boot).\n"
         "• Drone shoots up to ceiling in laser mode: Laser reads <0.05 m because yellow film is on lens or rainbow wire is hanging in the 27 deg cone.\n"
         "• 'Address already in use' (UDP 2399): Close any other running fly.py / hover.py terminal window before starting a new script."),
    ]

    cy = y + h - 34
    for heading, body in items:
        text(c, x + 10, cy, heading, font="Helvetica-Bold", size=7.0, color=NAVY)
        cy -= 9.5
        for line in body.split("\n"):
            cy = paragraph(c, x + 14, cy, line, font="Helvetica", size=6.5, color=SLATE, max_w=w - 24, leading=8.2)
        cy -= 4


def build_page2(c):
    c.saveState()
    c.setFillColor(LIGHT_BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.restoreState()

    draw_header(c, 2, "PAGE 2: WORKBENCH HARDWARE REFERENCE  •  MOTOR & PROP MAP, J3/J4 LASER PINOUT, DJI GAMEPAD COCKPIT & BATTERY PHYSICS")

    margin = 18
    gap = 10
    top_y = 268
    top_h = H - 62 - top_y
    bot_y = 28
    bot_h = top_y - bot_y - gap

    w_left = 335
    w_right = W - 2 * margin - gap - w_left

    draw_drone_diagram(c, margin, top_y, w_left, top_h)
    draw_wiring_diagram(c, margin + w_left + gap, top_y, w_right, top_h)
    draw_gamepad_cockpit(c, margin, bot_y, w_left, bot_h)
    draw_physics_box(c, margin + w_left + gap, bot_y, w_right, bot_h)

    draw_footer(c, 2)


def main():
    os.makedirs("docs", exist_ok=True)
    out_path = os.path.join("docs", "course-drone-build-infographic.pdf")
    c = canvas.Canvas(out_path, pagesize=landscape(A4))
    c.setTitle("ESP32-S2 Drone Build & 0.50m Laser Hover Course Infographic")
    c.setAuthor("ESP32CrazyFlyDrone Course")
    build_page1(c)
    c.showPage()
    build_page2(c)
    c.showPage()
    c.save()
    print(f"Generated {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    main()
