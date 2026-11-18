#!/usr/bin/env python3
"""Assisted flight: automatic take-off, pilot-held height around measured hover thrust, automatic landing.

No height sensor, so the program cannot hold height by itself (sim: accelerometer-only hold climbs to
metres from a 0.005 g bias). Instead:
  take-off: thrust ramps until the accelerometer sees lift-off -> hover thrust for this battery, short climb.
  flying:   LEFT STICK UP/DOWN = climb/sink. Centre = hover thrust + vertical damping. Range +-12 %.
            Right stick = roll/pitch, left stick X = yaw, trim from tools/fly_trim.json.
  A = automatic landing (gentle descent, motors off on touchdown, never cut in the air).
  During landing the left stick still adds/removes thrust; full up = cancel landing.
  Land from low height: there is no height reference, so the descent is not speed-limited.
  B = kill motors now (any time).
  Controller lost -> landing. Tilt > 35 deg -> kill. Ctrl-C -> kill. 60 s -> landing.
Usage: .venv/bin/python tools/hover.py          (drone flat and still at start)
       .venv/bin/python tools/hover.py --sim    (offline checks, no drone)
       .venv/bin/python tools/hover.py --dry    (real drone, never armed, thrust 0: pipeline + false lift-off check)
Flight log CSV: logs/hover-*.csv
"""
import argparse
import csv
import json
import os
import random
import time

G = 9.81
T_START = 30000           # ramp start, well below lift-off
RAMP = 6000               # thrust units per second during lift-off search
T_LIFTOFF_MAX = 55000     # no lift-off by here -> abort (battery/props)
THRUST_LIMIT = 58000      # firmware caps at 60000
LIFTOFF_VZ = 0.15         # m/s estimated climb that counts as lift-off
LIFTOFF_LAG = 0.50        # s; detection delay, subtracted from the ramp to estimate hover thrust
CLIMB_S, CLIMB_GAIN = 0.8, 1.06    # short climb out of ground effect after lift-off
TAU = 1.0                 # s; leaky speed estimate = damping only, cannot run away on bias
KD = 0.3                  # damping, fraction of hover thrust per m/s
PILOT_RANGE = 0.12        # full left stick = +-12 % of hover thrust
BAND = (0.80, 1.15)       # thrust / hover thrust, always
DESC_GAIN, DESC_SLOPE, DESC_MIN = 0.92, 0.05, 0.82   # landing: 92 % of hover, -5 %/s, floor 82 %
DESC_BRAKE_V = 0.5        # m/s; landing damping only brakes descents faster than this (flight 2: full
                          # damping cancelled the descent and A looked dead)
LEARN_S = 6.0             # s; holding the stick shifts stick-centre hover thrust (+-12 % max)
DESC_MAX_S = 4.0
SETTLE_S = 2.0            # after DESC_MAX_S without touchdown: ramp 0.85 -> 0 of hover thrust
TOUCH_G = 0.4             # filtered upward accel spike (g) = touchdown
MAX_TILT = 35.0
MAX_FLIGHT_S = 60.0


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class Flight:
    """Phases: ramp -> climb -> pilot -> descend -> (settle) -> done, or abort."""

    def __init__(self, g0: float):
        self.g0, self.vz, self.az_f = g0, 0.0, g0
        self.t_hover = self.t_hover0 = None
        self.phase, self.t_phase, self.cmd = "ramp", 0.0, float(T_START)

    def update(self, az: float, dt: float) -> None:
        """Body z acceleration in g, from the drone log."""
        self.vz += (az - self.g0) * G * dt - self.vz * dt / TAU
        self.az_f += 0.3 * (az - self.az_f)

    def enter(self, phase: str) -> None:
        self.phase, self.t_phase = phase, 0.0

    def land(self) -> None:
        if self.phase == "ramp":          # not detected airborne: at most a few cm up
            self.enter("done")
        elif self.phase in ("climb", "pilot"):
            self.enter("descend")

    def _thrust(self, gain: float, vz_free: float = 0.0) -> int:
        """Damping acts on speed beyond vz_free (m/s, downward allowance)."""
        v = min(0.0, self.vz + vz_free) if vz_free else self.vz
        t = self.t_hover * gain - KD * self.t_hover * v
        return int(clamp(t, BAND[0] * self.t_hover, min(BAND[1] * self.t_hover, THRUST_LIMIT)))

    def step(self, dt: float, stick_up: float = 0.0) -> int:
        """stick_up: -1..1, already dead-zoned. Returns thrust to send."""
        self.t_phase += dt
        if self.phase == "ramp":
            self.cmd += RAMP * dt
            if self.vz > LIFTOFF_VZ:
                self.t_hover = self.t_hover0 = self.cmd - RAMP * LIFTOFF_LAG
                self.enter("climb")
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
            # pilot keeps pushing one way -> stick centre was wrong: move hover thrust slowly toward it
            self.t_hover = clamp(self.t_hover * (1 + PILOT_RANGE * stick_up * dt / LEARN_S),
                                 self.t_hover0 * (1 - PILOT_RANGE), self.t_hover0 * (1 + PILOT_RANGE))
            return self._thrust(1 + PILOT_RANGE * stick_up)
        if self.phase == "descend":
            if stick_up > 0.8:
                self.enter("pilot")
                return self._thrust(1.0)
            if self.t_phase > 0.3 and touched:
                self.enter("done")
                return 0
            if self.t_phase >= DESC_MAX_S:
                self.enter("settle")       # never cut in the air
            else:
                gain = max(DESC_MIN, DESC_GAIN - DESC_SLOPE * self.t_phase)
                return self._thrust(gain + PILOT_RANGE * stick_up, vz_free=DESC_BRAKE_V)
        if self.phase == "settle":
            if touched or self.t_phase >= SETTLE_S:
                self.enter("done")
                return 0
            return int(self.t_hover * 0.85 * (1 - self.t_phase / SETTLE_S))
        return 0


