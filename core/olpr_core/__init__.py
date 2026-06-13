"""OLPR-kjernen — gjenbrukbar LPR-motor (web + bridge + config).

Konsumeres av core/lpr_web.py og core/lpr_bridge.py (tynne shims), og er ment
å importeres av homeserver i steg 4 av felles-kjerne-planen:

    from olpr_core import web
    web.register_routes('GET', {'/api/ludvig': ...})
    web.run(auth=False)
"""
