#!/usr/bin/env python3
"""Fly one ESP-Drone with a gamepad (tested with Google Stadia controller over Bluetooth).

Controls: RT = thrust (release = 0), right stick = roll/pitch, left stick X = yaw.
          Hold A 1 s with RT released = arm.  B = disarm + stop motors (any time).
          D-pad = trim roll (left/right) and pitch (up/down) in 0.5 deg steps; saved to tools/fly_trim.json.
Failsafes: controller lost -> stop + disarm; Ctrl-C -> stop + disarm.
Firmware: no setpoint for 0.5 s -> levels; 2 s -> motors off.
Usage: .venv/bin/python tools/fly.py [--seconds N]
"""
import argparse
import json
import os
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402
from pygame._sdl2 import controller  # noqa: E402

URI = "udp://192.168.43.42:2390"
MAX_TILT_DEG = 15.0
MAX_YAW_RATE = 90.0       # deg/s
MAX_THRUST = 55000        # hover needs ~42000 (firmware thrustBase) and more on a sagging battery; fw caps at 60000
DEADZONE = 0.08
ARM_HOLD_S = 1.0
RATE_HZ = 50
TRIM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fly_trim.json")
TRIM_STEP = 0.5
TRIM_MAX = 5.0
# Bench: flat drone reads roll +1.94. Flight 2026-11-17 with +2.0 drifted right ~1 m/s -> sign is opposite.
DEFAULT_TRIM = {"roll": -2.0, "pitch": 0.0}


def shape(v: float) -> float:
    """Deadzone, then rescale so output starts at 0 at the deadzone edge."""
    if abs(v) < DEADZONE:
        return 0.0
    return (abs(v) - DEADZONE) / (1 - DEADZONE) * (1 if v > 0 else -1)


def setpoint(rx: float, ry: float, lx: float, rt: float):
    """Gamepad (-1..1 sticks, SDL y down = +, 0..1 trigger) -> (roll, pitch, yawrate, thrust) for cflib.

    Firmware conventions (crtp_commander_rpyt.c): negative pitch = forward, positive roll = right,
    positive yaw = clockwise (firmware negates it). Bench-verify motor response before props.
    """
    roll = shape(rx) * MAX_TILT_DEG
    pitch = shape(ry) * MAX_TILT_DEG          # stick up = SDL negative = forward
    yawrate = shape(lx) * MAX_YAW_RATE
    thrust = int(shape(rt) * MAX_THRUST)
    return roll, pitch, yawrate, thrust


assert setpoint(0, 0, 0, 0) == (0.0, 0.0, 0.0, 0)
assert setpoint(0.05, -0.05, 0.05, 0.05) == (0.0, 0.0, 0.0, 0)  # inside deadzone
assert setpoint(1, -1, 1, 1) == (MAX_TILT_DEG, -MAX_TILT_DEG, MAX_YAW_RATE, MAX_THRUST)


def axis(pad, a) -> float:
    return pad.get_axis(a) / 32767


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0, help="auto-exit after N s (0 = until Ctrl-C)")
    args = ap.parse_args()

    import cflib.crtp
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

    pygame.init()
    controller.init()
    if controller.get_count() == 0:
        raise SystemExit("no game controller found")
    pad = controller.Controller(0)
    print(f"controller: {pad.name}")

    cflib.crtp.init_drivers()
    state = {}
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf:
        cf = scf.cf
        if str(cf.param.get_value("stabilizer.stop")) == "1":
            raise SystemExit("emergency stop latched (stabilizer.stop=1): power-cycle the drone")
        log = LogConfig(name="fly", period_in_ms=200)
        for v in ("pm.vbat", "stabilizer.roll", "stabilizer.pitch"):
            log.add_variable(v)
        cf.log.add_config(log)
        log.data_received_cb.add_callback(lambda ts, d, _: state.update(d))
        log.start()

        trim = dict(DEFAULT_TRIM)
        if os.path.exists(TRIM_FILE):
            trim.update(json.load(open(TRIM_FILE)))
        print(f"trim roll={trim['roll']:+.1f} pitch={trim['pitch']:+.1f} (D-pad adjusts)")
        dpad = {pygame.CONTROLLER_BUTTON_DPAD_LEFT: ("roll", -TRIM_STEP),
                pygame.CONTROLLER_BUTTON_DPAD_RIGHT: ("roll", TRIM_STEP),
                pygame.CONTROLLER_BUTTON_DPAD_UP: ("pitch", -TRIM_STEP),
                pygame.CONTROLLER_BUTTON_DPAD_DOWN: ("pitch", TRIM_STEP)}
        held = set()
        armed, a_since, last_print = False, None, 0.0
        end = time.time() + args.seconds if args.seconds else float("inf")

        def disarm(reason: str) -> None:
            nonlocal armed
            cf.commander.send_stop_setpoint()
            cf.param.set_value("system.forceArm", "0")
            if armed:
                print(f"\nDISARMED ({reason})")
            armed = False

        print("ready: hold A 1 s (RT released) to arm, B = stop")
        try:
            while time.time() < end:
                pygame.event.pump()
                if not pad.attached():
                    disarm("controller lost")
                    break
                rt = axis(pad, pygame.CONTROLLER_AXIS_TRIGGERRIGHT)
                if pad.get_button(pygame.CONTROLLER_BUTTON_B):
                    disarm("B")
                    a_since = None
                elif not armed and pad.get_button(pygame.CONTROLLER_BUTTON_A) and shape(rt) == 0:
                    a_since = a_since or time.time()
                    if time.time() - a_since >= ARM_HOLD_S:
                        cf.param.set_value("system.forceArm", "1")
                        armed = True
                        print("\nARMED")
                else:
                    a_since = None

                for btn, (k, step) in dpad.items():
                    if pad.get_button(btn) and btn not in held:
                        trim[k] = max(-TRIM_MAX, min(TRIM_MAX, trim[k] + step))
                        print(f"\ntrim roll={trim['roll']:+.1f} pitch={trim['pitch']:+.1f}")
                held = {b for b in dpad if pad.get_button(b)}

                sp = setpoint(axis(pad, pygame.CONTROLLER_AXIS_RIGHTX), axis(pad, pygame.CONTROLLER_AXIS_RIGHTY),
                              axis(pad, pygame.CONTROLLER_AXIS_LEFTX), rt)
                sp = (sp[0] + trim["roll"], sp[1] + trim["pitch"], sp[2], sp[3])
                cf.commander.send_setpoint(*sp) if armed else cf.commander.send_setpoint(0, 0, 0, 0)

                if time.time() - last_print > 0.5:
                    last_print = time.time()
                    print(f"\r{'ARMED ' if armed else 'safe  '} roll={sp[0]:+5.1f} pitch={sp[1]:+5.1f} "
                          f"yaw={sp[2]:+6.1f} thrust={sp[3] if armed else 0:5d} | "
                          f"vbat={state.get('pm.vbat', 0):.2f}V att=({state.get('stabilizer.roll', 0):+.0f},"
                          f"{state.get('stabilizer.pitch', 0):+.0f})   ", end="", flush=True)
                time.sleep(1 / RATE_HZ)
        except KeyboardInterrupt:
            pass
        finally:
            disarm("exit")
            log.stop()
            json.dump(trim, open(TRIM_FILE, "w"))
            print(f"\ntrim saved: {trim}")
    print("\nbye")


if __name__ == "__main__":
    main()
