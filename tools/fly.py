#!/usr/bin/env python3
"""Fly one ESP-Drone with a gamepad (DJI Mode-2 + RT/LT gas/brake laser altitude hold, or --manual-rt).

Default mode (when VL53L1X laser height sensor is present):
  Hold A 1 s (triggers/sticks released) = arm & auto-takeoff to 0.50 m hover.
  CLIMB / DESCEND (either one works, release = hold current height!):
    - RT ("gas" trigger)   or LEFT STICK UP   = climb (up to +0.50 m/s)
    - LT ("brake" trigger) or LEFT STICK DOWN = descend (up to -0.40 m/s)
    - LB / RB = fine height step -10 cm / +10 cm
  LANDING PROTECTION (like DJI):
    - Descending stops automatically at 0.25 m floor height and hovers there.
    - At 0.25 m, press X (land button) OR keep holding LT / Left Stick full down for 1.5 s to land & disarm.
    - Pressing X at any height starts automatic smooth landing.
  STEERING:
    - Right stick = forward/backward (pitch) and left/right (roll).
    - Left stick left/right = rotate (yaw).
    - D-pad = trim roll/pitch in 0.25 deg steps (saved to tools/fly_trim.json) + automatic stick learning.
  EMERGENCY KILL:
    - B = disarm + cut motors immediately at any time.

Pass --manual-rt for raw manual RT throttle (no height hold).
Usage: .venv/bin/python tools/fly.py [--seconds N] [--manual-rt] [--no-learn] [--sim]
"""
import argparse
import csv
import json
import math
import os
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402
from pygame._sdl2 import controller  # noqa: E402

URI = "udp://192.168.43.42:2390"
MAX_TILT_DEG = 15.0
MAX_YAW_RATE = 90.0       # deg/s
MAX_THRUST = 55000        # raw manual-rt max thrust; fw caps at 60000
DEADZONE = 0.08
ARM_HOLD_S = 1.0
RATE_HZ = 50
TRIM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fly_trim.json")
TRIM_STEP = 0.25
TRIM_MAX = 5.0
DEFAULT_TRIM = {"roll": 0.0, "pitch": 0.0}
LEARN_TAU = 20.0          # s; holding a 2 deg correction moves trim ~0.1 deg/s
LEARN_MAX_STICK = 0.4     # only small, steady corrections are learned; bigger = manoeuvre, ignored
LEARN_MIN_THRUST = 35000  # learn only when airborne

TAKEOFF_Z = 0.50          # m initial hover height after arming in DJI mode
FLOOR_Z = 0.25            # m descent floor pause height (stops descending and asks to land)
LAND_HOLD_S = 1.5         # s holding full down / LT at FLOOR_Z to confirm landing


def learn_trim(trim: dict, roll_cmd: float, pitch_cmd: float, dt: float) -> None:
    """Stick learning: move trim slowly toward the pilot's steady right-stick correction (deg, without trim)."""
    lim = LEARN_MAX_STICK * MAX_TILT_DEG
    if abs(roll_cmd) > lim or abs(pitch_cmd) > lim:
        return
    for k, cmd in (("roll", roll_cmd), ("pitch", pitch_cmd)):
        trim[k] = max(-TRIM_MAX, min(TRIM_MAX, trim[k] + cmd * dt / LEARN_TAU))


def shape(v: float) -> float:
    """Deadzone, then rescale so output starts at 0 at the deadzone edge."""
    if abs(v) < DEADZONE:
        return 0.0
    return (abs(v) - DEADZONE) / (1 - DEADZONE) * (1 if v > 0 else -1)


def setpoint(rx: float, ry: float, lx: float, rt: float):
    """Gamepad (-1..1 sticks, SDL y down = +, 0..1 trigger) -> (roll, pitch, yawrate, thrust) for cflib."""
    roll = shape(rx) * MAX_TILT_DEG
    pitch = -shape(ry) * MAX_TILT_DEG         # stick up = SDL negative -> +pitch = forward
    yawrate = shape(lx) * MAX_YAW_RATE
    thrust = int(shape(rt) * MAX_THRUST)
    return roll, pitch, yawrate, thrust


def climb_input(left_y: float, rt: float, lt: float) -> float:
    """Combine DJI Mode-2 left stick Y (SDL up = negative) and RT (gas=up) / LT (brake=down) into -1..1."""
    stick_up = -shape(left_y)
    trig_up = shape(rt) - shape(lt)
    return max(-1.0, min(1.0, stick_up + trig_up))


