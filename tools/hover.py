#!/usr/bin/env python3
"""Assisted flight with automatic laser height hold (VL53L1X) or accelerometer fallback.

When VL53L1X is detected (deck.bcZRanger2=1), holds target height (default 1.0 m, --height) in closed loop
using range.zrange (mm, tilt-compensated) + accelerometer vertical speed damping.
  LB / RB = target height -0.10 m / +0.10 m per press (0.20..2.00 m). (In no-sensor fallback: +-1 % hover thrust.)
  LEFT STICK UP/DOWN = temporary climb/sink speed override (+-0.5 m/s) and shifts target height while pushed.
  Right stick = roll/pitch, left stick X = yaw, trim from tools/fly_trim.json.
  Stick learning: steady small right-stick corrections slowly move into the trim (--no-learn).
  D-pad = roll/pitch trim (0.25 deg steps).
  A = automatic landing (ramps target height down at 0.35 m/s until z < 0.08 m or touchdown).
  B = kill motors now (any time).
  Controller lost -> landing. Tilt > 35 deg -> kill. Ctrl-C -> kill. 60 s -> landing.
Usage: .venv/bin/python tools/hover.py [--height 1.0] [--no-laser-ok]
       .venv/bin/python tools/hover.py --sim    (offline checks, no drone)
       .venv/bin/python tools/hover.py --dry    (real drone, never armed, thrust 0)
Flight log CSV: logs/hover-*.csv
"""
import argparse
import csv
import json
import math
import os
import random
import time

