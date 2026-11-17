#!/usr/bin/env python3
"""Spin each motor alone (M1..M4) at low power to check wiring and direction. PROPELLERS OFF.

Usage: .venv/bin/python tools/motor_test.py [ratio] [on_s]   (default 13107 = 20%, firmware's own test level; 1 s)
"""
import sys
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "udp://192.168.43.42:2390"
RATIO = int(sys.argv[1]) if len(sys.argv) > 1 else 13107
ON_S = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
GAP_S = 2.0
assert 0 < ON_S <= 10
assert 0 < RATIO <= 20000, "keep bench test low"

cflib.crtp.init_drivers()
pwm = {}
with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf:
    cf = scf.cf
    if str(cf.param.get_value("stabilizer.stop")) == "1":
        raise SystemExit("emergency stop latched: power-cycle first")
    log = LogConfig(name="pwm", period_in_ms=100)
    for i in range(1, 5):
        log.add_variable(f"pwm.m{i}_pwm")
    cf.log.add_config(log)
    log.data_received_cb.add_callback(lambda ts, d, _: pwm.update(d))
    log.start()

    def all_off():
        for i in range(1, 5):
            cf.param.set_value(f"motorPowerSet.m{i}", "0")

    try:
        all_off()
        cf.param.set_value("motorPowerSet.enable", "1")
        cf.param.set_value("system.forceArm", "1")
        print("starting in 3 s", flush=True)
        time.sleep(3)
        for i in range(1, 5):
            t0 = time.strftime("%H:%M:%S")
            cf.param.set_value(f"motorPowerSet.m{i}", str(RATIO))
            time.sleep(ON_S)
            seen = [pwm.get(f"pwm.m{k}_pwm", 0) for k in range(1, 5)]
            cf.param.set_value(f"motorPowerSet.m{i}", "0")
            print(f"{t0} M{i} on {ON_S:.0f}s  pwm seen m1..m4 = {seen}", flush=True)
            time.sleep(GAP_S)
    finally:
        all_off()
        cf.param.set_value("system.forceArm", "0")
        cf.param.set_value("motorPowerSet.enable", "0")
        time.sleep(0.5)
        print("final pwm:", [pwm.get(f"pwm.m{k}_pwm", 0) for k in range(1, 5)],
              "forceArm", cf.param.get_value("system.forceArm"),
              "enable", cf.param.get_value("motorPowerSet.enable"), flush=True)
        log.stop()
