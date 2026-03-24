#!/usr/bin/env python3
"""
EasyEDA Pro (.epro2) parser.

Extracts component placements, pin coordinates, wires, and net labels
from an EasyEDA Pro schematic file.

Usage:
    python3 parse_epro2.py <file.epro2>
    python3 parse_epro2.py <file.epro2> --pins          # Show all pin coordinates
    python3 parse_epro2.py <file.epro2> --wires         # Show existing wires
    python3 parse_epro2.py <file.epro2> --json          # Output JSON for scripting
    python3 parse_epro2.py <file.epro2> --netlist       # Generate netlist (pin-to-wire mapping)
"""

import json
import sys
import os
import zipfile
import tempfile
import argparse
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Pin:
    number: str
    name: str
    pin_type: str
    rel_x: float  # relative to symbol origin
    rel_y: float
    rotation: int  # 0=left, 90=bottom, 180=right, 270=top


@dataclass
class Symbol:
    uuid: str
    pins: list  # list of Pin


@dataclass
class Component:
    comp_id: str
    part_id: str
    designator: str
    x: float
    y: float
    rotation: int
    mirror: bool
    symbol_uuid: str
    device_uuid: str
    name: str  # for power symbols
    global_net: str  # for power symbols


@dataclass
class WireLine:
    start_x: float
    start_y: float
    end_x: float
    end_y: float


@dataclass
class Wire:
    wire_id: str
    lines: list  # list of WireLine
    net_name: str


def parse_line(line: str):
    """Parse a single epru line into (header_dict, body_dict)."""
    line = line.strip()
    if not line:
        return None, None
    parts = line.split("||")
    if len(parts) < 2:
        return None, None
    try:
        header = json.loads(parts[0])
        body_str = parts[1].rstrip("|")
        body = json.loads(body_str) if body_str else {}
        return header, body
    except (json.JSONDecodeError, IndexError):
        return None, None


def find_sections(lines):
    """Find all DOCHEAD section boundaries."""
    sections = []
    for i, line in enumerate(lines):
        h, b = parse_line(line)
        if h and h.get("type") == "DOCHEAD" and b:
            sections.append({
                "line": i,
                "docType": b.get("docType", ""),
                "uuid": b.get("uuid", ""),
            })
    return sections


def parse_symbols(lines, sections):
    """Extract all SYMBOL sections with their pins."""
    symbols = {}
    sym_sections = [s for s in sections if s["docType"] == "SYMBOL"]

    for idx, sec in enumerate(sym_sections):
        start = sec["line"]
        # find next section start
        all_starts = sorted([s["line"] for s in sections])
        my_pos = all_starts.index(start)
        end = all_starts[my_pos + 1] if my_pos + 1 < len(all_starts) else len(lines)

        pins = []
        current_pin = None

        for i in range(start, end):
            h, b = parse_line(lines[i])
            if not h:
                continue

            if h["type"] == "PIN":
                if current_pin:
                    pins.append(current_pin)
                current_pin = Pin(
                    number="", name="", pin_type="",
                    rel_x=b.get("x", 0), rel_y=b.get("y", 0),
                    rotation=b.get("rotation", 0),
                )
            elif h["type"] == "ATTR" and current_pin:
                key = b.get("key", "")
                val = b.get("value", "") or ""
                if key == "Pin Name":
                    current_pin.name = val
                elif key == "Pin Number":
                    current_pin.number = val
                elif key == "Pin Type":
                    current_pin.pin_type = val

        if current_pin:
            pins.append(current_pin)

        if pins:
            symbols[sec["uuid"]] = Symbol(uuid=sec["uuid"], pins=pins)

    return symbols


def parse_sch_page(lines, sections):
    """Extract components and wires from SCH_PAGE section."""
    sch_sections = [s for s in sections if s["docType"] == "SCH_PAGE"]
    if not sch_sections:
        return [], []

    start = sch_sections[0]["line"]
    all_starts = sorted([s["line"] for s in sections])
    my_pos = all_starts.index(start)
    end = all_starts[my_pos + 1] if my_pos + 1 < len(all_starts) else len(lines)

    # Parse components
    components = {}
    for i in range(start, end):
        h, b = parse_line(lines[i])
        if not h:
            continue

        if h["type"] == "COMPONENT":
            cid = h["id"]
            components[cid] = Component(
                comp_id=cid,
                part_id=b.get("partId", ""),
                designator="", x=b.get("x", 0), y=b.get("y", 0),
                rotation=b.get("rotation", 0),
                mirror=b.get("isMirror", False),
                symbol_uuid="", device_uuid="",
                name="", global_net="",
            )
        elif h["type"] == "ATTR":
            pid = b.get("parentId", "")
            if pid in components:
                key = b.get("key", "")
                val = b.get("value", "") or ""
                if key == "Designator":
                    components[pid].designator = val
                elif key == "Symbol":
                    components[pid].symbol_uuid = val
                elif key == "Device":
                    components[pid].device_uuid = val
                elif key == "Name":
                    components[pid].name = val
                elif key == "Global Net Name":
                    components[pid].global_net = val

    # Parse wires
    wires = {}
    for i in range(start, end):
        h, b = parse_line(lines[i])
        if not h:
            continue

        if h["type"] == "WIRE":
            wid = h["id"]
            wires[wid] = Wire(wire_id=wid, lines=[], net_name="")
        elif h["type"] == "LINE":
            lg = b.get("lineGroup", "")
            if lg in wires:
                wires[lg].lines.append(WireLine(
                    start_x=b.get("startX", 0), start_y=b.get("startY", 0),
                    end_x=b.get("endX", 0), end_y=b.get("endY", 0),
                ))
        elif h["type"] == "ATTR":
            pid = b.get("parentId", "")
            if pid in wires and b.get("key") == "NET":
                wires[pid].net_name = b.get("value", "") or ""

    return list(components.values()), list(wires.values())