assert setpoint(0, 0, 0, 0) == (0.0, 0.0, 0.0, 0)
assert setpoint(0.05, -0.05, 0.05, 0.05) == (0.0, 0.0, 0.0, 0)
assert setpoint(1, -1, 1, 1) == (MAX_TILT_DEG, MAX_TILT_DEG, MAX_YAW_RATE, MAX_THRUST)
assert climb_input(0, 0, 0) == 0.0
assert climb_input(-1, 0, 0) == 1.0 and climb_input(0, 1, 0) == 1.0
assert climb_input(1, 0, 0) == -1.0 and climb_input(0, 0, 1) == -1.0


def _learn_check() -> None:
    t = {"roll": 0.0, "pitch": 0.0}
    for _ in range(1000):
        learn_trim(t, -2.0, 0.0, 0.02)
    assert abs(t["roll"] + 2.0) < 0.01 and t["pitch"] == 0.0, t
    learn_trim(t, 10.0, 0.0, 1.0)
    assert abs(t["roll"] + 2.0) < 0.01, t
    t = {"roll": 0.0, "pitch": 0.0}
    for _ in range(5000):
        learn_trim(t, 2.0 - t["roll"], 0.0, 0.02)
    assert abs(t["roll"] - 2.0) < 0.05, t


_learn_check()


class DjiAltitude:
    """Wraps hover.Flight for DJI-style climb/hold/descend with a 0.25 m landing-protection floor."""

    def __init__(self, g0: float, z0: float):
        import hover
        self.h = hover
        self.f = hover.Flight(g0=g0, target_z=TAKEOFF_Z, has_z=True, z0=z0)
        self.initial_climb = True
        self.at_floor = False
        self.down_hold_s = 0.0

    def step(self, dt: float, up_cmd: float, land_btn: bool = False) -> int:
        f, h = self.f, self.h
        if land_btn:
            self.at_floor = False
            f.land()
        if f.phase == "pilot" and f.has_z:
            # While still climbing to initial 0.50m takeoff height, ignore accidental LT/down unless > 1.2s in pilot
            if self.initial_climb and f.t_phase < 1.2 and up_cmd < 0:
                up_cmd = 0.0
            if abs(f.z_ref - TAKEOFF_Z) < 0.01:
                self.initial_climb = False
            if up_cmd > 0:
                self.initial_climb = False
                self.at_floor = False
                self.down_hold_s = 0.0
                f.target_z = h.clamp(f.target_z + up_cmd * h.Z_RATE * dt, FLOOR_Z, h.Z_MAX)
                return f.step(dt, 0.0)
            elif up_cmd < 0:
                self.initial_climb = False
                new_z = f.target_z + up_cmd * h.Z_RATE * dt
                if new_z <= FLOOR_Z:
                    f.target_z = FLOOR_Z
                    self.at_floor = True
                    if up_cmd < -0.75:
                        self.down_hold_s += dt
                        if self.down_hold_s >= LAND_HOLD_S:
                            self.at_floor = False
                            f.land()
                    else:
                        self.down_hold_s = 0.0
                else:
                    f.target_z = new_z
                    self.at_floor = False
                    self.down_hold_s = 0.0
                return f.step(dt, 0.0)
            else:
                self.down_hold_s = 0.0
                if not self.initial_climb:
                    f.target_z = h.clamp(f.z_ref, FLOOR_Z, h.Z_MAX)
                return f.step(dt, 0.0)
        return f.step(dt, up_cmd)


