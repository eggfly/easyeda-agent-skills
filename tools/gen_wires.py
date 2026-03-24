#!/usr/bin/env python3
"""
Generate EasyEDA Pro wire source code lines for a schematic.

Reads the current .epro2 to get pin positions, then generates WIRE/LINE/ATTR
lines that can be appended to the SCH_PAGE section.

Usage:
    python3 gen_wires.py <file.epro2> --netlist netlist.json
    python3 gen_wires.py <file.epro2> --dry-run     # Preview without generating
"""

import json
import sys
import os
import secrets
import argparse
from parse_epro2 import load_epro2, get_max_ticket, pin_abs_position


def rand_id():
    """Generate a 16-char lowercase hex ID like EasyEDA uses."""
    return secrets.token_hex(8)


def make_wire_lines(start_x, start_y, end_x, end_y, net_name="",
                    ticket_start=1000, z_start=100):
    """
    Generate EasyEDA Pro source lines for a wire connection.
    Returns (list_of_lines, next_ticket, next_z).
    """
    t = ticket_start
    z = z_start
    wire_id = rand_id()
    lines = []

    # WIRE
    lines.append(
        f'{{"type":"WIRE","ticket":{t},"id":"{wire_id}"}}||{{"zIndex":{z}}}|'
    )
    t += 1
    z += 1

    # LINE
    line_id = rand_id()
    lines.append(
        f'{{"type":"LINE","ticket":{t},"id":"{line_id}"}}'
        f'||{{"fillColor":null,"fillStyle":null,"strokeColor":null,'
        f'"strokeStyle":null,"strokeWidth":null,'
        f'"startX":{start_x},"startY":{start_y},'
        f'"endX":{end_x},"endY":{end_y},'
        f'"lineGroup":"{wire_id}"}}|'
    )
    t += 1

    # Relevance ATTR
    rel_id = rand_id()
    lines.append(
        f'{{"type":"ATTR","ticket":{t},"id":"{rel_id}"}}'
        f'||{{"x":null,"y":null,"rotation":null,"color":null,'
        f'"fontFamily":null,"fontSize":null,"fontWeight":null,'
        f'"italic":null,"underline":null,"align":null,'
        f'"value":"[]","keyVisible":null,"valueVisible":null,'
        f'"key":"Relevance","fillColor":null,'
        f'"parentId":"{wire_id}","zIndex":0}}|'
    )
    t += 1

    # NET ATTR
    net_id = rand_id()
    label_x = start_x if start_x != end_x else start_x
    label_y = start_y if start_y != end_y else start_y
    lines.append(
        f'{{"type":"ATTR","ticket":{t},"id":"{net_id}"}}'
        f'||{{"x":{label_x},"y":{label_y},"rotation":0,'
        f'"color":null,"fontFamily":null,"fontSize":null,'
        f'"fontWeight":null,"italic":null,"underline":null,'
        f'"align":null,"value":"{net_name}",'
        f'"keyVisible":false,"valueVisible":true,'
        f'"key":"NET","fillColor":null,'
        f'"parentId":"{wire_id}","zIndex":2}}|'
    )
    t += 1

    return lines, t, z


