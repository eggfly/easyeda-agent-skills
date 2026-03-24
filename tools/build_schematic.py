#!/usr/bin/env python3
"""
EasyEDA Pro schematic builder framework.

Provides the EasyEDAWriter class for programmatically adding wires, power
symbols, and components to an existing .epro2 file.

Usage:
    # As a library:
    from build_schematic import EasyEDAWriter, inject_lines

    w = EasyEDAWriter(start_ticket=500, start_z=200)
    w.add_wire(100, -200, 150, -200, "SDA")
    w.add_power(100, -300, "GND", sym_uuid="...", dev_uuid="...")
    inject_lines("input.epro2", "output.epro2", w.lines)

    # As a CLI (dry-run to preview generated lines):
    python3 build_schematic.py input.epro2 -o output.epro2 --dry-run
"""

import json
import sys
import zipfile
import secrets
import argparse
from parse_epro2 import load_epro2, get_max_ticket, pin_abs_position


def rand_id():
    return secrets.token_hex(8)


class EasyEDAWriter:
    """Generates EasyEDA Pro source code lines."""

    def __init__(self, start_ticket, start_z):
        self.ticket = start_ticket
        self.z = start_z
        self.lines = []

    def _t(self):
        t = self.ticket; self.ticket += 1; return t

    def _z(self):
        z = self.z; self.z += 1; return z

    def add_wire(self, x1, y1, x2, y2, net_name=""):
        """Single-segment wire with optional net label."""
        wid = rand_id()
        z = self._z()
        self.lines.append(f'{{"type":"WIRE","ticket":{self._t()},"id":"{wid}"}}||{{"zIndex":{z}}}|')
        self.lines.append(
            f'{{"type":"LINE","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"fillColor":null,"fillStyle":null,"strokeColor":null,"strokeStyle":null,"strokeWidth":null,'
            f'"startX":{x1},"startY":{y1},"endX":{x2},"endY":{y2},"lineGroup":"{wid}"}}|')
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"[]",'
            f'"keyVisible":null,"valueVisible":null,"key":"Relevance","fillColor":null,'
            f'"parentId":"{wid}","zIndex":0}}|')
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{x1},"y":{y1},"rotation":0,"color":null,"fontFamily":null,"fontSize":8,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"{net_name}",'
            f'"keyVisible":false,"valueVisible":true,"key":"NET","fillColor":null,'
            f'"parentId":"{wid}","zIndex":2}}|')

    def add_multi_wire(self, segments, net_name=""):
        """Multi-segment wire (all segments share one WIRE group)."""
        if not segments:
            return
        wid = rand_id()
        z = self._z()
        self.lines.append(f'{{"type":"WIRE","ticket":{self._t()},"id":"{wid}"}}||{{"zIndex":{z}}}|')
        for (x1, y1, x2, y2) in segments:
            self.lines.append(
                f'{{"type":"LINE","ticket":{self._t()},"id":"{rand_id()}"}}'
                f'||{{"fillColor":null,"fillStyle":null,"strokeColor":null,"strokeStyle":null,"strokeWidth":null,'
                f'"startX":{x1},"startY":{y1},"endX":{x2},"endY":{y2},"lineGroup":"{wid}"}}|')
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"[]",'
            f'"keyVisible":null,"valueVisible":null,"key":"Relevance","fillColor":null,'
            f'"parentId":"{wid}","zIndex":0}}|')
        x1, y1 = segments[0][0], segments[0][1]
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{x1},"y":{y1},"rotation":0,"color":null,"fontFamily":null,"fontSize":8,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"{net_name}",'
            f'"keyVisible":false,"valueVisible":true,"key":"NET","fillColor":null,'
            f'"parentId":"{wid}","zIndex":2}}|')

    def add_power(self, x, y, net_name, sym_uuid, dev_uuid, rotation=None):
        """Add power symbol. Returns component ID.

        Args:
            sym_uuid: Symbol UUID from project's SYMBOL section
            dev_uuid: Device UUID from project's DEVICE section
        """
        comp_id = rand_id()
        z = self._z()
        if rotation is None:
            rotation = 270 if net_name == "GND" else 90

        self.lines.append(
            f'{{"type":"COMPONENT","ticket":{self._t()},"id":"{comp_id}"}}'
            f'||{{"partId":"pid8a0e77bacb214e","x":{x},"y":{y},'
            f'"rotation":{rotation},"isMirror":false,"attrs":{{}},"zIndex":{z}}}|')

        # Symbol attr
        if rotation == 90: sx, sy = x+30, y
        elif rotation == 270: sx, sy = x-30, y
        else: sx, sy = x, y-30
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{sx},"y":{sy},"rotation":{rotation},"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"{sym_uuid}",'
            f'"keyVisible":null,"valueVisible":null,"key":"Symbol","fillColor":null,'
            f'"parentId":"{comp_id}","zIndex":1,"locked":false}}|')
        # Device attr
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"{dev_uuid}",'
            f'"keyVisible":null,"valueVisible":null,"key":"Device","fillColor":null,'
            f'"parentId":"{comp_id}","zIndex":12}}|')
        # Relevance
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"[]",'
            f'"keyVisible":null,"valueVisible":null,"key":"Relevance","fillColor":null,'
            f'"parentId":"{comp_id}","zIndex":0}}|')
        # Name
        nx = x-20 if rotation==90 else (x+20 if rotation==270 else x)
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{nx},"y":{y},"rotation":0,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":"CENTER_MIDDLE",'
            f'"value":"{net_name}","keyVisible":null,"valueVisible":true,"key":"Name",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":3,"locked":false}}|')
        # Global Net Name
        gnx = x-10 if rotation==90 else (x+5 if rotation==270 else x)
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{gnx},"y":{y},"rotation":{rotation},"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":"CENTER_MIDDLE",'
            f'"value":"{net_name}","keyVisible":null,"valueVisible":null,"key":"Global Net Name",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":17}}|')
        return comp_id

    def add_component(self, x, y, part_id, designator, symbol_uuid, device_uuid,
                      rotation=0, mirror=False, show_value=False, value=None):
        """Add a new component. Returns component ID."""
        comp_id = rand_id()
        z = self._z()
        m = "true" if mirror else "false"
        self.lines.append(
            f'{{"type":"COMPONENT","ticket":{self._t()},"id":"{comp_id}"}}'
            f'||{{"partId":"{part_id}","x":{x},"y":{y},'
            f'"rotation":{rotation},"isMirror":{m},"attrs":{{}},"zIndex":{z}}}|')
        # Symbol
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":0,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":false,"italic":false,"underline":false,"align":"LEFT_BOTTOM",'
            f'"value":"{symbol_uuid}","keyVisible":null,"valueVisible":null,"key":"Symbol",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":1,"locked":false}}|')
        # Device
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
            f'"value":"{device_uuid}","keyVisible":null,"valueVisible":null,"key":"Device",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":12}}|')
        # Unique ID
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
            f'"value":"","keyVisible":null,"valueVisible":null,"key":"Unique ID",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":-2}}|')
        # Designator
        dx, dy = x - 10, y - 20
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{dx},"y":{dy},"rotation":0,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":false,"italic":false,"underline":false,"align":"LEFT_BOTTOM",'
            f'"value":"{designator}","keyVisible":null,"valueVisible":true,"key":"Designator",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":2,"locked":false}}|')
        # Footprint
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
            f'"value":null,"keyVisible":null,"valueVisible":null,"key":"Footprint",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":21}}|')
        # Value
        if value is not None:
            vx, vy = x - 10, y + 15
            vis = "true" if show_value else "null"
            self.lines.append(
                f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
                f'||{{"x":{vx},"y":{vy},"rotation":0,"color":null,"fontFamily":null,"fontSize":null,'
                f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
                f'"value":"{value}","keyVisible":null,"valueVisible":{vis},"key":"Value",'
                f'"fillColor":null,"parentId":"{comp_id}","zIndex":26}}|')
        # Name, Reuse Block, Group ID, Channel ID
        for k in ["Name", "Reuse Block", "Group ID", "Channel ID"]:
            self.lines.append(
                f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
                f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
                f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
                f'"value":null,"keyVisible":null,"valueVisible":null,"key":"{k}",'
                f'"fillColor":null,"parentId":"{comp_id}","zIndex":32}}|')
        return comp_id