def sim_dji_check() -> None:
    """Verify DJI climb -> release holds height -> descend stops at 0.25 m floor -> X/hold lands."""
    dji = DjiAltitude(g0=1.0, z0=0.02)
    dt, z, vz, t_true = 0.02, 0.0, 0.0, 50000.0
    # 1. Takeoff to 0.50m (3s), 2. RT climb for 1.2s -> ~1.10m, 3. Release for 2.5s -> holds ~1.10m,
    # 4. LT descend for 2.5s -> stops at 0.25m floor, 5. Press X -> lands to 0.0m
    z_after_climb = z_after_hold = z_at_floor = None
    for k in range(int(16 / dt)):
        t = k * dt
        up = 0.8 if 3.0 <= t < 4.2 else (-0.8 if 6.7 <= t < 9.2 else 0.0)
        x_land = (t >= 10.5)
        th = dji.step(dt, up, land_btn=x_land)
        a = 9.81 * (th / t_true - 1.0)
        if z <= 0 and a <= 0:
            a, vz = 0.0, 0.0
        vz += a * dt
        z = max(0.0, z + vz * dt)
        dji.f.update(1.0 + a / 9.81, dt, z_m=0.02 + z)
        if abs(t - 5.0) < 0.01:
            z_after_climb = z
        if abs(t - 6.6) < 0.01:
            z_after_hold = z
        if abs(t - 10.0) < 0.01:
            z_at_floor = z
        if dji.f.phase == "done":
            break
    print(f"DJI sim: climb->{z_after_climb:.2f}m, hold->{z_after_hold:.2f}m, "
          f"floor pause->{z_at_floor:.2f}m (at_floor={dji.at_floor}), final phase={dji.f.phase} z={z:.2f}m")
    assert 0.85 < z_after_climb < 1.15 and abs(z_after_hold - z_after_climb) < 0.06
    assert 0.18 < z_at_floor < 0.30 and dji.f.phase == "done" and z < 0.06
    print("DJI sim OK")