G = 9.81
T_START = 43000           # ramp start; motor vibration on ground below 50k can fake vz>0.15 if we trigger earlier
T_LIFTOFF_MIN = 48500     # minimum thrust before accel-only lift-off can trigger (prevents vibration false-trigger at 47k)
RAMP = 10000              # thrust units per second during lift-off search (43k -> 51k in 0.8 s)
T_LIFTOFF_MAX = 59500     # no lift-off by here -> abort (battery/props)
THRUST_LIMIT = 59500      # firmware caps at 60000
LIFTOFF_VZ = 0.15         # m/s estimated climb that counts as lift-off
LIFTOFF_Z = 0.05          # m laser height rise above ground that also counts as lift-off
LIFTOFF_LAG = 0.27        # s; fallback detection delay subtracted from ramp (10000*0.27 = 2700)
LIFTOFF_LAG_Z = 0.37      # s; laser lift-off detection delay (10000*0.37 = 3700; laser closes loop after)
CLIMB_S, CLIMB_GAIN = 0.80, 1.07   # fallback-only climb out of ground effect after lift-off
TAU = 1.0                 # s; leaky speed estimate = damping only, cannot run away on bias
KD = 0.30                 # damping, fraction of hover thrust per m/s (no-sensor fallback)
KP_Z, KD_Z = 0.36, 0.42   # laser height P and D gains (fraction of hover thrust per m and per m/s)
KI_Z, IZ_MAX = 0.12, 0.18 # height I gain (fraction of hover thrust per m*s) and cap (absorbs battery sag)
Z_DEFAULT = 1.0           # m default target hover height
Z_STEP = 0.10             # m per LB/RB press
Z_MIN, Z_MAX = 0.20, 2.00 # m allowed target height range
Z_RATE = 0.50             # m/s max target height slew rate (smooth climb & left-stick rate)
LAND_RATE = 0.35          # m/s target descent rate during landing with laser
LAND_DONE_Z = 0.05        # m laser height above ground considered landed
PILOT_RANGE = 0.14        # fallback: full left stick = +-14 % of hover thrust
BAND = (0.72, 1.22)       # thrust / hover thrust clamp
DESC_GAIN, DESC_SLOPE, DESC_MIN = 0.92, 0.05, 0.82
DESC_BRAKE_V = 0.5
NUDGE = 0.01              # fallback LB/RB step, fraction of hover thrust
NUDGE_RANGE = (0.75, 1.20)
LEARN_S = 6.0
DESC_MAX_S = 5.0
SETTLE_S = 2.0
TOUCH_G = 0.4
MAX_TILT = 35.0
MAX_FLIGHT_S = 60.0


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class Flight:
    """Phases: ramp -> (climb) -> pilot -> descend -> (settle) -> done, or abort."""

    def __init__(self, g0: float, target_z: float = Z_DEFAULT, has_z: bool = False, z0: float = 0.0):
        self.g0, self.vz, self.az_f = g0, 0.0, g0
        self.has_z, self.z0, self.z, self.vz_z = has_z, z0, z0, 0.0
        self.target_z = clamp(target_z, Z_MIN, Z_MAX)
        self.z_ref, self.iz, self.z_age = z0, 0.0, 0.0
        self.t_hover = self.t_hover0 = self.t_lift = None
        self.phase, self.t_phase, self.cmd = "ramp", 0.0, float(T_START)

    def update(self, az: float, dt: float, z_m: float = None) -> None:
        """az: body z acceleration in g. z_m: tilt-compensated laser height in metres (if available)."""
        self.vz += (az - self.g0) * G * dt - self.vz * dt / TAU
        self.az_f += 0.3 * (az - self.az_f)
        if z_m is not None and 0.0 <= z_m < 4.0:
            if self.has_z and dt > 0:
                vz_laser = (z_m - self.z) / dt
                if abs(vz_laser) < 5.0:
                    self.vz_z += 0.25 * (vz_laser - self.vz_z)
            self.z, self.z_age = z_m, 0.0
        else:
            self.z_age += dt

    def enter(self, phase: str) -> None:
        self.phase, self.t_phase = phase, 0.0

    def land(self) -> None:
        if self.phase == "ramp":
            self.enter("done")
        elif self.phase in ("climb", "pilot"):
            self.enter("descend")

    def nudge(self, sign: int) -> None:
        """LB/RB: shift target height by +-0.10 m when laser active, else hover thrust by +-1 %."""
        if self.has_z:
            self.target_z = round(clamp(self.target_z + sign * Z_STEP, Z_MIN, Z_MAX), 2)
            return
        if self.t_hover is None:
            return
        new0 = clamp(self.t_hover0 * (1 + sign * NUDGE), NUDGE_RANGE[0] * self.t_lift, NUDGE_RANGE[1] * self.t_lift)
        self.t_hover *= new0 / self.t_hover0
        self.t_hover0 = new0

    def _thrust(self, gain: float, vz_free: float = 0.0) -> int:
        v = min(0.0, self.vz + vz_free) if vz_free else self.vz
        t = self.t_hover * gain - KD * self.t_hover * v
        return int(clamp(t, BAND[0] * self.t_hover, min(BAND[1] * self.t_hover, THRUST_LIMIT)))

    def _thrust_z(self, dt: float, vz_cmd: float = 0.0) -> int:
        err = self.z_ref - self.z
        self.iz = clamp(self.iz + KI_Z * err * dt, -IZ_MAX, IZ_MAX)
        gain = 1.0 + KP_Z * err + self.iz + KD_Z * (vz_cmd - self.vz_z)
        return int(clamp(self.t_hover * gain, BAND[0] * self.t_hover, min(BAND[1] * self.t_hover, THRUST_LIMIT)))

    def step(self, dt: float, stick_up: float = 0.0) -> int:
        """stick_up: -1..1, already dead-zoned. Returns thrust to send."""
        self.t_phase += dt
        z_ok = self.has_z and self.z_age < 0.5
        if self.phase == "ramp":
            self.cmd += RAMP * dt
            lifted = (z_ok and (self.z - self.z0) > LIFTOFF_Z) or (self.cmd >= T_LIFTOFF_MIN and self.vz > LIFTOFF_VZ)
            if lifted:
                lag = LIFTOFF_LAG_Z if z_ok else LIFTOFF_LAG
                self.t_hover = self.t_hover0 = self.t_lift = self.cmd - RAMP * lag
                self.z_ref = self.z
                self.enter("pilot" if z_ok else "climb")
            elif self.cmd > T_LIFTOFF_MAX:
                self.enter("abort")
                return 0
            else:
                return int(self.cmd)
        touched = self.az_f - self.g0 > TOUCH_G
        if self.phase == "climb":
            if self.t_phase >= CLIMB_S:
                self.enter("pilot")
            return self._thrust(CLIMB_GAIN)
        if self.phase == "pilot":
            if z_ok:
                if abs(stick_up) > 0:
                    self.target_z = clamp(self.target_z + stick_up * Z_RATE * dt, Z_MIN, Z_MAX)
                diff = self.target_z - self.z_ref
                step_z = clamp(diff, -Z_RATE * dt, Z_RATE * dt)
                self.z_ref += step_z
                return self._thrust_z(dt, vz_cmd=step_z / dt if dt > 0 else 0.0)
            self.t_hover = clamp(self.t_hover * (1 + PILOT_RANGE * stick_up * dt / LEARN_S),
                                 self.t_hover0 * (1 - PILOT_RANGE), self.t_hover0 * (1 + PILOT_RANGE))
            return self._thrust(1 + PILOT_RANGE * stick_up)
        if self.phase == "descend":
            if stick_up > 0.8:
                self.z_ref = self.z
                self.enter("pilot")
                return self._thrust_z(dt) if z_ok else self._thrust(1.0)
            if self.t_phase > 0.3 and (touched or (z_ok and self.z <= self.z0 + LAND_DONE_Z and abs(self.vz_z) < 0.25)):
                self.enter("done")
                return 0
            if z_ok and self.t_phase < DESC_MAX_S:
                self.z_ref = max(self.z0, self.z_ref - LAND_RATE * dt)
                return self._thrust_z(dt, vz_cmd=-LAND_RATE)
            if self.t_phase >= DESC_MAX_S:
                self.enter("settle")
            else:
                gain = max(DESC_MIN, DESC_GAIN - DESC_SLOPE * self.t_phase)
                return self._thrust(gain + PILOT_RANGE * stick_up, vz_free=DESC_BRAKE_V)
        if self.phase == "settle":
            if touched or (z_ok and self.z <= self.z0 + LAND_DONE_Z) or self.t_phase >= SETTLE_S:
                self.enter("done")
                return 0
            return int(self.t_hover * 0.85 * (1 - self.t_phase / SETTLE_S))
        return 0