def inject_lines(input_epro2, output_epro2, new_lines):
    """Inject generated lines into an epro2 file (before BLOB section)."""
    with zipfile.ZipFile(input_epro2, "r") as zf:
        epru_names = [n for n in zf.namelist() if n.endswith(".epru")]
        with zf.open(epru_names[0]) as f:
            epru_content = f.read().decode("utf-8")

    epru_lines = epru_content.split("\n")
    blob_line = None
    for i, line in enumerate(epru_lines):
        if '"docType":"BLOB"' in line:
            blob_line = i
            break

    if blob_line is not None:
        final_lines = epru_lines[:blob_line] + new_lines + epru_lines[blob_line:]
    else:
        final_lines = epru_lines + new_lines

    new_epru = "\n".join(final_lines)

    with zipfile.ZipFile(input_epro2, "r") as zf_in:
        with zipfile.ZipFile(output_epro2, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.namelist():
                if item.endswith(".epru"):
                    zf_out.writestr(item, new_epru)
                else:
                    zf_out.writestr(item, zf_in.read(item))

    print(f"Written to {output_epro2}")


def main():
    parser = argparse.ArgumentParser(description="Build EasyEDA Pro schematic")
    parser.add_argument("file", help="Input .epro2 file")
    parser.add_argument("-o", "--output", required=True, help="Output .epro2 file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    components, wires, symbols = load_epro2(args.file)
    max_ticket = get_max_ticket(args.file)

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

    w = EasyEDAWriter(start_ticket=max_ticket + 1, start_z=200)

    # --- Add your wiring logic here ---
    # Example:
    # w.add_wire(100, -200, 150, -200, "SDA")
    # w.add_power(100, -300, "GND", sym_uuid="...", dev_uuid="...")
    print("No wiring logic defined. Add your connections in the script or use gen_wires.py with a netlist.")

    new_lines = w.lines
    print(f"Generated {len(new_lines)} new lines (ticket {max_ticket+1} -> {w.ticket-1})")

    if args.dry_run:
        for line in new_lines:
            print(line)
        return

    if new_lines:
        inject_lines(args.file, args.output, new_lines)


if __name__ == "__main__":
    main()
