#!/usr/bin/env python3
"""Ground level calibration: measure the drone's attitude offset, cancelling floor tilt by rotating 4x 90 deg.

Setup: rest the drone on 4 equal supports under the 4 motor pods (battery and legs hanging free), so the
reference is the motor plane, not whatever touches the floor. Motors stay off; nothing is armed.
Steps: Enter -> 3 s sample, rotate drone (with its supports) 90 deg the same way, Enter ... 4 times.
Result: offset = mean of the 4 readings (floor tilt rotates with the drone and cancels).
        Written as trim to tools/fly_trim.json (old trim kept in tools/level_calib.json).
Usage: .venv/bin/python tools/calibrate_level.py [--no-save]
"""
import argparse
import json
import math
import os
import statistics
import time

SAMPLE_S = 3.0
MAX_SD = 0.3              # deg; more = drone moved during the sample
HERE = os.path.dirname(os.path.abspath(__file__))


def solve(readings):
    """readings: 4 (roll, pitch) at 0/90/180/270 deg. Returns offset, floor tilt (deg), max fit residual (deg)."""
    off_r = sum(r for r, _ in readings) / 4
    off_p = sum(p for _, p in readings) / 4
    floor = [(r - off_r, p - off_p) for r, p in readings]
    tilts = [math.hypot(*f) for f in floor]
    tilt = sum(tilts) / 4
    # a pure floor tilt has the same size in every position; spread = measurement/support error
    return (off_r, off_p), tilt, max(abs(t - tilt) for t in tilts)


def _check():
    a, b, off = 0.8, -0.3, (1.9, 0.5)          # floor tilt (a, b) seen at 0 deg; rotates by 90 deg each step
    fl = [(a, b), (b, -a), (-a, -b), (-b, a)]
    o, tilt, spread = solve([(off[0] + x, off[1] + y) for x, y in fl])
    assert abs(o[0] - 1.9) < 1e-9 and abs(o[1] - 0.5) < 1e-9 and abs(tilt - math.hypot(a, b)) < 1e-9 and spread < 1e-9
    fl.reverse()                                # rotating the other way gives the same offset
    assert abs(solve([(off[0] + x, off[1] + y) for x, y in fl])[0][0] - 1.9) < 1e-9


_check()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true", help="measure only, do not change the trim")
    args = ap.parse_args()

    import cflib.crtp
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    from fly import URI, TRIM_FILE, TRIM_MAX

    cflib.crtp.init_drivers()
    samples = []
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf:
        cf = scf.cf
        log = LogConfig(name="lvl", period_in_ms=50)
        for v in ("stabilizer.roll", "stabilizer.pitch"):
            log.add_variable(v, "float")
        cf.log.add_config(log)
        log.data_received_cb.add_callback(lambda ts, d, _: samples.append((d["stabilizer.roll"], d["stabilizer.pitch"])))
        log.start()
        readings = []
        try:
            while len(readings) < 4:
                pos = len(readings) * 90
                input(f"\nposition {pos:3d} deg: drone still on its 4 supports, press Enter ")
                time.sleep(0.5)                 # let hand vibration settle
                del samples[:]
                time.sleep(SAMPLE_S)
                rs, ps = [s[0] for s in samples], [s[1] for s in samples]
                if len(rs) < 20:
                    print(f"  only {len(rs)} samples: link problem, repeat")
                    continue
                sd = max(statistics.pstdev(rs), statistics.pstdev(ps))
                if sd > MAX_SD:
                    print(f"  moved during sample (sd {sd:.2f} deg): repeat")
                    continue
                readings.append((statistics.mean(rs), statistics.mean(ps)))
                print(f"  roll {readings[-1][0]:+.2f}  pitch {readings[-1][1]:+.2f}  (n={len(rs)}, sd {sd:.2f})"
                      + ("" if len(readings) == 4 else "   -> rotate 90 deg, same direction"))
        finally:
            log.stop()

    (off_r, off_p), tilt, spread = solve(readings)
    print(f"\ndrone offset: roll {off_r:+.2f}  pitch {off_p:+.2f} deg")
    print(f"floor/support tilt: {tilt:.2f} deg   fit spread: {spread:.2f} deg"
          + ("   (> 0.3: supports uneven or drone shifted; consider repeating)" if spread > 0.3 else ""))
    if args.no_save:
        return
    if max(abs(off_r), abs(off_p)) > TRIM_MAX:
        raise SystemExit(f"offset beyond trim limit {TRIM_MAX} deg: check mounting, not saved")
    old = json.load(open(TRIM_FILE)) if os.path.exists(TRIM_FILE) else None
    json.dump({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "readings": readings, "offset": [off_r, off_p],
               "floor_tilt": tilt, "spread": spread, "previous_trim": old},
              open(os.path.join(HERE, "level_calib.json"), "w"), indent=1)
    json.dump({"roll": round(off_r, 2), "pitch": round(off_p, 2)}, open(TRIM_FILE, "w"))
    print(f"trim {old} -> {{'roll': {off_r:.2f}, 'pitch': {off_p:.2f}}} saved")


if __name__ == "__main__":
    main()