def sim(seed: int, bias: float, pilot: bool, pilot_s: float = 6.0, t_true: float = 44000.0,
        has_z: bool = False, target_z: float = 1.0) -> dict:
    """Crude 1-D model: unknown hover thrust, 40 ms latency, noise, accelerometer bias (g), battery sag."""
    random.seed(seed)
    dt, z, vz, latency, seen = 0.02, 0.0, 0.0, [0, 0], [(0.0, 0.0)] * 15
    f = Flight(g0=1.0, target_z=target_z, has_z=has_z, z0=0.02)
    max_z, touch_v, hold_err = 0.0, 0.0, []
    for _ in range(int(40 / dt)):
        stick = 0.0
        z_seen, vz_seen = seen[0]
        if f.phase in ("pilot", "descend") and pilot and not has_z:
            target = 0.4 if f.phase == "pilot" and f.t_phase < pilot_s - 2 else 0.15
            if f.phase == "descend":
                stick = clamp(2.0 * (-0.4 - vz_seen), -1, 0.7)
            else:
                stick = clamp(1.5 * (target - z_seen) - 1.0 * vz_seen, -1, 1)
        if f.phase == "pilot" and f.t_phase >= (pilot_s if (pilot or has_z) else 3.0):
            f.land()
        latency.append(f.step(dt, stick))
        seen = seen[1:] + [(z, vz)]
        applied = latency.pop(0)
        t_true *= 1.00002
        a = G * (applied / t_true - 1)
        if z <= 0 and a <= 0:
            a, vz = 0.0, 0.0
        vz += a * dt
        z += vz * dt
        spike = 0.0
        if z < 0:
            touch_v = max(touch_v, -vz)
            spike, z, vz = -vz / dt / G, 0.0, 0.0
        z_meas = max(0.01, 0.02 + z + random.gauss(0, 0.005)) if has_z else None
        f.update(1 + a / G + spike + bias + random.gauss(0, 0.02), dt, z_m=z_meas)
        max_z = max(max_z, z)
        if f.phase == "pilot" and f.t_phase > 3.5:
            hold_err.append(abs(z + 0.02 - target_z))
        if f.phase in ("done", "abort"):
            break
    return {"phase": f.phase, "t_hover": f.t_hover, "max_z": max_z, "touch_v": touch_v, "final_z": z,
            "hold_err": max(hold_err) if hold_err else 0.0}


