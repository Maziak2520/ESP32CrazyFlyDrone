#!/usr/bin/env python3
"""cflib end-to-end test: connect, read params, stream logs, send commander setpoints.

SAFETY: sends a 1 s low-thrust pulse. Run only with motors disconnected or propellers removed.
Usage: .venv/bin/python tools/drone_link_test.py [--no-thrust]
"""
import sys
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "udp://192.168.43.42:2390"
PULSE_THRUST = 12000  # of 65535
# Each log block payload must fit one CRTP packet (~26 bytes), hence two blocks.
LOG_BLOCKS = [["stabilizer.roll", "stabilizer.pitch", "stabilizer.yaw", "pm.vbat"],
              ["pwm.m1_pwm", "pwm.m2_pwm", "pwm.m3_pwm", "pwm.m4_pwm", "stabilizer.thrust"]]
# motor.m* goes stale under emergency stop; pwm.m*_pwm is the real output.

samples = []  # (time, {var: value}), both blocks interleaved


def run(send_thrust: bool) -> int:
    cflib.crtp.init_drivers()
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="/tmp/cf_cache")) as scf:
        cf = scf.cf
        toc = cf.param.toc.toc
        print(f"connected; param groups: {len(toc)}, params: {sum(len(g) for g in toc.values())}")
        for name in ["system.selftestPassed", "stabilizer.stop", "stabilizer.estimator", "stabilizer.controller"]:
            group, var = name.split(".")
            if var in toc.get(group, {}):
                print(f"  {name} = {cf.param.get_value(name)}")

        confs = []
        for i, block in enumerate(LOG_BLOCKS):
            conf = LogConfig(name=f"t{i}", period_in_ms=100)
            for v in block:
                if cf.log.toc.get_element_by_complete_name(v):
                    conf.add_variable(v)  # fetch as the TOC's native type
                else:
                    print(f"  log var missing: {v}")
            cf.log.add_config(conf)
            conf.data_received_cb.add_callback(lambda ts, d, _: samples.append((time.time(), d)))
            conf.start()
            confs.append(conf)

        time.sleep(1.5)
        for block in LOG_BLOCKS:
            last = next((d for _, d in reversed(samples) if block[0] in d), None)
            print(f"idle sample: {last}")

        phases = [("unlock", 0, 1.0)] + ([("pulse", PULSE_THRUST, 1.0)] if send_thrust else []) + [("zero", 0, 1.0)]
        peak, counts, seen, last_motor = {}, {}, {}, None
        estop = cf.param.get_value("stabilizer.stop")
        if send_thrust and "forceArm" in toc.get("system", {}):
            cf.param.set_value("system.forceArm", "1")  # upstream fw boots disarmed; runtime only
        for label, thrust, dur in phases:
            start = time.time()
            while time.time() - start < dur:
                cf.commander.send_setpoint(0, 0, 0, thrust)
                time.sleep(0.02)
            window = [d for t, d in samples if t >= start]
            motors = [max(d[f"pwm.m{i}_pwm"] for i in range(1, 5)) for d in window if "pwm.m1_pwm" in d]
            thrusts = [d["stabilizer.thrust"] for d in window if "stabilizer.thrust" in d]
            peak[label], counts[label] = max(motors, default=None), len(window)
            last_motor = motors[-1] if motors else None
            print(f"{label:6s} cmd={thrust:5d}  fw thrust max={max(thrusts, default=None)}  max pwm={peak[label]}  ({len(window)} samples)")
            seen[label] = max(thrusts, default=None)
        cf.commander.send_stop_setpoint()
        if send_thrust and "forceArm" in toc.get("system", {}):
            cf.param.set_value("system.forceArm", "0")
        for conf in confs:
            conf.stop()

    print(f"total log samples: {len(samples)}")
    ok = all(n >= 10 for n in counts.values()) and last_motor == 0  # logs kept flowing; motors end stopped
    if send_thrust:
        ok = ok and seen["pulse"] == PULSE_THRUST  # firmware received the setpoint
        if str(estop) == "1":
            print("NOTE: stabilizer.stop=1 (emergency stop latched): PWM held at 0. Reboot to clear.")
        else:
            ok = ok and (peak["pulse"] or 0) > 0
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run(send_thrust="--no-thrust" not in sys.argv))
