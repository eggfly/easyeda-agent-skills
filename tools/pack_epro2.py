#!/usr/bin/env python3
"""
Pack epru content into a valid .epro2 file.

Creates a complete .epro2 ZIP archive containing:
- project2.json (metadata)
- <name>.epru (all schematic data)

Can build from scratch or inject sections into an existing file.

Usage:
    # Create minimal test file
    python3 pack_epro2.py --test -o test.epro2

    # Build from component list
    python3 pack_epro2.py --from-scratch -o my_design.epro2

    # Combine section files into epro2
    python3 pack_epro2.py sections.txt -o output.epro2
"""

import json
import sys
import os
import zipfile
import secrets
import time
import argparse


def rand_id():
    return secrets.token_hex(8)


def now_ms():
    return int(time.time() * 1000)


class Epro2Builder:
    """Builds a complete .epro2 file from scratch."""

    def __init__(self, project_title="MyProject"):
        self.project_title = project_title
        self.lines = []
        self.ticket = 1
        self.sch_uuid = rand_id()
        self.page_uuid = rand_id()

    def _t(self):
        t = self.ticket
        self.ticket += 1
        return t

    def add_raw_lines(self, lines):
        """Add pre-built epru lines (from v6_to_epru or other tools)."""
        for line in lines:
            line = line.strip()
            if line:
                self.lines.append(line)

    def add_sch_section(self):
        """Add the SCH (schematic hierarchy) section."""
        ts = now_ms()
        client = rand_id()

        self.lines.append(
            f'{{"type":"DOCHEAD","ticket":{self._t()}}}'
            f'||{{"docType":"SCH","client":"{client}",'
            f'"uuid":"{self.sch_uuid}","updateTime":{ts},'
            f'"version":"{ts}"}}'
            f'|'
        )
        self.lines.append(
            f'{{"type":"META","ticket":{self._t()},"id":"META"}}'
            f'||{{"title":"Schematic1","source":"","board":"","zIndex":null}}'
            f'|'
        )

    def add_sch_page_section(self, components_and_wires=None):
        """Add the SCH_PAGE section with optional content.

        Args:
            components_and_wires: list of pre-built epru lines for
                                  COMPONENT/ATTR/WIRE/LINE records
        """
        ts = now_ms()
        client = rand_id()

        # DOCHEAD
        self.lines.append(
            f'{{"type":"DOCHEAD","ticket":{self._t()}}}'
            f'||{{"docType":"SCH_PAGE","client":"{client}",'
            f'"uuid":"{self.page_uuid}","updateTime":{ts},'
            f'"version":"{ts}"}}'
            f'|'
        )

        # META - links to parent SCH
        self.lines.append(
            f'{{"type":"META","ticket":{self._t()},"id":"META"}}'
            f'||{{"title":"{self.project_title}",'
            f'"schematic":"{self.sch_uuid}","source":"","zIndex":1}}'
            f'|'
        )

        # Add components and wires if provided
        if components_and_wires:
            for line in components_and_wires:
                line = line.strip()
                if line:
                    self.lines.append(line)

    def add_blob_section(self):
        """Add the BLOB section (required, can be minimal)."""
        ts = now_ms()
        client = rand_id()

        self.lines.append(
            f'{{"type":"DOCHEAD","ticket":{self._t()}}}'
            f'||{{"docType":"BLOB","client":"{client}",'
            f'"uuid":"BLOB","updateTime":{ts},'
            f'"version":"{ts}"}}'
            f'|'
        )

    def build_epru(self):
        """Return the complete epru content as a string."""
        return "\n".join(self.lines)

    def build_project_json(self):
        """Return project2.json content."""
        return json.dumps({
            "title": self.project_title,
            "cbb_project": False,
            "editorVersion": "",
            "introduction": "",
            "description": "",
            "tags": "[]"
        }, indent=2)

    def write_epro2(self, output_path):
        """Write the complete .epro2 ZIP file."""
        epru_content = self.build_epru()
        project_json = self.build_project_json()
        epru_filename = f"{self.project_title}.epru"

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project2.json", project_json)
            zf.writestr(epru_filename, epru_content)

        return output_path


