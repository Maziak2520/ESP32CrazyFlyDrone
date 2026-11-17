#!/usr/bin/env python3
"""Spin ONE motor until stopped (for identifying it). PROPELLERS OFF.

Start: .venv/bin/python tools/motor_spin.py <1-4> [ratio] [max_s]   (default 13107 = 20%, 60 s cap)
Stop:  touch /tmp/motor_stop   (or Ctrl-C). All motors -> 0, disarm, override off.
If this process dies without cleanup the motor keeps running: rerun with any motor and stop it at once.
"""
import os
import sys
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "udp://192.168.43.42:2390"
STOP = "/tmp/motor_stop"
motor = int(sys.argv[1])
ratio = int(sys.argv[2]) if len(sys.argv) > 2 else 13107
max_s = float(sys.argv[3]) if len(sys.argv) > 3 else 60
assert motor in (1, 2, 3, 4) and 0 < ratio <= 20000 and max_s <= 120

if os.path.exists(STOP):
    os.remove(STOP)
cflib.crtp.init_drivers()
with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf:
    cf = scf.cf
    try:
        for i in range(1, 5):
            cf.param.set_value(f"motorPowerSet.m{i}", "0")
        cf.param.set_value("motorPowerSet.enable", "1")
        cf.param.set_value("system.forceArm", "1")
        cf.param.set_value(f"motorPowerSet.m{motor}", str(ratio))
        print(f"{time.strftime('%H:%M:%S')} M{motor} spinning at {ratio}", flush=True)
        end = time.time() + max_s
        while time.time() < end and not os.path.exists(STOP):
            time.sleep(0.1)
        print(f"{time.strftime('%H:%M:%S')} stopping ({'stop file' if os.path.exists(STOP) else 'time cap'})", flush=True)
    finally:
        for i in range(1, 5):
            cf.param.set_value(f"motorPowerSet.m{i}", "0")
        cf.param.set_value("system.forceArm", "0")
        cf.param.set_value("motorPowerSet.enable", "0")
        time.sleep(0.3)
        print("off: forceArm", cf.param.get_value("system.forceArm"),
              "enable", cf.param.get_value("motorPowerSet.enable"), flush=True)
