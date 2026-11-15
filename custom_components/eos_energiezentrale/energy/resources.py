"""EOS resource requirements shared by commissioning and controller setup."""
import json
import re


def validate_resources(options):
    battery=options.get('battery_resource')
    if not isinstance(battery,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',battery):
        raise ValueError('Invalid battery resource')
    raw=options.get('vehicles','[]')
    fleet=json.loads(raw) if isinstance(raw,str) else raw
    if fleet:
        # Each listed vehicle is validated separately with its own assignment.
        return
    vehicle=options.get('vehicle_resource','')
    required=options.get('wallbox_type')!='none'
    if vehicle=='' and not required:
        return
    if not isinstance(vehicle,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',vehicle):
        raise ValueError('Invalid vehicle resource')
    if required and vehicle==battery:
        raise ValueError('Resources must be different')