class SchematicBuilder:
    """High-level builder that combines v6_to_epru + pack_epro2.

    Handles ticket numbering across all sections.
    """

    def __init__(self, project_title="MyProject"):
        self.project_title = project_title
        self.device_lines = []      # DEVICE sections
        self.symbol_lines = []      # SYMBOL sections
        self.footprint_lines = []   # FOOTPRINT sections (future)
        self.sch_content_lines = [] # COMPONENT/WIRE/ATTR in SCH_PAGE
        self.components = {}        # part_id -> {device_uuid, symbol_uuid, ...}
        self.ticket = 1
        self.z_index = 1

    def _t(self):
        t = self.ticket
        self.ticket += 1
        return t

    def _z(self):
        z = self.z_index
        self.z_index += 1
        return z

    def add_component_from_lcsc(self, lcsc_code):
        """Fetch and add a component from LCSC.

        Returns: part_id string, or None on failure.
        """
        from v6_to_epru import convert_component
        result = convert_component(lcsc_code, ticket_start=self.ticket)
        if not result:
            return None

        # All lines go in order: SYMBOL + FOOTPRINT + DEVICE
        # (convert_component generates them in this order now)
        self.symbol_lines.extend(result["lines"])
        self.ticket = result["next_ticket"]

        self.components[result["part_id"]] = {
            "device_uuid": result["device_uuid"],
            "symbol_uuid": result["symbol_uuid"],
            "footprint_uuid": result.get("footprint_uuid"),
            "lcsc_code": lcsc_code,
            "title": result["title"],
            "package": result.get("package", ""),
        }
        return result["part_id"]

    def add_power_symbols(self):
        """Add GND and VCC power symbol DEVICE+SYMBOL sections.

        Returns: dict with {gnd_sym, gnd_dev, vcc_sym, vcc_dev} UUIDs.
        """
        from v6_to_epru import EpruSectionWriter
        writer = EpruSectionWriter(start_ticket=self.ticket)

        gnd_sym, gnd_dev = writer.write_power_symbol_section("GND")
        vcc_sym, vcc_dev = writer.write_power_symbol_section("VCC")

        self.ticket = writer.ticket
        # Split into device + symbol lines
        self.device_lines.extend(writer.lines)

        return {
            "gnd_sym": gnd_sym, "gnd_dev": gnd_dev,
            "vcc_sym": vcc_sym, "vcc_dev": vcc_dev,
        }

    def place_component(self, part_id, x, y, designator, rotation=0, mirror=False):
        """Place a component instance on the schematic page."""
        info = self.components.get(part_id)
        if not info:
            raise ValueError(f"Unknown part_id: {part_id}")

        comp_id = rand_id()
        z = self._z()
        m = "true" if mirror else "false"

        # COMPONENT
        self.sch_content_lines.append(
            f'{{"type":"COMPONENT","ticket":{self._t()},"id":"{comp_id}"}}'
            f'||{{"partId":"{part_id}","x":{x},"y":{y},'
            f'"rotation":{rotation},"isMirror":{m},"attrs":{{}},"zIndex":{z}}}|'
        )

        # Symbol ATTR
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":0,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":false,"italic":false,"underline":false,"align":"LEFT_BOTTOM",'
            f'"value":"{info["symbol_uuid"]}","keyVisible":null,"valueVisible":null,"key":"Symbol",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":1,"locked":false}}|'
        )

        # Device ATTR
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
            f'"value":"{info["device_uuid"]}","keyVisible":null,"valueVisible":null,"key":"Device",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":12}}|'
        )

        # Designator ATTR
        dx, dy = x - 10, y - 20
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{dx},"y":{dy},"rotation":0,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":false,"italic":false,"underline":false,"align":"LEFT_BOTTOM",'
            f'"value":"{designator}","keyVisible":null,"valueVisible":true,"key":"Designator",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":2,"locked":false}}|'
        )

        # Unique ID
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
            f'"value":"","keyVisible":null,"valueVisible":null,"key":"Unique ID",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":-2}}|'
        )

        # Footprint
        fp_uuid = info.get("footprint_uuid")
        fp_val = f'"{fp_uuid}"' if fp_uuid else "null"
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
            f'"value":{fp_val},"keyVisible":null,"valueVisible":null,"key":"Footprint",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":21}}|'
        )

        # Name, Reuse Block, Group ID, Channel ID
        for k in ["Name", "Reuse Block", "Group ID", "Channel ID"]:
            self.sch_content_lines.append(
                f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
                f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
                f'"fontWeight":null,"italic":null,"underline":null,"align":null,'
                f'"value":null,"keyVisible":null,"valueVisible":null,"key":"{k}",'
                f'"fillColor":null,"parentId":"{comp_id}","zIndex":32}}|'
            )

        return comp_id

    def place_power(self, x, y, net_name, power_uuids, rotation=None):
        """Place a power symbol (GND, VCC, 3V3, +5V)."""
        comp_id = rand_id()
        z = self._z()

        if net_name == "GND":
            sym_uuid = power_uuids["gnd_sym"]
            dev_uuid = power_uuids["gnd_dev"]
            if rotation is None:
                rotation = 270
        else:
            sym_uuid = power_uuids["vcc_sym"]
            dev_uuid = power_uuids["vcc_dev"]
            if rotation is None:
                rotation = 90

        self.sch_content_lines.append(
            f'{{"type":"COMPONENT","ticket":{self._t()},"id":"{comp_id}"}}'
            f'||{{"partId":"pid8a0e77bacb214e","x":{x},"y":{y},'
            f'"rotation":{rotation},"isMirror":false,"attrs":{{}},"zIndex":{z}}}|'
        )

        # Symbol ATTR
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":{rotation},"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"{sym_uuid}",'
            f'"keyVisible":null,"valueVisible":null,"key":"Symbol","fillColor":null,'
            f'"parentId":"{comp_id}","zIndex":1,"locked":false}}|'
        )

        # Device ATTR
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"{dev_uuid}",'
            f'"keyVisible":null,"valueVisible":null,"key":"Device","fillColor":null,'
            f'"parentId":"{comp_id}","zIndex":12}}|'
        )

        # Relevance
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"[]",'
            f'"keyVisible":null,"valueVisible":null,"key":"Relevance","fillColor":null,'
            f'"parentId":"{comp_id}","zIndex":0}}|'
        )

        # Name
        nx = x - 20 if rotation == 90 else (x + 20 if rotation == 270 else x)
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{nx},"y":{y},"rotation":0,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":"CENTER_MIDDLE",'
            f'"value":"{net_name}","keyVisible":null,"valueVisible":true,"key":"Name",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":3,"locked":false}}|'
        )

        # Global Net Name
        gnx = x - 10 if rotation == 90 else (x + 5 if rotation == 270 else x)
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{gnx},"y":{y},"rotation":{rotation},"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":"CENTER_MIDDLE",'
            f'"value":"{net_name}","keyVisible":null,"valueVisible":null,"key":"Global Net Name",'
            f'"fillColor":null,"parentId":"{comp_id}","zIndex":17}}|'
        )

        return comp_id

    def add_wire(self, x1, y1, x2, y2, net_name=""):
        """Add a wire with optional net label."""
        wid = rand_id()
        z = self._z()

        self.sch_content_lines.append(
            f'{{"type":"WIRE","ticket":{self._t()},"id":"{wid}"}}'
            f'||{{"zIndex":{z}}}|'
        )
        self.sch_content_lines.append(
            f'{{"type":"LINE","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"fillColor":null,"fillStyle":null,"strokeColor":null,"strokeStyle":null,"strokeWidth":null,'
            f'"startX":{x1},"startY":{y1},"endX":{x2},"endY":{y2},"lineGroup":"{wid}"}}|'
        )
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"[]",'
            f'"keyVisible":null,"valueVisible":null,"key":"Relevance","fillColor":null,'
            f'"parentId":"{wid}","zIndex":0}}|'
        )
        self.sch_content_lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"{rand_id()}"}}'
            f'||{{"x":{x1},"y":{y1},"rotation":0,"color":null,"fontFamily":null,"fontSize":8,'
            f'"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"{net_name}",'
            f'"keyVisible":false,"valueVisible":true,"key":"NET","fillColor":null,'
            f'"parentId":"{wid}","zIndex":2}}|'
        )

    def build(self, output_path):
        """Assemble and write the final .epro2 file."""
        builder = Epro2Builder(self.project_title)

        # 1. SYMBOL + FOOTPRINT + DEVICE sections (from LCSC components)
        builder.add_raw_lines(self.symbol_lines)

        # 2. Power symbol DEVICE+SYMBOL sections
        builder.add_raw_lines(self.device_lines)

        # 3. Extra footprint sections
        builder.add_raw_lines(self.footprint_lines)

        # 4. SCH section
        builder.add_sch_section()

        # 5. SCH_PAGE section with content
        builder.add_sch_page_section(self.sch_content_lines)

        # 6. BLOB section
        builder.add_blob_section()

        builder.write_epro2(output_path)
        return output_path


