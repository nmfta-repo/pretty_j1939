#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
import time
import sys

# Simulate python-can logger output with headers
lines = [
    "Connected to CantactBus: CANtact: ch:0\n",
    "Can Logger (Started on 2026-02-06 10:38:58.771323)\n",
    "Timestamp: 1.000000 ID: 18F0010B X Rx DL: 8 C0 FF F0 FF FF 40 0B 3F\n",
    "Timestamp: 2.000000 ID: 0CF00400 X Rx DL: 8 00 41 FF 20 48 14 00 F0\n",
]

for line in lines:
    sys.stdout.write(line)
    sys.stdout.flush()
    time.sleep(1)