def sim(seed: int, bias: float, pilot: bool, pilot_s: float = 6.0, t_true: float = 44000.0) -> dict:
    """Crude 1-D model: unknown hover thrust, 40 ms latency, noise, accelerometer bias (g), battery sag.
    pilot=True: human holds ~0.4 m by eye (0.3 s reaction), lowers to ~0.15 m, presses A.
    pilot=False: hands off for 3 s, then A."""
    random.seed(seed)
    dt, z, vz, latency, seen = 0.02, 0.0, 0.0, [0, 0], [(0.0, 0.0)] * 15
    f = Flight(g0=1.0)
    max_z, touch_v, pilot_z = 0.0, 0.0, []
    for _ in range(int(40 / dt)):
        stick = 0.0
        z_seen, vz_seen = seen[0]                    # what the pilot saw 0.3 s ago
        if f.phase in ("pilot", "descend") and pilot:
            target = 0.4 if f.phase == "pilot" and f.t_phase < pilot_s - 2 else 0.15
            if f.phase == "descend":
                target = -0.3                        # wants it down, but not fast
                stick = clamp(2.0 * (-0.4 - vz_seen), -1, 0.7)
            else:
                stick = clamp(1.5 * (target - z_seen) - 1.0 * vz_seen, -1, 1)
        if f.phase == "pilot" and f.t_phase >= (pilot_s if pilot else 3.0):
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
        f.update(1 + a / G + spike + bias + random.gauss(0, 0.02), dt)
        max_z = max(max_z, z)
        if f.phase == "pilot":
            pilot_z.append(z)
        if f.phase in ("done", "abort"):
            break
    return {"phase": f.phase, "t_hover": f.t_hover, "max_z": max_z, "touch_v": touch_v, "final_z": z,
            "hands_off_drift": max(pilot_z) - min(pilot_z) if pilot_z else 0.0}


def sim_check() -> None:
    for bias in (-0.005, 0.0, 0.005):
        for t_true in (40000.0, 44000.0, 50000.0):
            rs = [sim(seed, bias, pilot=True, t_true=t_true) for seed in range(1, 9)]
            ho = [sim(seed, bias, pilot=False, t_true=t_true) for seed in range(1, 9)]
            print(f"bias {bias:+.3f} g, hover {t_true:.0f}: est {min(r['t_hover'] for r in rs):.0f}-"
                  f"{max(r['t_hover'] for r in rs):.0f} | piloted: max {max(r['max_z'] for r in rs):.2f} m, "
                  f"touchdown <= {max(r['touch_v'] for r in rs):.2f} m/s | hands-off 3 s: "
                  f"max {max(r['max_z'] for r in ho):.2f} m")
            for r in rs:
                assert r["phase"] == "done" and r["final_z"] < 0.05, r     # always ends on the ground
                assert abs(r["t_hover"] / t_true - 1) < 0.08, r           # lift-off detection works
                assert r["max_z"] < 1.0 and r["touch_v"] < 1.5, r        # pilot can hold it, soft landing
            assert all(r["phase"] == "done" and r["final_z"] < 0.05 for r in ho)  # even hands-off ends down
    print("sim OK")