def pin_abs_position(comp: Component, pin: Pin):
    """Calculate absolute pin position on schematic."""
    cx, cy = comp.x, comp.y
    px, py = pin.rel_x, pin.rel_y
    rot = comp.rotation

    if rot == 0:
        return cx + px, cy + py
    elif rot == 90:
        return cx - py, cy + px
    elif rot == 180:
        return cx - px, cy - py
    elif rot == 270:
        return cx + py, cy - px
    return cx + px, cy + py


def load_epro2(filepath):
    """Load and parse an .epro2 file. Returns (components, wires, symbols)."""
    with zipfile.ZipFile(filepath, "r") as zf:
        epru_names = [n for n in zf.namelist() if n.endswith(".epru")]
        if not epru_names:
            raise ValueError("No .epru file found in archive")
        with zf.open(epru_names[0]) as f:
            lines = f.read().decode("utf-8").splitlines()

    sections = find_sections(lines)
    symbols = parse_symbols(lines, sections)
    components, wires = parse_sch_page(lines, sections)

    return components, wires, symbols


def get_max_ticket(filepath):
    """Get the maximum ticket number from the epru file."""
    with zipfile.ZipFile(filepath, "r") as zf:
        epru_names = [n for n in zf.namelist() if n.endswith(".epru")]
        with zf.open(epru_names[0]) as f:
            lines = f.read().decode("utf-8").splitlines()

    max_ticket = 0
    for line in lines:
        h, _ = parse_line(line)
        if h and "ticket" in h:
            max_ticket = max(max_ticket, h["ticket"])
    return max_ticket


def print_components(components, symbols):
    """Print component summary table."""
    print(f"\n{'Designator':<10} {'Part ID':<30} {'Position':<16} {'Rot':<5} {'Pins'}")
    print("-" * 80)
    for c in sorted(components, key=lambda x: x.designator or "zzz"):
        if c.part_id == "pid8a0e77bacb214e":
            continue  # skip power symbols / title block
        npins = len(symbols[c.symbol_uuid].pins) if c.symbol_uuid in symbols else "?"
        print(f"{c.designator:<10} {c.part_id:<30} ({c.x:>6},{c.y:>6})  {c.rotation:<5} {npins}")


def print_pins(components, symbols):
    """Print all pin absolute coordinates per component."""
    for c in sorted(components, key=lambda x: x.designator or "zzz"):
        if c.part_id == "pid8a0e77bacb214e":
            continue
        if c.symbol_uuid not in symbols:
            continue

        sym = symbols[c.symbol_uuid]
        print(f"\n{'='*60}")
        print(f"{c.designator} ({c.part_id})")
        print(f"  Position: ({c.x}, {c.y})  Rotation: {c.rotation}")
        print(f"  {'Pin#':<8} {'Name':<14} {'AbsX':<8} {'AbsY':<8}")
        print(f"  {'-'*44}")

        for pin in sym.pins:
            ax, ay = pin_abs_position(c, pin)
            print(f"  {pin.number:<8} {pin.name:<14} {ax:<8.0f} {ay:<8.0f}")


def print_wires(wires):
    """Print all wires with their net names."""
    print(f"\n{'Wire ID':<20} {'Net Name':<16} {'Segments'}")
    print("-" * 60)
    for w in wires:
        segs = "; ".join(
            f"({l.start_x},{l.start_y})->({l.end_x},{l.end_y})"
            for l in w.lines
        )
        net = w.net_name or "(unnamed)"
        print(f"{w.wire_id[:18]:<20} {net:<16} {segs}")


def print_power_symbols(components):
    """Print power symbol placements."""
    print(f"\n{'Net':<8} {'Position':<16} {'Rot':<5} {'ID'}")
    print("-" * 50)
    for c in components:
        if c.part_id == "pid8a0e77bacb214e" and c.name:
            print(f"{c.name:<8} ({c.x:>6},{c.y:>6})  {c.rotation:<5} {c.comp_id[:16]}")