def make_power_symbol(x, y, net_name, sym_uuid, dev_uuid,
                      rotation=None, ticket_start=1000, z_start=100):
    """
    Generate EasyEDA Pro source lines for a power symbol.
    Returns (list_of_lines, next_ticket, next_z, component_id).

    sym_uuid/dev_uuid: project-specific UUIDs extracted from existing epru.
    rotation: 90=arrow left (VCC/3V3/+5V), 270=bar down (GND).
    """
    t = ticket_start
    z = z_start
    comp_id = rand_id()
    lines = []

    if rotation is None:
        rotation = 270 if net_name == "GND" else 90

    # COMPONENT
    lines.append(
        f'{{"type":"COMPONENT","ticket":{t},"id":"{comp_id}"}}'
        f'||{{"partId":"pid8a0e77bacb214e","x":{x},"y":{y},'
        f'"rotation":{rotation},"isMirror":false,"attrs":{{}},"zIndex":{z}}}|'
    )
    t += 1
    z += 1

    # Symbol ATTR
    aid = rand_id()
    sym_x = x + 30 if rotation == 90 else x - 30
    sym_y = y
    lines.append(
        f'{{"type":"ATTR","ticket":{t},"id":"{aid}"}}'
        f'||{{"x":{sym_x},"y":{sym_y},"rotation":{rotation},'
        f'"color":null,"fontFamily":null,"fontSize":null,'
        f'"fontWeight":null,"italic":null,"underline":null,'
        f'"align":null,"value":"{sym_uuid}",'
        f'"keyVisible":null,"valueVisible":null,'
        f'"key":"Symbol","fillColor":null,'
        f'"parentId":"{comp_id}","zIndex":1,"locked":false}}|'
    )
    t += 1

    # Device ATTR
    aid = rand_id()
    lines.append(
        f'{{"type":"ATTR","ticket":{t},"id":"{aid}"}}'
        f'||{{"x":null,"y":null,"rotation":null,"color":null,'
        f'"fontFamily":null,"fontSize":null,"fontWeight":null,'
        f'"italic":null,"underline":null,"align":null,'
        f'"value":"{dev_uuid}","keyVisible":null,"valueVisible":null,'
        f'"key":"Device","fillColor":null,'
        f'"parentId":"{comp_id}","zIndex":12}}|'
    )
    t += 1

    # Relevance ATTR
    aid = rand_id()
    lines.append(
        f'{{"type":"ATTR","ticket":{t},"id":"{aid}"}}'
        f'||{{"x":null,"y":null,"rotation":null,"color":null,'
        f'"fontFamily":null,"fontSize":null,"fontWeight":null,'
        f'"italic":null,"underline":null,"align":null,'
        f'"value":"[]","keyVisible":null,"valueVisible":null,'
        f'"key":"Relevance","fillColor":null,'
        f'"parentId":"{comp_id}","zIndex":0}}|'
    )
    t += 1

    # Name ATTR
    aid = rand_id()
    name_x = x - 20 if rotation == 90 else x + 20
    lines.append(
        f'{{"type":"ATTR","ticket":{t},"id":"{aid}"}}'
        f'||{{"x":{name_x},"y":{y},"rotation":0,'
        f'"color":null,"fontFamily":null,"fontSize":null,'
        f'"fontWeight":null,"italic":null,"underline":null,'
        f'"align":"CENTER_MIDDLE","value":"{net_name}",'
        f'"keyVisible":null,"valueVisible":null,'
        f'"key":"Name","fillColor":null,'
        f'"parentId":"{comp_id}","zIndex":9}}|'
    )
    t += 1

    # Global Net Name ATTR
    aid = rand_id()
    gnx = x - 10 if rotation == 90 else x + 10
    lines.append(
        f'{{"type":"ATTR","ticket":{t},"id":"{aid}"}}'
        f'||{{"x":{gnx},"y":{y},"rotation":{rotation},'
        f'"color":null,"fontFamily":null,"fontSize":null,'
        f'"fontWeight":null,"italic":null,"underline":null,'
        f'"align":"CENTER_BOTTOM","value":"{net_name}",'
        f'"keyVisible":null,"valueVisible":null,'
        f'"key":"Global Net Name","fillColor":null,'
        f'"parentId":"{comp_id}","zIndex":11}}|'
    )
    t += 1

    return lines, t, z, comp_id


def main():
    parser = argparse.ArgumentParser(description="Generate wires for EasyEDA Pro schematic")
    parser.add_argument("file", help="Path to .epro2 file")
    parser.add_argument("--netlist", help="JSON netlist file defining connections")
    parser.add_argument("--dry-run", action="store_true", help="Preview pin map only")
    parser.add_argument("--output", "-o", help="Output file for generated lines")
    args = parser.parse_args()

    components, wires, symbols = load_epro2(args.file)
    max_ticket = get_max_ticket(args.file)

    # Build pin position lookup: designator.pin_name -> (x, y)
    pin_map = {}
    for c in components:
        if c.part_id == "pid8a0e77bacb214e":
            continue
        if c.symbol_uuid not in symbols:
            continue
        for pin in symbols[c.symbol_uuid].pins:
            ax, ay = pin_abs_position(c, pin)
            if pin.name:
                pin_map[f"{c.designator}.{pin.name}"] = (ax, ay)
            if pin.number:
                pin_map[f"{c.designator}.#{pin.number}"] = (ax, ay)

    if args.dry_run:
        print("Pin position map:")
        print("=" * 50)
        for k, v in sorted(pin_map.items()):
            print(f"  {k:<25} ({v[0]:>6.0f}, {v[1]:>6.0f})")
        print(f"\nMax ticket: {max_ticket}")
        return

    if not args.netlist:
        print("No --netlist specified. Use --dry-run to see pin map.")
        print("\nNetlist JSON format:")
        print(json.dumps({
            "wires": [
                {"from": "U1.D+", "to": "J1.DP1", "net": "USB_DP"},
                {"from": "U3.GND", "to_power": "GND"},
            ]
        }, indent=2))
        return

    with open(args.netlist) as f:
        netlist = json.load(f)

    ticket = max_ticket + 1
    z = 200
    all_lines = []

    for conn in netlist.get("wires", []):
        from_key = conn["from"]
        net = conn.get("net", "")

        if from_key not in pin_map:
            print(f"WARNING: pin '{from_key}' not found in pin map", file=sys.stderr)
            continue

        fx, fy = pin_map[from_key]

        if "to" in conn:
            to_key = conn["to"]
            if to_key not in pin_map:
                print(f"WARNING: pin '{to_key}' not found in pin map", file=sys.stderr)
                continue
            tx, ty = pin_map[to_key]
            new_lines, ticket, z = make_wire_lines(fx, fy, tx, ty, net, ticket, z)
            all_lines.extend(new_lines)

        elif "to_power" in conn:
            power_net = conn["to_power"]
            # NOTE: You must provide project-specific sym_uuid and dev_uuid
            # Extract these from the existing epru file's SYMBOL/DEVICE sections
            print(f"WARNING: power symbol generation requires project-specific UUIDs", file=sys.stderr)

    output = "\n".join(all_lines)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output + "\n")
        print(f"Written {len(all_lines)} lines to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