def run(dry: bool) -> None:
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
    s = {"samples": [], "last_ts": None, "flight": None}

    def on_log(ts, d, _):
        s.update(roll=d["stabilizer.roll"], pitch=d["stabilizer.pitch"], vbat=d["pm.vbat"], az=d["acc.z"])
        dt = (ts - s["last_ts"]) / 1000 if s["last_ts"] is not None else 0.02
        s["last_ts"] = ts
        if s["flight"] is None:
            s["samples"].append(d["acc.z"])
        else:
            s["flight"].update(d["acc.z"], clamp(dt, 0.001, 0.1))

    os.makedirs("logs", exist_ok=True)
    path = time.strftime("logs/hover-%Y%m%d-%H%M%S.csv")
    with SyncCrazyflie(manual.URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf, open(path, "w", newline="") as fh:
        cf = scf.cf
        out = csv.writer(fh)
        out.writerow(["t", "phase", "thrust", "stick_up", "vz_est", "az", "roll", "pitch", "vbat",
                      "a_btn", "trim_roll", "trim_pitch", "t_hover"])
        if str(cf.param.get_value("stabilizer.stop")) == "1":
            raise SystemExit("emergency stop latched: power-cycle the drone")
        log = LogConfig(name="hover", period_in_ms=20)
        for var in ("acc.z", "stabilizer.roll", "stabilizer.pitch", "pm.vbat"):
            log.add_variable(var, "float")
        cf.log.add_config(log)
        log.data_received_cb.add_callback(on_log)
        log.start()
        time.sleep(1.2)                          # ground calibration: drone must be still and flat
        if len(s["samples"]) < 30:
            raise SystemExit("too few log samples: link problem")
        g0 = sum(s["samples"]) / len(s["samples"])
        if abs(s["roll"]) > 6 or abs(s["pitch"]) > 6:
            raise SystemExit(f"not level (roll {s['roll']:.1f}, pitch {s['pitch']:.1f}): put it flat")
        print(f"ground: acc.z={g0:.4f} g  vbat={s['vbat']:.2f} V  trim={trim}")

        f = Flight(g0)
        s["flight"] = f
        t0 = last = time.time()
        killed = None
        try:
            if not dry:
                cf.param.set_value("system.forceArm", "1")
            for _ in range(15):                  # zero setpoints unlock thrust in the firmware
                cf.commander.send_setpoint(0, 0, 0, 0)
                time.sleep(0.02)
            print("taking off.  LEFT STICK up/down = height, A = land, B = KILL, D-pad = trim")
            dpad = {pygame.CONTROLLER_BUTTON_DPAD_LEFT: ("roll", -manual.TRIM_STEP),
                    pygame.CONTROLLER_BUTTON_DPAD_RIGHT: ("roll", manual.TRIM_STEP),
                    pygame.CONTROLLER_BUTTON_DPAD_UP: ("pitch", manual.TRIM_STEP),
                    pygame.CONTROLLER_BUTTON_DPAD_DOWN: ("pitch", -manual.TRIM_STEP)}
            held = set()
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
                up = -manual.shape(stick(pygame.CONTROLLER_AXIS_LEFTY))   # SDL: stick up = negative
                before = f.phase
                thrust = f.step(dt, up)
                if f.phase != before:
                    extra = f" (hover thrust {f.t_hover:.0f})" if f.phase == "climb" else ""
                    print(f"\n{now - t0:5.1f}s -> {f.phase}{extra}")
                r, p, y, _ = manual.setpoint(stick(pygame.CONTROLLER_AXIS_RIGHTX),
                                             stick(pygame.CONTROLLER_AXIS_RIGHTY),
                                             stick(pygame.CONTROLLER_AXIS_LEFTX), 0)
                cf.commander.send_setpoint(r + trim["roll"], p + trim["pitch"], y, 0 if dry else thrust)
                out.writerow([f"{now - t0:.3f}", f.phase, thrust, f"{up:.2f}", f"{f.vz:.3f}",
                              f"{s['az']:.3f}", f"{s['roll']:.1f}", f"{s['pitch']:.1f}", f"{s['vbat']:.2f}",
                              int(a_btn), trim["roll"], trim["pitch"], f"{f.t_hover or 0:.0f}"])
                print(f"\r{f.phase:8s} thrust={thrust:5d} stick={up:+.2f} vz~{f.vz:+.2f} "
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
    ap.add_argument("--sim", action="store_true", help="offline checks only")
    ap.add_argument("--dry", action="store_true", help="real drone, disarmed, thrust 0")
    a = ap.parse_args()
    if a.sim:
        sim_check()
    else:
        run(a.dry)
