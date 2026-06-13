#!/usr/bin/env python3
"""OLPR – Frigate LPR bridge (entrypoint).

Tynn shim: all logikk bor i olpr_core.bridge.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from olpr_core import bridge

if __name__ == "__main__":
    bridge.run()