def sim_check() -> None:
    for bias in (-0.005, 0.0, 0.005):
        for t_true in (48500.0, 50500.0, 52500.0):
            lz = [sim(seed, bias, pilot=False, pilot_s=8.0, t_true=t_true, has_z=True, target_z=1.0) for seed in range(1, 5)]
            rs = [sim(seed, bias, pilot=True, t_true=t_true, has_z=False) for seed in range(1, 5)]
            print(f"bias {bias:+.3f} g, hover {t_true:.0f} | LASER 1.0m: max {max(r['max_z'] for r in lz):.2f} m, "
                  f"err <= {max(r['hold_err'] for r in lz):.2f} m, touch <= {max(r['touch_v'] for r in lz):.2f} m/s | "
                  f"no-sensor piloted: max {max(r['max_z'] for r in rs):.2f} m")
            for r in lz:
                assert r["phase"] == "done" and r["final_z"] < 0.08, r
                assert 0.85 < r["max_z"] < 1.15 and r["hold_err"] < 0.12 and r["touch_v"] < 0.8, r
            for r in rs:
                assert r["phase"] == "done" and r["final_z"] < 0.05 and r["max_z"] < 1.0 and r["touch_v"] < 1.5, r
    f = Flight(1.0, target_z=1.0, has_z=True)
    f.nudge(-1)
    assert f.target_z == 0.90
    f.nudge(1)
    assert f.target_z == 1.00
    print("sim OK")


