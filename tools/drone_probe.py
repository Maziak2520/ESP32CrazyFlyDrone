#!/usr/bin/env python3
"""Link probe for ESP-Drone over Wi-Fi/UDP. Read-only: CRTP echo + param TOC info; never commands motors.

Usage: join ESP-DRONE_XXXXXXXXXXXX Wi-Fi, then `/usr/bin/python3 -I tools/drone_probe.py`.
macOS: use system python; unsigned (e.g. uv-downloaded) interpreters get EHOSTUNREACH
from Local Network privacy.
"""
import socket
import struct
import sys

DRONE = ("192.168.43.42", 2390)
LOCAL_PORT = 2399
ECHO = 0xFC  # port 15 (link), channel 0 = echo; null packets (0xFF) get no reply
PARAM_TOC = 0x2C  # port 2 (param), channel 0 = TOC
TOC_GET_INFO_V2 = 0x03


def frame(header: int, data: bytes = b"") -> bytes:
    raw = bytes([header]) + data
    return raw + bytes([sum(raw) % 256])


assert frame(0xFC, b"ping0") == bytes.fromhex("fc70696e6730da")  # captured from real drone

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("", LOCAL_PORT))
sock.settimeout(0.3)

echoes = 0
params = None
for i in range(10):
    sock.sendto(frame(ECHO, b"ping%d" % i), DRONE)
    sock.sendto(frame(PARAM_TOC, bytes([TOC_GET_INFO_V2])), DRONE)
    try:
        while True:
            pkt, _ = sock.recvfrom(64)
            if pkt[:-1] == frame(ECHO, b"ping%d" % i)[:-1]:
                echoes += 1
            elif pkt[0] >> 4 == 2 and pkt[1] == TOC_GET_INFO_V2:
                params, crc = struct.unpack("<HI", pkt[2:8])
    except socket.timeout:
        pass

print(f"echo {echoes}/10")
if params is not None:
    print(f"param TOC: {params} params, crc 0x{crc:08x}")
sys.exit(0 if echoes else 1)
