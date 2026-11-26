#!/usr/bin/env python3
"""Generate printable 2-page A4 landscape AI-assisted course infographic PDF for ESP32-S2 Drone build.

Course Pedagogy: Students DO NOT copy pre-made scripts. They partner with an AI Coding Agent to discover,
build, debug, and verify their own scripts step-by-step from bare PCB to 0.50 m DJI-style laser hover.

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
    text(c, 28, H - 31, "AI-NATIVE HARDWARE ENGINEERING LAB  •  BUILD & FLY AN ESP32-S2 DRONE WITH YOUR AI AGENT",
         font="Helvetica-Bold", size=12.0, color=colors.white)
    text(c, 28, H - 45, subtitle, font="Helvetica", size=8.3, color=colors.HexColor("#93C5FD"))
    rrect(c, W - 195, H - 47, 167, 26, r=5, fill=GREEN, stroke=None)
    text(c, W - 111.5, H - 32, "COURSE MISSION & AI RULE", font="Helvetica-Bold", size=6.5,
         color=colors.HexColor("#DCFCE7"), align="center")
    text(c, W - 111.5, H - 42, "No Pre-Made Scripts! Co-Build -> 0.50m Hover", font="Helvetica-Bold", size=7.4,
         color=colors.white, align="center")


def draw_footer(c, page_num):
    c.saveState()
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.7)
    c.line(18, 22, W - 18, 22)
    c.restoreState()
    text(c, 20, 11, "AI Engineering Rule: Never write flight code blindly — ask your AI to inspect hardware/docs, build a small probe/sim first, log CSV evidence, and iterate!",
         font="Helvetica-Bold", size=6.9, color=SLATE)
    text(c, W - 20, 11, f"Page {page_num} of 2", font="Helvetica-Bold", size=7.5, color=SLATE, align="right")


def draw_arch_bar(c, x, y, w, h):
    rrect(c, x, y, w, h, r=6, fill=BLUE_BG, stroke=colors.HexColor("#BFDBFE"), lw=1)
    text(c, x + 10, y + h - 13, "THE AI CO-ENGINEERING LOOP", font="Helvetica-Bold", size=7.5, color=BLUE)
    text(c, x + 10, y + 6, "Keep internet on Phone USB Tethering while Wi-Fi joins ESP-DRONE_* so your AI stays online!",
         font="Helvetica", size=6.3, color=SLATE)

    nodes = [
        (x + 295, "1. Prompt & Frame", "Give AI docs/photos/goal", PURPLE, PURPLE_BG),
        (x + 425, "2. AI Builds Probe/Sim", "Small script + self-test", BLUE, colors.white),
        (x + 565, "3. Run on Real Drone", "Capture logs / serial / CSV", TEAL, TEAL_BG),
        (x + 700, "4. Feed Evidence to AI", "AI diagnoses & refines", GREEN, GREEN_BG),
    ]
    for i, (nx, title, sub, col, bg) in enumerate(nodes):
        rrect(c, nx, y + 4, 102, h - 8, r=4, fill=bg, stroke=col, lw=1)
        text(c, nx + 51, y + h - 13, title, font="Helvetica-Bold", size=7.1, color=col, align="center")
        text(c, nx + 51, y + 7, sub, font="Helvetica", size=6.4, color=SLATE, align="center")
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
                   why, prompt_task, pitfall, tip, verify):
    rrect(c, x, y, w, h, r=6, fill=CARD_BG, stroke=BORDER, lw=1)
    rrect(c, x, y + h - 22, w, 22, r=6, fill=badge_bg, stroke=badge_col, lw=1)
    c.saveState()
    c.setFillColor(badge_col)
    c.circle(x + 13, y + h - 11, 7.5, fill=1, stroke=0)
    c.restoreState()
    text(c, x + 13, y + h - 13.8, str(num), font="Helvetica-Bold", size=8, color=colors.white, align="center")
    text(c, x + 24, y + h - 14, title, font="Helvetica-Bold", size=7.8, color=NAVY)
    text(c, x + w - 6, y + h - 14, badge, font="Helvetica-Bold", size=6.0, color=badge_col, align="right")

    cy = y + h - 33
    text(c, x + 8, cy, "GOAL:", font="Helvetica-Bold", size=6.7, color=badge_col)
    cy = paragraph(c, x + 32, cy, why, font="Helvetica", size=6.7, color=SLATE, max_w=w - 38, leading=8.2)

    # What to build with your AI (Prompt box)
    cy -= 2
    p_lines = wrap_lines(c, "CO-BUILD WITH AI: " + prompt_task, "Helvetica-Bold", 6.5, w - 22)
    box_h = 6 + len(p_lines) * 7.9
    rrect(c, x + 7, cy - box_h + 6, w - 14, box_h, r=3, fill=PURPLE_BG, stroke=colors.HexColor("#DDD6FE"), lw=0.7)
    ty = cy - 2.5
    for pl in p_lines:
        text(c, x + 11, ty, pl, font="Helvetica-Bold", size=6.5, color=PURPLE)
        ty -= 7.9
    cy -= box_h + 4

    # Pitfall box
    pit_lines = wrap_lines(c, "TRAP TO CATCH: " + pitfall, "Helvetica", 6.4, w - 22)
    p_h = 6 + len(pit_lines) * 7.7
    rrect(c, x + 7, cy - p_h + 6, w - 14, p_h, r=3, fill=AMBER_BG, stroke=colors.HexColor("#FDE68A"), lw=0.6)
    ty = cy - 2.5
    for pl in pit_lines:
        text(c, x + 11, ty, pl, font="Helvetica", size=6.4, color=AMBER)
        ty -= 7.7
    cy -= p_h + 4

    # Clue / Hardware fact box
    tip_lines = wrap_lines(c, "KEY CLUE: " + tip, "Helvetica", 6.4, w - 22)
    t_h = 6 + len(tip_lines) * 7.7
    rrect(c, x + 7, cy - t_h + 6, w - 14, t_h, r=3, fill=LIGHT_BG, stroke=BORDER, lw=0.5)
    ty = cy - 2.5
    for tl in tip_lines:
        text(c, x + 11, ty, tl, font="Helvetica", size=6.4, color=SLATE)
        ty -= 7.7

    # Verify gate pinned to bottom
    ver_lines = wrap_lines(c, verify, "Helvetica-Bold", 6.5, w - 30)
    v_h = 8 + len(ver_lines) * 7.7
    vy = y + 5
    rrect(c, x + 7, vy, w - 14, v_h, r=3, fill=GREEN_BG, stroke=colors.HexColor("#86EFAC"), lw=0.8)
    rrect(c, x + 11, vy + v_h - 11, 7, 7, r=1, fill=colors.white, stroke=GREEN, lw=1)
    ty = vy + v_h - 9.5
    for vl in ver_lines:
        text(c, x + 22, ty, vl, font="Helvetica-Bold", size=6.5, color=GREEN)
        ty -= 7.7


def build_page1(c):
    c.saveState()
    c.setFillColor(LIGHT_BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.restoreState()

    draw_header(c, 1, "PAGE 1: 7 MILESTONES TO CO-BUILD WITH YOUR AI AGENT  (DISCOVER -> BACKUP -> PATCH -> FLASH -> SOLDER -> CALIBRATE -> 0.50 m HOVER)")
    draw_arch_bar(c, 18, H - 92, W - 36, 32)

    steps = [
        (1, "Hardware Discovery & Probe", "NO MOTORS", BLUE, BLUE_BG,
         "Connect bare board via USB & Wi-Fi before soldering motors. Back up factory 4 MB flash and prove two-way UDP communication.",
         "Give AI the product URL & Espressif ESP-Drone docs. Ask it to: 1) back up 4 MB flash via USB serial, 2) write a zero-dependency UDP link probe.",
         "ESP32-S2 has NO Bluetooth. High USB baud (460800+) fails with packet noise (use 115200). Firmware ignores 0xFF null packets!",
         "Drone AP is 192.168.43.42:2390 (pass 12345678), client binds UDP 2399. CRTP packet adds 1 checksum byte = sum(bytes)%256. Use 0xFC echo.",
         "ACHIEVEMENT: 4 MB factory backup saved; your UDP probe gets 10/10 echo replies & reads Param TOC."),
        (2, "cflib Telemetry & Link Patch", "BENCH TEST", BLUE, BLUE_BG,
         "Stream live 50 Hz roll/pitch/vbat logs and send a 1 s low-thrust test pulse with motors detached to verify the control loop.",
         "Ask AI to install Espressif's crazyflie-lib-python fork (esp-drone branch) and write a script that streams logs & pulses thrust 0->12000->0.",
         "1) macOS UDP sendto() crashes with Errno 56. 2) Log stream dies after 2.4 s! 3) Pulsing thrust while board is upside-down latches emergency stop!",
         "Have AI debug why logs stop at 2.4 s (drone only transmits while receiving host packets -> add 20 ms null keepalive in udpdriver.py). Log pwm.m*_pwm.",
         "ACHIEVEMENT: Board upright (battery down): logs stream continuously & PWM pulses 0 -> >14000 -> 0."),
        (3, "Source Audit & Firmware Flash", "ESP-IDF v5.5", PURPLE, PURPLE_BG,
         "Why build custom firmware? Test if external position (CRTP port 6) works for future camera/swarm — then find out why firmware ignores it!",
         "Ask AI to write an extpos test, then search espressif/esp-drone C source for why port 6 / locSrv is dead, patch it, build & flash.",
         "In upstream comm.c:61, '//locSrvInit();' is commented out & crtp_localization_service.c is missing from CMake! Never RTS-reset via USB while powered.",
         "Match vendor 715 motor config (thrustBase=42000). New upstream firmware boots DISARMED for safety — your scripts must set system.forceArm=1.",
         "ACHIEVEMENT: Custom firmware flashed & verified; extpos test converges to sent (x,y,z) with 0.000 m error."),
        (4, "Solder Motors & Spin Check", "PROPS", TEAL, TEAL_BG,
         "Solder 4 brushed motors (props OFF). Build a per-motor spin tool to verify corner positions and CW/CCW rotation before fitting A/B props.",
         "Ask AI to find the firmware's direct motor-override parameters (motorPowerSet) and write a script to spin M1..M4 one by one at 10% power.",
         "If all 4 motors spin the same way (or diagonal pairs don't match), the drone spins on the ground and 2 props push air UP so it never lifts off!",
         "Look from above: M1(Front-Right) & M3(Rear-Left) must spin CCW (Prop B); M2(Rear-Right) & M4(Front-Left) must spin CW (Prop A). Swap wires to reverse.",
         "ACHIEVEMENT: All 4 motors spin in correct CW/CCW directions; Props A & B installed on matching corners."),
        (5, "Gamepad & 3-Layer Trim", "CALIBRATE", TEAL, TEAL_BG,
         "Pair Bluetooth gamepad. Solve the 'drifts sideways at 1 m/s on takeoff' problem caused by a ~2 deg board/battery mounting offset.",
         "Brainstorm an auto-trim strategy with AI: 1) 4-rotation ground calibration script, 2) D-pad 0.25 deg live trim, 3) in-flight stick learning.",
         "Why can't the accelerometer auto-trim tilt in flight? In hover, thrust points along the body axis, so a tilted drifting drone feels 0 lateral accel!",
         "Rest drone on 4 equal supports under the motor pods and average 0/90/180/270 deg readings so floor slope cancels out. Watch pitch sign (+pitch=forward).",
         "ACHIEVEMENT: Gamepad script reads sticks; 4-way ground calibration & D-pad trim give a level liftoff."),
        (6, "Sim First -> Wire Laser Sensor", "I2C1 + 3V3", AMBER, AMBER_BG,
         "Ask AI to build a 1-D vertical physics simulator before flying height-hold — prove why accelerometer-only hold fails, then wire VL53L1X laser.",
         "1) Have AI simulate accel-only height hold with 0.005 g bias. 2) Show AI photos of B-Cube V2.0 headers & CJMCU-531 to map pins and verify range.zrange.",
         "Trap 1: Sim proves accel-only hold climbs to 3-4 m in 3 s! Trap 2: Left header J4 has NO 3.3V pin! Trap 3: Yellow film or loose wire in 27 deg laser cone.",
         "Read PCB silkscreen: VCC->Right Header J3 Pin 1 (3V3); GND/SDA1/SCL1->Left Header J4 Pins 5, 6, 7. Power-cycle drone so deck.bcZRanger2=1 at boot.",
         "ACHIEVEMENT: deck.bcZRanger2 = 1 at boot; moving drone up/down by hand updates live laser height in m."),
        (7, "0.50 m DJI Hover & Log Audit", "FINAL MISSION", GREEN, GREEN_BG,
         "Co-design a DJI-style flight controller: auto-takeoff to 0.50 m hover, RT/LT (or Left Stick) climb/descend, release-to-hold, 0.25 m floor pause & auto-land.",
         "Fly, log 50 Hz CSV telemetry, and ask AI to diagnose real flight anomalies from your CSV logs (table edges, cable glitches, steering altitude drop).",
         "Why does steering drop altitude late in a flight? When loaded vbat < 3.38V, hover needs ~56k+ thrust -> roll/pitch clips boosted motors at 100% PWM!",
         "Add tilt-thrust boost (1/(cos R*cos P)), online adaptive hover-thrust learning, smooth 0.5 m/s terrain-following over tables, and <3.38V LOW-BAT alerts.",
         "FINAL ACHIEVEMENT: Hold A -> auto-takeoff to steady 0.50 m hover -> climb/descend -> 0.25 m floor pause -> X lands!"),
    ]

    margin = 18
    gap = 8
    w4 = (W - 2 * margin - 3 * gap) / 4.0
    h_row1 = 218
    y_row1 = H - 98 - h_row1
    for i in range(4):
        s = steps[i]
        draw_step_card(c, margin + i * (w4 + gap), y_row1, w4, h_row1, *s)

    w3 = (W - 2 * margin - 2 * gap) / 3.0
    h_row2 = 214
    y_row2 = 28
    for i in range(3):
        s = steps[4 + i]
        draw_step_card(c, margin + i * (w3 + gap), y_row2, w3, h_row2, *s)

    draw_footer(c, 1)


def draw_rot_arc(c, cx, cy, r, ccw, col):
    c.saveState()
    c.setStrokeColor(col)
    c.setFillColor(col)
    c.setLineWidth(1.3)
    c.arc(cx - r, cy - r, cx + r, cy + r, startAng=25, extent=130)
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

    arm = 52
    c.saveState()
    c.setStrokeColor(SLATE)
    c.setLineWidth(4)
    c.line(cx - arm, cy - arm, cx + arm, cy + arm)
    c.line(cx - arm, cy + arm, cx + arm, cy - arm)
    c.restoreState()

    rrect(c, cx - 26, cy - 30, 52, 60, r=4, fill=NAVY, stroke=SLATE, lw=1.2)
    text(c, cx, cy + 12, "ESP32-S2", font="Helvetica-Bold", size=6.5, color=colors.white, align="center")
    text(c, cx, cy + 2, "MPU6050", font="Helvetica", size=6, color=colors.HexColor("#93C5FD"), align="center")
    text(c, cx, cy - 8, "Battery Down", font="Helvetica-Oblique", size=5.5, color=colors.HexColor("#CBD5E1"), align="center")
    rrect(c, cx - 23, cy - 22, 6, 32, r=1, fill=AMBER, stroke=None)
    text(c, cx - 15, cy - 19, "J4", font="Helvetica-Bold", size=5.5, color=AMBER)
    rrect(c, cx + 17, cy - 22, 6, 32, r=1, fill=BLUE, stroke=None)
    text(c, cx + 11, cy - 19, "J3", font="Helvetica-Bold", size=5.5, color=colors.HexColor("#60A5FA"))
    rrect(c, cx + 23, cy + 8, 6, 14, r=1, fill=colors.HexColor("#94A3B8"), stroke=NAVY, lw=0.6)
    text(c, cx + 31, cy + 13, "USB-C", font="Helvetica-Bold", size=5.8, color=SLATE)

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

    rrect(c, x + 8, y + 6, w - 16, 28, r=4, fill=AMBER_BG, stroke=colors.HexColor("#FDE68A"), lw=0.7)
    text(c, x + 12, y + 23, "Golden Rule: Diagonal motors MUST spin the same way (M1+M3 = CCW/Prop B; M2+M4 = CW/Prop A).",
         font="Helvetica-Bold", size=6.3, color=AMBER)
    text(c, x + 12, y + 12, "If any motor spins the wrong way in your single-motor test script, swap its two soldered motor wires.",
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
    text(c, x + 10, y + h - 14, "3. TARGET FLIGHT COCKPIT SPEC  (Design This With Your AI Agent!)", font="Helvetica-Bold", size=8.2, color=BLUE)

    controls = [
        ("Hold A (1.0 s)", "ARM & AUTO-TAKEOFF", "Sets system.forceArm=1 & climbs smoothly to 0.50 m laser hover.", GREEN, GREEN_BG),
        ("RT or Left Stick UP", "CLIMB (+0.50 m/s)", "Climbs while held; release = locks & holds current laser height!", BLUE, BLUE_BG),
        ("LT or Left Stick DOWN", "DESCEND (-0.40 m/s)", "Descends while held; pauses automatically at 0.25 m safety floor.", BLUE, BLUE_BG),
        ("LB / RB Bumpers", "HEIGHT TRIM -/+10 cm", "Nudges target hover altitude down/up by 0.10 m (0.20..2.00 m).", TEAL, TEAL_BG),
        ("X Button (or Hold Down)", "AUTO-LAND & DISARM", "At 0.25 m floor pause (or any height), descends gently & disarms.", PURPLE, PURPLE_BG),
        ("Right Stick (X / Y)", "ROLL & PITCH STEERING", "Tilts drone left/right/forward/back with 1/(cos R*cos P) lift boost.", NAVY, CODE_BG),
        ("Left Stick (Left/Right)", "YAW ROTATION", "Rotates heading counter-clockwise / clockwise (up to 90 deg/s).", NAVY, CODE_BG),
        ("D-Pad (Up/Down/L/R)", "0.25 deg TILT TRIM", "Nudges roll/pitch trim toward push direction + auto stick learning.", AMBER, AMBER_BG),
        ("B Button (Any Time)", "EMERGENCY KILL", "Cuts all 4 motors to 0 immediately & sets system.forceArm=0.", RED, RED_BG),
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
    text(c, x + 10, y + h - 14, "4. HOW TO WORK WITH YOUR AI AGENT & DIAGNOSE FLIGHT PHYSICS", font="Helvetica-Bold", size=8.2, color=GREEN)

    items = [
        ("1. The AI Co-Engineering Playbook (How We Built This From Scratch):",
         "• Never ask AI for 'one giant drone program'. Break it into verifiable layers: UDP Probe -> cflib Log/Pulse Test -> Motor Spin Test -> Gamepad Reader -> 4-Way Level Calibrator -> 1-D Physics Sim -> Laser Hover Controller.\n"
         "• Always log 50 Hz CSV telemetry (t, phase, thrust, z_m, target_z, vz, roll, pitch, vbat). When a flight misbehaves, feed the CSV log to your AI and ask it to prove the cause from the numbers before changing code!"),
        ("2. Why Steering on a Low Battery Drops Altitude (Mixer Saturation):",
         "A 1S LiPo starts at ~4.18 V at rest and sags ~0.5 V under load. When loaded vbat > 3.40 V, hover needs ~49,000-52,000 thrust (~78% PWM). Once loaded vbat drops below 3.38 V, hover needs 56,000-59,500 (~92%+ PWM). Rolling/pitching adds +8,000 to two motors (which clip at the 65,535 ceiling) and subtracts -8,000 from the opposite two motors — reducing total lift! Have your AI add low-battery warnings (<3.92V rest / <3.38V load), tilt scaling, and <3.26V auto-land."),
        ("3. Tilt-Thrust Compensation & Smooth Terrain-Following Over Tables:",
         "• Tilting by (roll, pitch) tilts both the laser beam and thrust vector: multiply laser range by cos(R)*cos(P) and boost thrust by 1/(cos(R)*cos(P)).\n"
         "• When flying over a table edge (laser distance jumps >25 cm in 20 ms while accel vz is small), reset reference height z_ref to the new surface distance and slew smoothly at 0.50 m/s to copy the terrain without a throttle spike."),
    ]

    cy = y + h - 34
    for heading, body in items:
        text(c, x + 10, cy, heading, font="Helvetica-Bold", size=7.0, color=NAVY)
        cy -= 9.5
        for line in body.split("\n"):
            cy = paragraph(c, x + 14, cy, line, font="Helvetica", size=6.4, color=SLATE, max_w=w - 24, leading=8.1)
        cy -= 3.5


def build_page2(c):
    c.saveState()
    c.setFillColor(LIGHT_BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.restoreState()

    draw_header(c, 2, "PAGE 2: HARDWARE & AI CO-DESIGN SPECS  •  MOTOR & PROP MAP, J3/J4 LASER PINOUT, TARGET COCKPIT & FLIGHT PHYSICS")

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
    c.setTitle("AI-Native ESP32-S2 Drone Build & 0.50m Laser Hover Course Infographic")
    c.setAuthor("ESP32CrazyFlyDrone Course")
    build_page1(c)
    c.showPage()
    build_page2(c)
    c.showPage()
    c.save()
    print(f"Generated {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    main()