def run(dry: bool, no_learn: bool, target_z: float, no_laser_ok: bool = False) -> None:
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    import pygame
    from pygame._sdl2 import controller
    import cflib.crtp
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    import fly as manual  # tools/fly.py: stick shaping, trim, URI

    pygame.init()
    controller.init()
    if controller.get_count() == 0:
        raise SystemExit("no game controller: B (kill) is required")
    pad = controller.Controller(0)
    trim = dict(manual.DEFAULT_TRIM)
    if os.path.exists(manual.TRIM_FILE):
        trim.update(json.load(open(manual.TRIM_FILE)))

    def stick(a):
        return pad.get_axis(a) / 32767

    cflib.crtp.init_drivers()
    s = {"samples": [], "z_samples": [], "last_ts": None, "flight": None, "z_m": None}

    def on_log(ts, d, _):
        roll, pitch = d["stabilizer.roll"], d["stabilizer.pitch"]
        s.update(roll=roll, pitch=pitch, vbat=d["pm.vbat"], az=d["acc.z"])
        dt = (ts - s["last_ts"]) / 1000 if s["last_ts"] is not None else 0.02
        s["last_ts"] = ts
        z_m = None
        if "range.zrange" in d and 0 <= d["range.zrange"] < 5000:
            tilt_cos = max(0.5, math.cos(math.radians(roll)) * math.cos(math.radians(pitch)))
            z_m = (d["range.zrange"] / 1000.0) * tilt_cos
            s["z_m"] = z_m
        if s["flight"] is None:
            s["samples"].append(d["acc.z"])
            if z_m is not None:
                s["z_samples"].append(z_m)
        else:
            s["flight"].update(d["acc.z"], clamp(dt, 0.001, 0.1), z_m=z_m)

    os.makedirs("logs", exist_ok=True)
    path = time.strftime("logs/hover-%Y%m%d-%H%M%S.csv")
    with SyncCrazyflie(manual.URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf, open(path, "w", newline="") as fh:
        cf = scf.cf
        out = csv.writer(fh)
        out.writerow(["t", "phase", "thrust", "stick_up", "vz_est", "az", "roll", "pitch", "vbat",
                      "a_btn", "trim_roll", "trim_pitch", "t_hover", "z_m", "target_z"])
        if str(cf.param.get_value("stabilizer.stop")) == "1":
            raise SystemExit("emergency stop latched: power-cycle the drone")
        has_zr = str(cf.param.get_value("deck.bcZRanger2")) == "1"
        log = LogConfig(name="hover", period_in_ms=20)
        for var in ("acc.z", "stabilizer.roll", "stabilizer.pitch", "pm.vbat"):
            log.add_variable(var, "float")
        if has_zr and cf.log.toc.get_element_by_complete_name("range.zrange"):
            log.add_variable("range.zrange")
        cf.log.add_config(log)
        log.data_received_cb.add_callback(on_log)
        log.start()
        time.sleep(1.2)
        if len(s["samples"]) < 30:
            raise SystemExit("too few log samples: link problem")
        g0 = sum(s["samples"]) / len(s["samples"])
        if abs(s["roll"]) > 6 or abs(s["pitch"]) > 6:
            raise SystemExit(f"not level (roll {s['roll']:.1f}, pitch {s['pitch']:.1f}): put it flat")
        use_z = has_zr and len(s["z_samples"]) >= 5
        z0 = sum(s["z_samples"]) / len(s["z_samples"]) if use_z else 0.0
        mode_str = f"LASER height hold target={target_z:.2f} m (ground z0={z0:.3f} m)" if use_z else f"NO LASER (bcZRanger2={int(has_zr)}, z_samples={len(s['z_samples'])})"
        print(f"ground: acc.z={g0:.4f} g  vbat={s['vbat']:.2f} V  trim={trim}  [{mode_str}]")
        if not use_z and not dry and not no_laser_ok:
            print("\n*** WARNING: VL53L1X laser height sensor NOT detected (deck.bcZRanger2=0) ***")
            print("    Check 4 wires: VCC->J3-1(3V3), GND->J4-5, SDA->J4-6(SDA1), SCL->J4-7(SCL1), then power-cycle drone.")
            print("    Press Y on gamepad (or pass --no-laser-ok) to fly in manual/accel fallback mode anyway, or B / Ctrl-C to abort.")
            while True:
                pygame.event.pump()
                if pad.get_button(pygame.CONTROLLER_BUTTON_B) or not pad.attached():
                    raise SystemExit("aborted (laser sensor not detected)")
                if pad.get_button(pygame.CONTROLLER_BUTTON_Y):
                    print("    -> Y pressed: continuing without laser sensor (manual height fallback)")
                    break
                time.sleep(0.05)

        f = Flight(g0, target_z=target_z, has_z=use_z, z0=z0)
        s["flight"] = f
        t0 = last = time.time()
        killed = None
        try:
            if not dry:
                cf.param.set_value("system.forceArm", "1")
            for _ in range(15):
                cf.commander.send_setpoint(0, 0, 0, 0)
                time.sleep(0.02)
            print("taking off.  LB/RB = height -/+10 cm, LEFT STICK = climb/sink, A = land, B = KILL, D-pad = trim")
            dpad = {pygame.CONTROLLER_BUTTON_DPAD_LEFT: ("roll", -manual.TRIM_STEP),
                    pygame.CONTROLLER_BUTTON_DPAD_RIGHT: ("roll", manual.TRIM_STEP),
                    pygame.CONTROLLER_BUTTON_DPAD_UP: ("pitch", manual.TRIM_STEP),
                    pygame.CONTROLLER_BUTTON_DPAD_DOWN: ("pitch", -manual.TRIM_STEP)}
            held = set()
            shoulders = {pygame.CONTROLLER_BUTTON_LEFTSHOULDER: -1, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: 1}
            sh_held = set()
            while f.phase not in ("done", "abort"):
                now = time.time()
                dt, last = now - last, now
                pygame.event.pump()
                if pad.get_button(pygame.CONTROLLER_BUTTON_B):
                    killed = "B pressed"
                    break
                if abs(s["roll"]) > MAX_TILT or abs(s["pitch"]) > MAX_TILT:
                    killed = f"tilt {s['roll']:.0f}/{s['pitch']:.0f}"
                    break
                if now - t0 > MAX_FLIGHT_S + 10:
                    killed = "time cap"
                    break
                a_btn = pad.get_button(pygame.CONTROLLER_BUTTON_A)
                if not pad.attached() or a_btn or now - t0 > MAX_FLIGHT_S:
                    f.land()
                for btn, (k, step) in dpad.items():
                    if pad.get_button(btn) and btn not in held:
                        trim[k] = clamp(trim[k] + step, -manual.TRIM_MAX, manual.TRIM_MAX)
                        print(f"\ntrim roll={trim['roll']:+.2f} pitch={trim['pitch']:+.2f}")
                held = {b for b in dpad if pad.get_button(b)}
                for btn, sign in shoulders.items():
                    if pad.get_button(btn) and btn not in sh_held:
                        f.nudge(sign)
                        if f.has_z:
                            print(f"\ntarget height = {f.target_z:.2f} m (current z = {f.z:.2f} m)")
                        elif f.t_hover:
                            print(f"\nhover thrust {f.t_hover:.0f} ({f.t_hover0 / f.t_lift * 100:.0f} % of lift-off estimate)")
                sh_held = {b for b in shoulders if pad.get_button(b)}
                up = -manual.shape(stick(pygame.CONTROLLER_AXIS_LEFTY))
                before = f.phase
                thrust = f.step(dt, up)
                if f.phase != before:
                    extra = f" (hover thrust {f.t_hover:.0f}, target {f.target_z:.2f} m)" if f.t_hover else ""
                    print(f"\n{now - t0:5.1f}s -> {f.phase}{extra}")
                r, p, y, _ = manual.setpoint(stick(pygame.CONTROLLER_AXIS_RIGHTX),
                                             stick(pygame.CONTROLLER_AXIS_RIGHTY),
                                             stick(pygame.CONTROLLER_AXIS_LEFTX), 0)
                if f.phase == "pilot" and not no_learn:
                    manual.learn_trim(trim, r, p, dt)
                cf.commander.send_setpoint(r + trim["roll"], p + trim["pitch"], y, 0 if dry else thrust)
                out.writerow([f"{now - t0:.3f}", f.phase, thrust, f"{up:.2f}", f"{f.vz:.3f}",
                              f"{s['az']:.3f}", f"{s['roll']:.1f}", f"{s['pitch']:.1f}", f"{s['vbat']:.2f}",
                              int(a_btn), trim["roll"], trim["pitch"], f"{f.t_hover or 0:.0f}",
                              f"{f.z:.3f}" if use_z else "", f"{f.target_z:.2f}"])
                z_str = f"z={f.z:.2f}/{f.target_z:.2f}m " if use_z else ""
                print(f"\r{f.phase:7s} {z_str}thrust={thrust:5d} vz~{f.vz:+.2f} "
                      f"trim=({trim['roll']:+.2f},{trim['pitch']:+.2f}) "
                      f"vbat={s['vbat']:.2f}   ", end="", flush=True)
                time.sleep(max(0.0, 0.02 - (time.time() - now)))
        except KeyboardInterrupt:
            killed = "Ctrl-C"
        finally:
            cf.commander.send_stop_setpoint()
            cf.param.set_value("system.forceArm", "0")
            log.stop()
            json.dump(trim, open(manual.TRIM_FILE, "w"))
        if f.phase == "abort":
            print(f"\nABORT: no lift-off up to thrust {T_LIFTOFF_MAX}: charge battery, check props")
        result = "KILLED: " + killed if killed else ("stopped" if f.phase == "abort" else "landed")
        print(f"\n{result}  log: {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--height", type=float, default=Z_DEFAULT, help="target hover height in metres (default 1.0)")
    ap.add_argument("--sim", action="store_true", help="offline checks only")
    ap.add_argument("--dry", action="store_true", help="real drone, disarmed, thrust 0")
    ap.add_argument("--no-learn", action="store_true", help="disable stick learning of trim")
    ap.add_argument("--no-laser-ok", action="store_true", help="fly in accel fallback without asking if VL53L1X is missing")
    a = ap.parse_args()
    if a.sim:
        sim_check()
    else:
        run(a.dry, a.no_learn, a.height, a.no_laser_ok)
