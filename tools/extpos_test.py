#!/usr/bin/env python3
"""Does the firmware accept external position (CRTP port 6, as from a camera)? No thrust is sent.

Switches estimator to Kalman (runtime only), streams fake positions, checks stateEstimate follows.
Usage: .venv/bin/python tools/extpos_test.py
"""
import sys
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "udp://192.168.43.42:2390"
TARGETS = [(1.0, 2.0, 0.5), (-1.0, 0.5, 0.3)]  # metres
TOLERANCE = 0.10
est = {}


def stream(cf, pos, seconds):
    end = time.time() + seconds
    while time.time() < end:
        cf.extpos.send_extpos(*pos)
        time.sleep(0.02)


def main() -> int:
    cflib.crtp.init_drivers()
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf:
        cf = scf.cf
        original = cf.param.get_value("stabilizer.estimator")
        cf.param.set_value("stabilizer.estimator", "2")
        time.sleep(0.5)
        if "resetEstimation" in cf.param.toc.toc.get("kalman", {}):
            cf.param.set_value("kalman.resetEstimation", "1")
            time.sleep(0.1)
            cf.param.set_value("kalman.resetEstimation", "0")
        print(f"estimator {original} -> {cf.param.get_value('stabilizer.estimator')}")

        conf = LogConfig(name="pos", period_in_ms=50)
        for v in ("stateEstimate.x", "stateEstimate.y", "stateEstimate.z"):
            conf.add_variable(v, "float")
        cf.log.add_config(conf)
        conf.data_received_cb.add_callback(lambda ts, d, _: est.update(d))
        conf.start()

        time.sleep(2)
        print(f"baseline (no extpos): {fmt(est)}")
        results = []
        for target in TARGETS:
            stream(cf, target, 3.0)
            err = max(abs(est[f"stateEstimate.{a}"] - t) for a, t in zip("xyz", target))
            results.append(err <= TOLERANCE)
            print(f"sent {target} -> estimate {fmt(est)}  max err {err:.3f} m")

        conf.stop()
        cf.param.set_value("stabilizer.estimator", str(original))
        time.sleep(0.3)
        print(f"estimator restored -> {cf.param.get_value('stabilizer.estimator')}")

    ok = all(results)
    print("RESULT:", "PASS (extpos accepted)" if ok else "FAIL (estimate did not follow extpos)")
    return 0 if ok else 1


def fmt(d):
    return "(" + ", ".join(f"{d.get(f'stateEstimate.{a}', float('nan')):+.3f}" for a in "xyz") + ")"


if __name__ == "__main__":
    sys.exit(main())