def axis(pad, a) -> float:
    return pad.get_axis(a) / 32767


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0, help="auto-exit after N s (0 = until Ctrl-C)")
    ap.add_argument("--manual-rt", action="store_true", help="raw manual RT throttle (disable DJI laser height hold)")
    ap.add_argument("--no-learn", action="store_true", help="disable stick learning of trim")
    ap.add_argument("--sim", action="store_true", help="run offline DJI altitude-hold simulation check")
    args = ap.parse_args()
    if args.sim:
        sim_dji_check()
        return

    import cflib.crtp
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    import hover

    pygame.init()
    controller.init()
    if controller.get_count() == 0:
        raise SystemExit("no game controller found")
    pad = controller.Controller(0)
    print(f"controller: {pad.name}")

    cflib.crtp.init_drivers()
    state = {"acc_samples": [], "z_samples": [], "last_ts": None, "dji": None}

    def on_log(ts, d, _):
        roll, pitch = d["stabilizer.roll"], d["stabilizer.pitch"]
        state.update(d, roll=roll, pitch=pitch, vbat=d["pm.vbat"], az=d["acc.z"])
        dt = (ts - state["last_ts"]) / 1000 if state["last_ts"] is not None else 0.02
        state["last_ts"] = ts
        z_m = None
        tilt_cos = max(0.5, math.cos(math.radians(roll)) * math.cos(math.radians(pitch)))
        if "range.zrange" in d and 0 <= d["range.zrange"] < 5000:
            z_m = (d["range.zrange"] / 1000.0) * tilt_cos
            state["z_m"] = z_m
        if state["dji"] is None:
            state["acc_samples"].append(d["acc.z"])
            if z_m is not None:
                state["z_samples"].append(z_m)
        else:
            state["dji"].f.update(d["acc.z"], hover.clamp(dt, 0.001, 0.1), z_m=z_m, tilt_cos=tilt_cos)

    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf:
        cf = scf.cf
        if str(cf.param.get_value("stabilizer.stop")) == "1":
            raise SystemExit("emergency stop latched (stabilizer.stop=1): power-cycle the drone")
        has_zr = str(cf.param.get_value("deck.bcZRanger2")) == "1"
        log = LogConfig(name="fly", period_in_ms=20)
        for v in ("acc.z", "pm.vbat", "stabilizer.roll", "stabilizer.pitch"):
            log.add_variable(v, "float")
        if has_zr and cf.log.toc.get_element_by_complete_name("range.zrange"):
            log.add_variable("range.zrange")
        cf.log.add_config(log)
        log.data_received_cb.add_callback(on_log)
        log.start()
        time.sleep(1.0)

        use_dji = has_zr and not args.manual_rt and len(state["z_samples"]) >= 5
        g0 = sum(state["acc_samples"]) / len(state["acc_samples"]) if state["acc_samples"] else 1.0
        z0 = sum(state["z_samples"]) / len(state["z_samples"]) if use_dji else 0.0
        if not has_zr:
            print("WARNING: VL53L1X laser height sensor NOT detected (deck.bcZRanger2=0) - using manual RT throttle")
        elif use_dji:
            print(f"DJI LASER ALTITUDE HOLD active (z0={z0:.3f}m): RT/LeftStick-UP = climb, LT/LeftStick-DOWN = descend, "
                  f"release = hold height, stops at {FLOOR_Z:.2f}m floor (press X or hold down 1.5s to land)")
        else:
            print("Manual RT throttle mode active (--manual-rt)")

        trim = dict(DEFAULT_TRIM)
        if os.path.exists(TRIM_FILE):
            trim.update(json.load(open(TRIM_FILE)))
        print(f"trim roll={trim['roll']:+.2f} pitch={trim['pitch']:+.2f} (D-pad adjusts)")
        dpad = {pygame.CONTROLLER_BUTTON_DPAD_LEFT: ("roll", -TRIM_STEP),
                pygame.CONTROLLER_BUTTON_DPAD_RIGHT: ("roll", TRIM_STEP),
                pygame.CONTROLLER_BUTTON_DPAD_UP: ("pitch", TRIM_STEP),
                pygame.CONTROLLER_BUTTON_DPAD_DOWN: ("pitch", -TRIM_STEP)}
        shoulders = {pygame.CONTROLLER_BUTTON_LEFTSHOULDER: -1, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: 1}
        held, sh_held = set(), set()
        armed, a_since, last_print, last = False, None, 0.0, time.time()
        floor_warned = False
        end = time.time() + args.seconds if args.seconds else float("inf")

        def disarm(reason: str) -> None:
            nonlocal armed, floor_warned
            cf.commander.send_stop_setpoint()
            cf.param.set_value("system.forceArm", "0")
            if armed:
                print(f"\nDISARMED ({reason})")
            armed, floor_warned = False, False
            state["dji"] = None

        os.makedirs("logs", exist_ok=True)
        path = time.strftime("logs/fly-%Y%m%d-%H%M%S.csv")
        fh = open(path, "w", newline="")
        out = csv.writer(fh)
        out.writerow(["t", "armed", "phase", "thrust", "up_cmd", "z_m", "target_z", "vz_est", "roll", "pitch", "vbat", "trim_roll", "trim_pitch", "t_hover"])
        t0 = time.time()
        print(f"ready: hold A 1 s (triggers/sticks released) to arm" + (" & takeoff to 0.50m" if use_dji else "") + f", X = land, B = KILL  (log: {path})")
        try:
            while time.time() < end:
                now = time.time()
                dt, last = now - last, now
                pygame.event.pump()
                if not pad.attached():
                    disarm("controller lost")
                    break
                rt = axis(pad, pygame.CONTROLLER_AXIS_TRIGGERRIGHT)
                lt = axis(pad, pygame.CONTROLLER_AXIS_TRIGGERLEFT)
                ly = axis(pad, pygame.CONTROLLER_AXIS_LEFTY)
                up_cmd = climb_input(ly, rt, lt)

                if pad.get_button(pygame.CONTROLLER_BUTTON_B):
                    disarm("B")
                    a_since = None
                elif armed and (abs(state.get("roll", 0)) > hover.MAX_TILT or abs(state.get("pitch", 0)) > hover.MAX_TILT):
                    disarm(f"tilt {state.get('roll', 0):.0f}/{state.get('pitch', 0):.0f}")
                elif not armed and pad.get_button(pygame.CONTROLLER_BUTTON_A) and shape(rt) == 0 and abs(up_cmd) == 0:
                    a_since = a_since or now
                    if now - a_since >= ARM_HOLD_S:
                        if use_dji:
                            state["dji"] = DjiAltitude(g0=g0, z0=state.get("z_m", z0))
                        cf.param.set_value("system.forceArm", "1")
                        for _ in range(10):
                            cf.commander.send_setpoint(0, 0, 0, 0)
                            time.sleep(0.01)
                        armed = True
                        last = time.time()  # reset dt after 100ms unlock loop so first ramp step does not jump!
                        print("\nARMED" + (f" -> climbing to {TAKEOFF_Z:.2f}m hover" if use_dji else ""))
                else:
                    a_since = None

                for btn, (k, step) in dpad.items():
                    if pad.get_button(btn) and btn not in held:
                        trim[k] = max(-TRIM_MAX, min(TRIM_MAX, trim[k] + step))
                        print(f"\ntrim roll={trim['roll']:+.2f} pitch={trim['pitch']:+.2f}")
                held = {b for b in dpad if pad.get_button(b)}

                sp = setpoint(axis(pad, pygame.CONTROLLER_AXIS_RIGHTX), axis(pad, pygame.CONTROLLER_AXIS_RIGHTY),
                              axis(pad, pygame.CONTROLLER_AXIS_LEFTX), rt)

                if armed and use_dji and state["dji"] is not None:
                    dji = state["dji"]
                    for btn, sign in shoulders.items():
                        if pad.get_button(btn) and btn not in sh_held:
                            dji.f.nudge(sign)
                            print(f"\ntarget height = {dji.f.target_z:.2f} m (current z = {dji.f.z:.2f} m)")
                    sh_held = {b for b in shoulders if pad.get_button(b)}
                    x_btn = pad.get_button(pygame.CONTROLLER_BUTTON_X)
                    thrust = dji.step(dt, up_cmd, land_btn=x_btn)
                    if dji.at_floor and not floor_warned:
                        print(f"\n*** AT {FLOOR_Z:.2f}m FLOOR: press X to LAND (or hold LT / Left Stick full down 1.5s) ***")
                        floor_warned = True
                    elif not dji.at_floor:
                        floor_warned = False
                    if dji.f.phase in ("done", "abort"):
                        why = f"landed (z={dji.f.z:.2f}m)" if dji.f.phase == "done" else f"takeoff abort (cmd={dji.f.cmd:.0f}, z={dji.f.z:.2f}m, vbat={state.get('pm.vbat',0):.2f}V)"
                        disarm(why)
                        thrust = 0
                else:
                    thrust = sp[3] if armed else 0

                if armed and thrust >= LEARN_MIN_THRUST and not args.no_learn:
                    learn_trim(trim, sp[0], sp[1], dt)
                cmd = (sp[0] + trim["roll"], sp[1] + trim["pitch"], sp[2], thrust)
                cf.commander.send_setpoint(*cmd) if armed else cf.commander.send_setpoint(0, 0, 0, 0)
                f_obj = state["dji"].f if (use_dji and state["dji"] is not None) else None
                out.writerow([f"{now - t0:.3f}", int(armed), f_obj.phase if f_obj else "manual", thrust,
                              f"{up_cmd:.2f}", f"{state.get('z_m', 0):.3f}", f"{f_obj.target_z:.2f}" if f_obj else "",
                              f"{f_obj.vz:.3f}" if f_obj else "", f"{state.get('roll', 0):.1f}",
                              f"{state.get('pitch', 0):.1f}", f"{state.get('pm.vbat', 0):.2f}",
                              f"{trim['roll']:.2f}", f"{trim['pitch']:.2f}", f"{f_obj.t_hover or 0:.0f}" if f_obj else ""])

                if now - last_print > 0.3:
                    last_print = now
                    if use_dji and state["dji"] is not None:
                        dji = state["dji"]
                        fl = " [FLOOR-PAUSE: press X to land]" if dji.at_floor else ""
                        z_str = f" z={dji.f.z:.2f}/{dji.f.target_z:.2f}m({dji.f.phase}){fl}"
                    elif has_zr:
                        z_str = f" z={state.get('z_m', 0):.2f}m"
                    else:
                        z_str = " z=NO_LASER"
                    print(f"\r{'ARMED ' if armed else 'safe  '} trim=({trim['roll']:+.2f},{trim['pitch']:+.2f}) "
                          f"roll={cmd[0]:+5.1f} pitch={cmd[1]:+5.1f} "
                          f"yaw={cmd[2]:+6.1f} thrust={thrust:5d} | "
                          f"vbat={state.get('pm.vbat', 0):.2f}V att=({state.get('stabilizer.roll', 0):+.0f},"
                          f"{state.get('stabilizer.pitch', 0):+.0f}){z_str}   ", end="", flush=True)
                time.sleep(1 / RATE_HZ)
        except KeyboardInterrupt:
            pass
        finally:
            disarm("exit")
            log.stop()
            fh.close()
            json.dump(trim, open(TRIM_FILE, "w"))
            print(f"\ntrim saved: {trim}  log: {path}")
    print("\nbye")


if __name__ == "__main__":
    main()