def build_test_schematic(output_path):
    """Build a test schematic with TP4054 charger + basic wiring.

    Fetches real component data from LCSC and generates a valid .epro2.
    """
    print("Building test schematic from scratch...")
    sb = SchematicBuilder(project_title="TestDesign")

    # 1. Add TP4054 from LCSC
    print("  Fetching TP4054 (C668215)...")
    tp4054_id = sb.add_component_from_lcsc("C668215")
    if not tp4054_id:
        print("ERROR: Failed to fetch TP4054", file=sys.stderr)
        return

    # 2. Add power symbols
    print("  Adding power symbols...")
    power = sb.add_power_symbols()

    # 3. Place TP4054 at center
    print("  Placing components...")
    u1 = sb.place_component(tp4054_id, 400, -300, "U1")

    # TP4054 pins (relative coords from v6 data):
    #   Pin 1 CHRG: (-45, -10)  → abs (355, -310)
    #   Pin 2 GND:  (-45,   0)  → abs (355, -300)
    #   Pin 3 BAT:  (-45,  10)  → abs (355, -290)
    #   Pin 4 VCC:  ( 45,  10)  → abs (445, -290)
    #   Pin 5 PROG: ( 45, -10)  → abs (445, -310)

    # 4. Add power connections
    print("  Adding wires and power symbols...")

    # VCC pin 4 (445, -290) → +5V
    sb.place_power(475, -290, "+5V", power)
    sb.add_wire(445, -290, 475, -290)

    # GND pin 2 (355, -300) → GND
    sb.place_power(325, -300, "GND", power, rotation=270)
    sb.add_wire(325, -300, 355, -300)

    # BAT pin 3 (355, -290) → net label VBAT
    sb.add_wire(355, -290, 325, -290, "VBAT")

    # CHRG pin 1 (355, -310) → net label CHRG
    sb.add_wire(355, -310, 325, -310, "CHRG")

    # PROG pin 5 (445, -310) → net label PROG
    sb.add_wire(445, -310, 475, -310, "PROG")

    # 5. Build and write
    print(f"  Writing {output_path}...")
    sb.build(output_path)

    # Show stats
    print(f"\nDone! Generated {output_path}")
    print(f"  DEVICE+SYMBOL lines: {len(sb.device_lines) + len(sb.symbol_lines)}")
    print(f"  SCH_PAGE content lines: {len(sb.sch_content_lines)}")
    print(f"  Total tickets used: {sb.ticket}")
    print(f"\nOpen in EasyEDA Pro to verify.")


def main():
    parser = argparse.ArgumentParser(description="Pack .epro2 schematic file")
    parser.add_argument("input", nargs="?", help="Input epru lines file")
    parser.add_argument("-o", "--output", default="output.epro2", help="Output .epro2 file")
    parser.add_argument("--title", default="MyProject", help="Project title")
    parser.add_argument("--test", action="store_true",
                        help="Build test schematic (TP4054 charger)")
    args = parser.parse_args()

    if args.test:
        build_test_schematic(args.output)
        return

    if args.input:
        # Read epru lines from file and pack
        with open(args.input) as f:
            lines = f.read().splitlines()

        builder = Epro2Builder(args.title)
        builder.add_raw_lines(lines)
        builder.add_sch_section()
        builder.add_sch_page_section()
        builder.add_blob_section()
        builder.write_epro2(args.output)
        print(f"Written {args.output}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
