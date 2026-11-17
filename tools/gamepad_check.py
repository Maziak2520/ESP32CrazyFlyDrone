#!/usr/bin/env python3
"""Live gamepad check: prints named stick/trigger values and button presses. Never talks to the drone.

Usage: .venv/bin/python tools/gamepad_check.py [seconds]   (default 30; Ctrl-C to stop)
"""
import os
import sys
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402
from pygame._sdl2 import controller  # noqa: E402

AXES = {"leftx": pygame.CONTROLLER_AXIS_LEFTX, "lefty": pygame.CONTROLLER_AXIS_LEFTY,
        "rightx": pygame.CONTROLLER_AXIS_RIGHTX, "righty": pygame.CONTROLLER_AXIS_RIGHTY,
        "LT": pygame.CONTROLLER_AXIS_TRIGGERLEFT, "RT": pygame.CONTROLLER_AXIS_TRIGGERRIGHT}
BUTTONS = {n[len("CONTROLLER_BUTTON_"):].lower(): getattr(pygame, n)
           for n in dir(pygame) if n.startswith("CONTROLLER_BUTTON_") and n != "CONTROLLER_BUTTON_MAX"}

pygame.init()
controller.init()
if controller.get_count() == 0 or not controller.is_controller(0):
    sys.exit("no game controller found (pair it: Stadia + Y for 2 s, then System Settings > Bluetooth)")
pad = controller.Controller(0)
print(f"{pad.name}: move sticks, squeeze triggers, press buttons")

end = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 30)
last = None
try:
    while time.time() < end:
        pygame.event.pump()
        axes = {k: round(pad.get_axis(v) / 32767, 2) for k, v in AXES.items()}  # -1..1, triggers 0..1
        pressed = [k for k, v in BUTTONS.items() if pad.get_button(v)]
        line = "  ".join(f"{k}={v:+.2f}" for k, v in axes.items()) + "  buttons=" + ",".join(pressed)
        if line != last:
            print(line)
            last = line
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
