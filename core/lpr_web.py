#!/usr/bin/env python3
"""OLPR – LPR Dashboard (entrypoint).

Tynn shim: all logikk bor i olpr_core. Homeserver vil i steg 4 ha sin egen
entrypoint som registrerer ekstra ruter før web.run().
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from olpr_core import web

if __name__ == "__main__":
    web.run()