def print_netlist(components, wires, symbols):
    """Generate a simple netlist: for each wire endpoint, find the nearest pin."""
    # Collect all pin positions
    all_pins = []
    for c in components:
        if c.part_id == "pid8a0e77bacb214e":
            # Power symbol - treat as a single-pin component
            if c.name:
                all_pins.append({
                    "designator": c.name,
                    "pin": "1",
                    "x": c.x, "y": c.y,
                    "net": c.global_net or c.name,
                })
            continue
        if c.symbol_uuid not in symbols:
            continue
        for pin in symbols[c.symbol_uuid].pins:
            ax, ay = pin_abs_position(c, pin)
            all_pins.append({
                "designator": c.designator,
                "pin": pin.number,
                "pin_name": pin.name,
                "x": ax, "y": ay,
            })

    # Collect all wire endpoints
    wire_points = {}  # (x,y) -> set of wire_ids
    for w in wires:
        for l in w.lines:
            wire_points.setdefault((l.start_x, l.start_y), set()).add(w.wire_id)
            wire_points.setdefault((l.end_x, l.end_y), set()).add(w.wire_id)

    # Match pins to wire endpoints (exact coordinate match)
    connections = {}  # wire_id -> list of (designator, pin#, pin_name)
    for p in all_pins:
        key = (p["x"], p["y"])
        if key in wire_points:
            for wid in wire_points[key]:
                connections.setdefault(wid, []).append(p)

    print("\nConnected Nets:")
    print("=" * 60)
    for w in wires:
        net = w.net_name or "(unnamed)"
        pins = connections.get(w.wire_id, [])
        if pins:
            pin_strs = [
                f"{p['designator']}.{p.get('pin','?')}({p.get('pin_name','')})"
                for p in pins
            ]
            print(f"  {net:<16} : {', '.join(pin_strs)}")


def output_json(components, wires, symbols):
    """Output everything as JSON."""
    result = {
        "components": [],
        "power_symbols": [],
        "wires": [],
    }

    for c in sorted(components, key=lambda x: x.designator or "zzz"):
        if c.part_id == "pid8a0e77bacb214e":
            if c.name:
                result["power_symbols"].append({
                    "name": c.name,
                    "global_net": c.global_net,
                    "x": c.x, "y": c.y,
                    "rotation": c.rotation,
                    "id": c.comp_id,
                })
            continue

        comp_data = {
            "designator": c.designator,
            "part_id": c.part_id,
            "x": c.x, "y": c.y,
            "rotation": c.rotation,
            "pins": [],
        }
        if c.symbol_uuid in symbols:
            for pin in symbols[c.symbol_uuid].pins:
                ax, ay = pin_abs_position(c, pin)
                comp_data["pins"].append({
                    "number": pin.number,
                    "name": pin.name,
                    "type": pin.pin_type,
                    "abs_x": ax, "abs_y": ay,
                })
        result["components"].append(comp_data)

    for w in wires:
        result["wires"].append({
            "id": w.wire_id,
            "net": w.net_name,
            "lines": [
                {"x1": l.start_x, "y1": l.start_y, "x2": l.end_x, "y2": l.end_y}
                for l in w.lines
            ],
        })

    print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Parse EasyEDA Pro .epro2 files")
    parser.add_argument("file", help="Path to .epro2 file")
    parser.add_argument("--pins", action="store_true", help="Show all pin coordinates")
    parser.add_argument("--wires", action="store_true", help="Show existing wires")
    parser.add_argument("--power", action="store_true", help="Show power symbols")
    parser.add_argument("--netlist", action="store_true", help="Generate netlist")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    components, wires, symbols = load_epro2(args.file)

    if args.json:
        output_json(components, wires, symbols)
        return

    print(f"Parsed: {sum(1 for c in components if c.part_id != 'pid8a0e77bacb214e')} components, "
          f"{sum(1 for c in components if c.part_id == 'pid8a0e77bacb214e' and c.name)} power symbols, "
          f"{len(wires)} wires, "
          f"{len(symbols)} symbols")

    if args.pins:
        print_pins(components, symbols)
    elif args.wires:
        print_wires(wires)
    elif args.power:
        print_power_symbols(components)
    elif args.netlist:
        print_netlist(components, wires, symbols)
    else:
        # Default: show component summary
        print_components(components, symbols)
        print(f"\nPower symbols:")
        print_power_symbols(components)
        print(f"\nWires with net labels:")
        for w in wires:
            if w.net_name:
                segs = [(l.start_x, l.start_y, l.end_x, l.end_y) for l in w.lines]
                print(f"  {w.net_name}: {segs}")


if __name__ == "__main__":
    main()
