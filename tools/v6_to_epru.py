#!/usr/bin/env python3
"""
Convert EasyEDA v6 component data to EasyEDA Pro (v3) epru format.

When EasyEDA Pro's editor places a component from the library, it internally
converts the v6-format library data into epru records. This tool replicates
that conversion, enabling fully programmatic .epro2 file generation.

Conversion rules (reverse-engineered):
- Pin coordinates: epru_rel = v6_abs - v6_origin
- Pin rotation: epru_rot = (v6_rot + 180) % 360
- Shapes: v6 R/E/PL/A → epru RECT/ELLIPSE/POLY/ARC

Usage:
    # Fetch component from LCSC and convert to epru lines
    python3 v6_to_epru.py C668215

    # Output as file fragment (can be injected into .epro2)
    python3 v6_to_epru.py C668215 -o tp4054_sections.txt

    # Batch convert multiple components
    python3 v6_to_epru.py C668215 C841192 C20617299
"""

import json
import sys
import os
import argparse
import secrets
import time

from lcsc_fetch import get_easyeda_component, get_lcsc_detail, parse_v6_pins, parse_v6_origin


def rand_id():
    return secrets.token_hex(8)


def rand_uuid():
    return secrets.token_hex(8)


class EpruSectionWriter:
    """Generates epru-format lines for DEVICE, SYMBOL, and FOOTPRINT sections."""

    def __init__(self, start_ticket=1):
        self.ticket = start_ticket
        self.lines = []

    def _t(self):
        t = self.ticket
        self.ticket += 1
        return t

    def write_device_section(self, part_id, title, tags=None,
                             symbol_uuid=None, footprint_uuid=None,
                             attributes=None):
        """Generate a DEVICE section.

        Args:
            symbol_uuid: UUID of the SYMBOL section (set after symbol is generated)
            footprint_uuid: UUID of the FOOTPRINT section
            attributes: dict of extra attributes (Supplier Part, Manufacturer, etc.)

        Returns: device_uuid
        """
        device_uuid = rand_uuid()
        now_ms = int(time.time() * 1000)
        client = rand_id()

        # DOCHEAD
        self.lines.append(
            f'{{"type":"DOCHEAD","ticket":{self._t()}}}'
            f'||{{"docType":"DEVICE","client":"{client}",'
            f'"uuid":"{device_uuid}","updateTime":{now_ms},'
            f'"version":"{now_ms}"}}'
            f'|'
        )

        # Build attributes dict
        attrs = {}
        if attributes:
            attrs.update(attributes)
        if symbol_uuid:
            attrs["Symbol"] = symbol_uuid
        if footprint_uuid:
            attrs["Footprint"] = footprint_uuid

        # META
        tag_str = json.dumps(tags or [], ensure_ascii=False)
        attrs_str = json.dumps(attrs, ensure_ascii=False)
        self.lines.append(
            f'{{"type":"META","ticket":{self._t()},"id":"META"}}'
            f'||{{"title":"{title}","tags":{tag_str},'
            f'"source":"","images":[""],'
            f'"attributes":{attrs_str}}}'
            f'|'
        )

        return device_uuid

    def _attr_json(self, part_id, z_index, parent_id, key, value,
                   key_visible=False, value_visible=False,
                   x=None, y=None, rotation=0):
        """Build a complete ATTR body JSON matching the real epro2 format."""
        xv = "null" if x is None else str(x)
        yv = "null" if y is None else str(y)
        kv = "false" if not key_visible else "true"
        vv = "false" if not value_visible else "true"
        rv = "null" if rotation is None else str(rotation)
        # Escape value for JSON
        val = json.dumps(value) if value is not None else "null"
        return (
            f'{{"partId":"{part_id}","groupId":"","locked":false,'
            f'"zIndex":{z_index},"parentId":"{parent_id}",'
            f'"key":"{key}","value":{val},'
            f'"keyVisible":{kv},"valueVisible":{vv},'
            f'"x":{xv},"y":{yv},"rotation":{rv},'
            f'"color":null,"fillColor":null,'
            f'"fontFamily":null,"fontSize":null,"fontWeight":null,'
            f'"italic":null,"underline":null,"align":null}}'
        )

    def _pin_label_xy(self, pin_x, pin_y, epru_rot, label_type):
        """Compute x,y for pin name/number labels based on pin position and rotation.

        Derived from real epro2 data analysis:
        - rot 0 (left pin): name x=pin_x+13.7, number x=pin_x+9.5
        - rot 180 (right pin): name x=pin_x-13.7, number x=pin_x-9.5
        - rot 90 (bottom pin): swap x/y logic
        - rot 270 (top pin): swap x/y logic
        - y offset: name +5.915, number +0.915
        """
        name_offset = 13.7
        num_offset = 9.5
        y_name = 5.91498
        y_num = 0.91498

        if epru_rot == 0:  # pin on left, pointing right
            if label_type == "name":
                return pin_x + name_offset, pin_y + y_name
            else:
                return pin_x + num_offset, pin_y + y_num
        elif epru_rot == 180:  # pin on right, pointing left
            if label_type == "name":
                return pin_x - name_offset, pin_y + y_name
            else:
                return pin_x - num_offset, pin_y + y_num
        elif epru_rot == 90:  # pin on bottom
            if label_type == "name":
                return pin_x - y_name, pin_y + name_offset
            else:
                return pin_x - y_num, pin_y + num_offset
        else:  # 270, pin on top
            if label_type == "name":
                return pin_x + y_name, pin_y - name_offset
            else:
                return pin_x + y_num, pin_y - num_offset

    def write_symbol_section(self, part_id, v6_data):
        """Generate a SYMBOL section from v6 component data.

        Args:
            part_id: e.g. "TP4054_C668215.1"
            v6_data: result from get_easyeda_component()

        Returns: symbol_uuid
        """
        symbol_uuid = rand_uuid()
        now_ms = int(time.time() * 1000)
        client = rand_id()

        ds = v6_data.get("dataStr", {})
        head = ds.get("head", {})
        shapes = ds.get("shape", [])
        origin_x, origin_y = head.get("x", 0), head.get("y", 0)

        # DOCHEAD
        self.lines.append(
            f'{{"type":"DOCHEAD","ticket":{self._t()}}}'
            f'||{{"docType":"SYMBOL","client":"{client}",'
            f'"uuid":"{symbol_uuid}","updateTime":{now_ms},'
            f'"version":"{now_ms}"}}'
            f'|'
        )

        # CANVAS
        self.lines.append(
            f'{{"type":"CANVAS","ticket":{self._t()},"id":"CANVAS"}}'
            f'||{{"originX":0,"originY":0}}|'
        )

        # PART
        bbox = self._compute_bbox(shapes, origin_x, origin_y)
        self.lines.append(
            f'{{"type":"PART","ticket":{self._t()},"id":"{part_id}"}}'
            f'||{{"BBOX":{json.dumps(bbox)},"title":"{part_id}"}}'
            f'|'
        )

        title = v6_data.get("title", part_id)
        c_para = head.get("c_para", {})
        pre = c_para.get("pre", "U?")

        # Symbol ATTR
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"e1"}}'
            f'||{self._attr_json(part_id, 1, "", "Symbol", title, value_visible=False)}'
            f'|'
        )

        # Designator ATTR
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"e2"}}'
            f'||{self._attr_json(part_id, 2, "", "Designator", pre, value_visible=False)}'
            f'|'
        )

        # Collect shapes: rects first, then pins (matching real file order)
        rects = [(i, s) for i, s in enumerate(shapes) if s.startswith("R~")]
        circles = [(i, s) for i, s in enumerate(shapes) if s.startswith("E~")]
        pins = [(i, s) for i, s in enumerate(shapes) if s.startswith("P~")]

        z_index = 3
        eid_counter = 3
        placeholder_counter = 1

        # Process rectangles
        for _, shape_str in rects:
            rect = self._parse_v6_rect(shape_str, origin_x, origin_y)
            if rect:
                self.lines.append(
                    f'{{"type":"ELE_PLACEHOLDER","ticket":{self._t()},"id":"placeholder{placeholder_counter}"}}'
                    f'||{{"dataType":"RECT","max":{eid_counter}}}'
                    f'|'
                )
                placeholder_counter += 1
                rect_id = f"e{eid_counter}"
                eid_counter += 1
                # Use dotX1/dotY1/dotX2/dotY2 format (matching real epro2)
                dot_x1 = rect["x"]
                dot_y1 = rect["y"] + rect["h"]
                dot_x2 = rect["x"] + rect["w"]
                dot_y2 = rect["y"]
                self.lines.append(
                    f'{{"type":"RECT","ticket":{self._t()},"id":"{rect_id}"}}'
                    f'||{{"partId":"{part_id}","groupId":"","locked":false,'
                    f'"zIndex":{z_index},'
                    f'"dotX1":{dot_x1},"dotY1":{dot_y1},'
                    f'"dotX2":{dot_x2},"dotY2":{dot_y2},'
                    f'"radiusX":{rect.get("rx", 0)},"radiusY":{rect.get("ry", 0)},'
                    f'"rotation":0,'
                    f'"strokeColor":null,"strokeStyle":null,'
                    f'"fillColor":null,"strokeWidth":null,"fillStyle":null}}'
                    f'|'
                )
                z_index += 1

        # Process circles (pin 1 dot indicator)
        for _, shape_str in circles:
            circle = self._parse_v6_circle(shape_str, origin_x, origin_y)
            if circle:
                self.lines.append(
                    f'{{"type":"ELE_PLACEHOLDER","ticket":{self._t()},"id":"placeholder{placeholder_counter}"}}'
                    f'||{{"dataType":"CIRCLE","max":{eid_counter}}}'
                    f'|'
                )
                placeholder_counter += 1
                circ_id = f"e{eid_counter}"
                eid_counter += 1
                self.lines.append(
                    f'{{"type":"CIRCLE","ticket":{self._t()},"id":"{circ_id}"}}'
                    f'||{{"partId":"{part_id}","groupId":"","locked":false,'
                    f'"zIndex":{z_index},'
                    f'"centerX":{circle["cx"]},"centerY":{circle["cy"]},'
                    f'"radius":{circle["r"]},'
                    f'"strokeColor":null,"strokeStyle":null,'
                    f'"fillColor":null,"strokeWidth":null,"fillStyle":null}}'
                    f'|'
                )
                z_index += 1

        # Process pins
        for _, shape_str in pins:
            pin_data = self._parse_v6_pin(shape_str, origin_x, origin_y)
            if not pin_data:
                continue

            # ELE_PLACEHOLDER with max = number of sub-elements (PIN + 3 ATTRs = 4, but max counts from eid)
            self.lines.append(
                f'{{"type":"ELE_PLACEHOLDER","ticket":{self._t()},"id":"placeholder{placeholder_counter}"}}'
                f'||{{"dataType":"PIN","max":3}}'
                f'|'
            )
            placeholder_counter += 1

            pin_id = f"e{eid_counter}"
            eid_counter += 1

            # PIN record
            self.lines.append(
                f'{{"type":"PIN","ticket":{self._t()},"id":"{pin_id}"}}'
                f'||{{"partId":"{part_id}","groupId":"","locked":false,'
                f'"zIndex":{z_index},"display":true,'
                f'"x":{pin_data["rel_x"]},"y":{pin_data["rel_y"]},'
                f'"length":10,"rotation":{pin_data["epru_rot"]},'
                f'"color":null,"pinShape":"NONE"}}'
                f'|'
            )
            z_index += 1

            # Pin Name ATTR (with computed label position)
            nx, ny = self._pin_label_xy(
                pin_data["rel_x"], pin_data["rel_y"],
                pin_data["epru_rot"], "name")
            attr_id = f"e{eid_counter}"
            eid_counter += 1
            self.lines.append(
                f'{{"type":"ATTR","ticket":{self._t()},"id":"{attr_id}"}}'
                f'||{self._attr_json(part_id, z_index, pin_id, "Pin Name", pin_data["name"], value_visible=True, x=nx, y=ny)}'
                f'|'
            )
            z_index += 1

            # Pin Number ATTR
            nnx, nny = self._pin_label_xy(
                pin_data["rel_x"], pin_data["rel_y"],
                pin_data["epru_rot"], "number")
            attr_id = f"e{eid_counter}"
            eid_counter += 1
            self.lines.append(
                f'{{"type":"ATTR","ticket":{self._t()},"id":"{attr_id}"}}'
                f'||{self._attr_json(part_id, z_index, pin_id, "Pin Number", pin_data["number"], value_visible=True, x=nnx, y=nny)}'
                f'|'
            )
            z_index += 1

            # Pin Type ATTR
            attr_id = f"e{eid_counter}"
            eid_counter += 1
            self.lines.append(
                f'{{"type":"ATTR","ticket":{self._t()},"id":"{attr_id}"}}'
                f'||{self._attr_json(part_id, z_index, pin_id, "Pin Type", pin_data.get("pin_type", "Undefined"), x=pin_data["rel_x"], y=pin_data["rel_y"])}'
                f'|'
            )
            z_index += 1

        # META at end
        title_clean = v6_data.get("title", part_id.rstrip(".1"))
        self.lines.append(
            f'{{"type":"META","ticket":{self._t()},"id":"META"}}'
            f'||{{"title":"{title_clean}","description":"","tags":[],'
            f'"docType":2,"source":""}}'
            f'|'
        )

        return symbol_uuid

    def write_power_symbol_section(self, net_type="GND"):
        """Generate a built-in power symbol DEVICE + SYMBOL section.

        Args:
            net_type: "GND" or "VCC" (VCC covers 3V3, +5V, etc.)

        Returns: (symbol_uuid, device_uuid)
        """
        symbol_uuid = rand_uuid()
        device_uuid = rand_uuid()
        now_ms = int(time.time() * 1000)
        client = rand_id()

        # DEVICE section
        self.lines.append(
            f'{{"type":"DOCHEAD","ticket":{self._t()}}}'
            f'||{{"docType":"DEVICE","client":"{client}",'
            f'"uuid":"{device_uuid}","updateTime":{now_ms},'
            f'"version":"{now_ms}"}}'
            f'|'
        )
        self.lines.append(
            f'{{"type":"META","ticket":{self._t()},"id":"META"}}'
            f'||{{"title":"{net_type}","tags":["Power"],'
            f'"source":"","images":[""],"attributes":{{}}}}'
            f'|'
        )

        # SYMBOL section
        self.lines.append(
            f'{{"type":"DOCHEAD","ticket":{self._t()}}}'
            f'||{{"docType":"SYMBOL","client":"{client}",'
            f'"uuid":"{symbol_uuid}","updateTime":{now_ms},'
            f'"version":"{now_ms}"}}'
            f'|'
        )
        self.lines.append(
            f'{{"type":"CANVAS","ticket":{self._t()},"id":"CANVAS"}}'
            f'||{{"originX":0,"originY":0}}|'
        )

        part_id = "pid8a0e77bacb214e"

        if net_type == "GND":
            # GND symbol: horizontal bar with vertical line
            self.lines.append(
                f'{{"type":"PART","ticket":{self._t()},"id":"{part_id}"}}'
                f'||{{"BBOX":[-10,-10,10,10],"title":"GND"}}'
                f'|'
            )
            # Single pin at origin pointing up (rot=270 in epru → connects from above)
            self.lines.append(
                f'{{"type":"PIN","ticket":{self._t()},"id":"e3"}}'
                f'||{{"partId":"{part_id}","groupId":"","locked":false,'
                f'"zIndex":3,"display":true,"x":0,"y":0,"length":5,'
                f'"rotation":270,"color":null,"pinShape":"NONE"}}'
                f'|'
            )
        else:
            # VCC/3V3/+5V symbol: arrow pointing up
            self.lines.append(
                f'{{"type":"PART","ticket":{self._t()},"id":"{part_id}"}}'
                f'||{{"BBOX":[-10,-10,10,10],"title":"VCC"}}'
                f'|'
            )
            self.lines.append(
                f'{{"type":"PIN","ticket":{self._t()},"id":"e3"}}'
                f'||{{"partId":"{part_id}","groupId":"","locked":false,'
                f'"zIndex":3,"display":true,"x":0,"y":0,"length":5,'
                f'"rotation":270,"color":null,"pinShape":"NONE"}}'
                f'|'
            )

        # Pin ATTRs
        for key, val in [("Pin Name", "1"), ("Pin Number", "1"), ("Pin Type", "Power")]:
            self.lines.append(
                f'{{"type":"ATTR","ticket":{self._t()},"id":"e{self.ticket}"}}'
                f'||{{"partId":"{part_id}","groupId":"","locked":false,'
                f'"zIndex":4,"parentId":"e3","key":"{key}","value":"{val}"}}'
                f'|'
            )

        self.lines.append(
            f'{{"type":"META","ticket":{self._t()},"id":"META"}}'
            f'||{{"title":"{net_type}","description":"","tags":["Power"],'
            f'"docType":2,"source":""}}'
            f'|'
        )

        return symbol_uuid, device_uuid

    # Standard PCB layer definitions (same for all footprints)
    FOOTPRINT_LAYERS = [
        {"layerType":"TOP","layerName":"Top Layer","use":True,"show":True,"locked":False,"activeColor":"#FF0000","activateTransparency":1,"inactiveColor":"#7F0000","inactiveTransparency":1},
        {"layerType":"BOTTOM","layerName":"Bottom Layer","use":True,"show":True,"locked":False,"activeColor":"#0000FF","activateTransparency":1,"inactiveColor":"#00007F","inactiveTransparency":1},
        {"layerType":"TOP_SILK","layerName":"Top Silkscreen Layer","use":True,"show":True,"locked":False,"activeColor":"#FFCC00","activateTransparency":1,"inactiveColor":"#7F6600","inactiveTransparency":1},
        {"layerType":"BOT_SILK","layerName":"Bottom Silkscreen Layer","use":True,"show":True,"locked":False,"activeColor":"#66CC33","activateTransparency":1,"inactiveColor":"#336619","inactiveTransparency":1},
        {"layerType":"TOP_PASTE_MASK","layerName":"Top Paste Mask Layer","use":True,"show":True,"locked":False,"activeColor":"#808080","activateTransparency":1,"inactiveColor":"#404040","inactiveTransparency":1},
        {"layerType":"BOT_PASTE_MASK","layerName":"Bottom Paste Mask Layer","use":True,"show":True,"locked":False,"activeColor":"#800000","activateTransparency":1,"inactiveColor":"#400000","inactiveTransparency":1},
        {"layerType":"TOP_SOLDER_MASK","layerName":"Top Solder Mask Layer","use":True,"show":True,"locked":False,"activeColor":"#800080","activateTransparency":1,"inactiveColor":"#400040","inactiveTransparency":1},
        {"layerType":"BOT_SOLDER_MASK","layerName":"Bottom Solder Mask Layer","use":True,"show":True,"locked":False,"activeColor":"#AA00FF","activateTransparency":1,"inactiveColor":"#55007F","inactiveTransparency":1},
        {"layerType":"DOCUMENT","layerName":"Document Layer","use":True,"show":True,"locked":False,"activeColor":"#FFFFFF","activateTransparency":1,"inactiveColor":"#7F7F7F","inactiveTransparency":1},
        {"layerType":"OUTLINE","layerName":"Board Outline Layer","use":True,"show":True,"locked":False,"activeColor":"#FF00FF","activateTransparency":1,"inactiveColor":"#7F007F","inactiveTransparency":1},
        {"layerType":"MULTI","layerName":"Multi-Layer","use":True,"show":True,"locked":False,"activeColor":"#C0C0C0","activateTransparency":1,"inactiveColor":"#606060","inactiveTransparency":1},
        {"layerType":"TOP_ASSEMBLY","layerName":"Top Assembly Layer","use":True,"show":True,"locked":False,"activeColor":"#33CC99","activateTransparency":1,"inactiveColor":"#19664C","inactiveTransparency":1},
        {"layerType":"BOT_ASSEMBLY","layerName":"Bottom Assembly Layer","use":True,"show":True,"locked":False,"activeColor":"#5555FF","activateTransparency":1,"inactiveColor":"#2A2A7F","inactiveTransparency":1},
        {"layerType":"MECHANICAL","layerName":"Mechanical Layer","use":True,"show":True,"locked":False,"activeColor":"#F022F0","activateTransparency":1,"inactiveColor":"#781178","inactiveTransparency":1},
        {"layerType":"COMPONENT_MODEL","layerName":"Component Model Layer","use":True,"show":True,"locked":False,"activeColor":"#FFFFFF","activateTransparency":1,"inactiveColor":"#7F7F7F","inactiveTransparency":1},
        {"layerType":"COMPONENT_SHAPE","layerName":"Component Shape Layer","use":True,"show":True,"locked":False,"activeColor":"#00CCCC","activateTransparency":1,"inactiveColor":"#006666","inactiveTransparency":1},
        {"layerType":"PIN_FLOATING","layerName":"Pin Floating Layer","use":True,"show":True,"locked":False,"activeColor":"#FF99FF","activateTransparency":1,"inactiveColor":"#7F4C7F","inactiveTransparency":1},
        {"layerType":"COMPONENT_MARKING","layerName":"Component Marking Layer","use":True,"show":True,"locked":False,"activeColor":"#66FFCC","activateTransparency":1,"inactiveColor":"#337F66","inactiveTransparency":1},
        {"layerType":"PIN_SOLDERING","layerName":"Pin Soldering Layer","use":True,"show":True,"locked":False,"activeColor":"#CC9999","activateTransparency":1,"inactiveColor":"#664C4C","inactiveTransparency":1},
    ]

    def write_footprint_section(self, package_name, pin_count, designator_prefix="U?"):
        """Generate a FOOTPRINT section with standard layers and minimal pad data.

        Args:
            package_name: e.g. "TSOT-23-5_L2.9-W1.6-P0.95-LS2.8-BR"
            pin_count: number of pads
            designator_prefix: e.g. "U?", "R?", "C?"

        Returns: footprint_uuid
        """
        footprint_uuid = rand_uuid()
        now_ms = int(time.time() * 1000)
        client = rand_id()

        # DOCHEAD
        self.lines.append(
            f'{{"type":"DOCHEAD","ticket":{self._t()}}}'
            f'||{{"docType":"FOOTPRINT","client":"{client}",'
            f'"uuid":"{footprint_uuid}","updateTime":{now_ms},'
            f'"version":"{now_ms}"}}'
            f'|'
        )

        # Standard LAYER records
        for layer in self.FOOTPRINT_LAYERS:
            self.lines.append(
                f'{{"type":"LAYER","ticket":{self._t()}}}'
                f'||{json.dumps(layer)}|'
            )

        # ACTIVE_LAYER
        self.lines.append(
            f'{{"type":"ACTIVE_LAYER","ticket":{self._t()}}}'
            f'||{{"layerId":1}}|'
        )

        # CANVAS
        self.lines.append(
            f'{{"type":"CANVAS","ticket":{self._t()},"id":"CANVAS"}}'
            f'||{{"originX":0,"originY":0,"unit":"mm","gridXSize":10,"gridYSize":10,'
            f'"snapXSize":0.5,"snapYSize":0.5,"gridType":"NONE","multiGridType":"NONE",'
            f'"highlightValue":0.5}}|'
        )

        # Generate PAD records with generic positions
        # For SMD pads: arrange in two rows for IC packages
        pad_spacing = 37.4  # ~0.95mm in mils*100 scale
        half_pins_left = (pin_count + 1) // 2  # pins on left side
        half_pins_right = pin_count - half_pins_left

        eid = 1
        self.lines.append(
            f'{{"type":"ELE_PLACEHOLDER","ticket":{self._t()},"id":"placeholder1"}}'
            f'||{{"dataType":"PAD","max":{pin_count}}}|'
        )

        for pad_num in range(1, pin_count + 1):
            if pad_num <= half_pins_right:
                # Right side pads (top to bottom)
                cx = 50.0
                cy = -pad_spacing * (half_pins_right - 1) / 2 + (pad_num - 1) * pad_spacing
                angle = 0
            else:
                # Left side pads (bottom to top)
                idx = pad_num - half_pins_right - 1
                cx = -50.0
                cy = pad_spacing * (half_pins_left - 1) / 2 - idx * pad_spacing
                angle = 180

            self.lines.append(
                f'{{"type":"PAD","ticket":{self._t()},"id":"e{eid}"}}'
                f'||{{"groupId":0,"netName":"","layerId":1,"num":"{pad_num}",'
                f'"centerX":{cx},"centerY":{cy},"padAngle":{angle},'
                f'"hole":null,'
                f'"defaultPad":{{"padWidth":15.748,"padHeight":37.402,"shape":"RECT","rotation":0,'
                f'"offset":{{"dx":17.323,"dy":0}},"expand":3.937}},'
                f'"locked":false,"zIndex":{eid},"polyType":"VIA"}}|'
            )
            eid += 1

        # Footprint ATTR
        self.lines.append(
            f'{{"type":"ELE_PLACEHOLDER","ticket":{self._t()},"id":"placeholder2"}}'
            f'||{{"dataType":"ATTR","max":1}}|'
        )
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"e{eid}"}}'
            f'||{{"groupId":0,"parentId":"","layerId":3,"x":null,"y":null,'
            f'"key":"Footprint","value":"{package_name}",'
            f'"keyVisible":false,"valueVisible":true,'
            f'"rotation":0,"color":null,"fillColor":null,'
            f'"fontFamily":null,"fontSize":null,"fontWeight":null,'
            f'"italic":null,"underline":null,"align":null}}|'
        )
        eid += 1

        # Designator ATTR
        self.lines.append(
            f'{{"type":"ATTR","ticket":{self._t()},"id":"e{eid}"}}'
            f'||{{"groupId":0,"parentId":"","layerId":3,"x":null,"y":null,'
            f'"key":"Designator","value":"{designator_prefix}",'
            f'"keyVisible":false,"valueVisible":true,'
            f'"rotation":0,"color":null,"fillColor":null,'
            f'"fontFamily":null,"fontSize":null,"fontWeight":null,'
            f'"italic":null,"underline":null,"align":null}}|'
        )
        eid += 1

        # NET
        self.lines.append(
            f'{{"type":"NET","ticket":{self._t()}}}'
            f'||{{"netType":null,"specialColor":null,"retLine":true,'
            f'"differentialName":null,"isPositiveNet":false,'
            f'"equalLengthGroupName":null}}|'
        )

        # META
        self.lines.append(
            f'{{"type":"META","ticket":{self._t()},"id":"META"}}'
            f'||{{"title":"{package_name}","description":"","tags":[],'
            f'"docType":4,"source":""}}|'
        )

        return footprint_uuid

    def _parse_v6_pin(self, shape_str, origin_x, origin_y):
        """Parse a v6 pin string into epru-compatible data."""
        parts = shape_str.split("^^")
        if len(parts) < 5:
            return None

        header = parts[0].split("~")
        if len(header) < 7:
            return None

        abs_x = float(header[4])
        abs_y = float(header[5])
        v6_rot = int(header[6]) if header[6] else 0

        # Pin name from part[3]
        name_parts = parts[3].split("~")
        pin_name = name_parts[4] if len(name_parts) > 4 else ""

        # Pin number from part[4]
        num_parts = parts[4].split("~")
        pin_number = num_parts[4] if len(num_parts) > 4 else ""

        # Determine pin type from color
        pin_type = "Undefined"
        if len(name_parts) > 8:
            color = name_parts[8] if len(name_parts) > 8 else ""
            if color == "#FF0000":
                pin_type = "Power"
            elif color == "#000000":
                pin_type = "Power"  # GND is also power

        return {
            "name": pin_name,
            "number": pin_number,
            "rel_x": abs_x - origin_x,
            "rel_y": abs_y - origin_y,
            "epru_rot": (v6_rot + 180) % 360,
            "pin_type": pin_type,
        }

    def _parse_v6_circle(self, shape_str, origin_x, origin_y):
        """Parse a v6 ellipse/circle string (E~cx~cy~rx~ry~...)."""
        parts = shape_str.split("~")
        if len(parts) < 5:
            return None
        try:
            return {
                "cx": float(parts[1]) - origin_x,
                "cy": float(parts[2]) - origin_y,
                "r": float(parts[3]),  # use rx as radius
            }
        except (ValueError, IndexError):
            return None

    def _parse_v6_rect(self, shape_str, origin_x, origin_y):
        """Parse a v6 rectangle string."""
        # R~x~y~rx~ry~width~height~color~strokeWidth~...
        parts = shape_str.split("~")
        if len(parts) < 7:
            return None
        try:
            return {
                "x": float(parts[1]) - origin_x,
                "y": float(parts[2]) - origin_y,
                "rx": float(parts[3]),
                "ry": float(parts[4]),
                "w": float(parts[5]),
                "h": float(parts[6]),
            }
        except (ValueError, IndexError):
            return None

    def _compute_bbox(self, shapes, origin_x, origin_y):
        """Compute bounding box from v6 shapes."""
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')

        for s in shapes:
            if s.startswith("P~"):
                parts = s.split("~")
                if len(parts) > 5:
                    try:
                        x = float(parts[4]) - origin_x
                        y = float(parts[5]) - origin_y
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        max_x = max(max_x, x)
                        max_y = max(max_y, y)
                    except ValueError:
                        pass
            elif s.startswith("R~"):
                parts = s.split("~")
                if len(parts) > 7:
                    try:
                        x = float(parts[1]) - origin_x
                        y = float(parts[2]) - origin_y
                        w = float(parts[5])
                        h = float(parts[6])
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        max_x = max(max_x, x + w)
                        max_y = max(max_y, y + h)
                    except ValueError:
                        pass

        if min_x == float('inf'):
            return [-50, -50, 50, 50]
        return [min_x, min_y, max_x, max_y]


def convert_component(lcsc_code, ticket_start=1):
    """Convert a LCSC component to epru DEVICE + SYMBOL + FOOTPRINT sections.

    Returns dict with: lines, device_uuid, symbol_uuid, footprint_uuid,
                       part_id, title, next_ticket
    """
    eda_data = get_easyeda_component(lcsc_code)
    if not eda_data:
        print(f"No EasyEDA data for {lcsc_code}", file=sys.stderr)
        return None

    detail = get_lcsc_detail(lcsc_code)
    title = eda_data.get("title", lcsc_code)
    part_id = f"{title}.1"

    ds = eda_data.get("dataStr", {})
    head = ds.get("head", {})
    c_para = head.get("c_para", {})
    shapes = ds.get("shape", [])

    # Count pins
    pin_count = sum(1 for s in shapes if s.startswith("P~"))
    package_name = c_para.get("package", "Unknown")
    pre = c_para.get("pre", "U?")

    writer = EpruSectionWriter(start_ticket=ticket_start)

    # 1. Generate SYMBOL section first (need UUID for DEVICE attributes)
    symbol_uuid = writer.write_symbol_section(part_id, eda_data)

    # 2. Generate FOOTPRINT section
    footprint_uuid = writer.write_footprint_section(
        package_name, pin_count, designator_prefix=pre)

    # 3. Generate DEVICE section (with Symbol + Footprint UUIDs in attributes)
    tags = []
    if detail:
        cat = detail.get("catalogName", "")
        if cat:
            tags.append(cat)

    # Build attributes matching real epro2 format
    dev_attrs = {
        "Supplier Part": c_para.get("Supplier Part", lcsc_code),
        "Manufacturer": c_para.get("Manufacturer", ""),
        "Manufacturer Part": c_para.get("Manufacturer Part", ""),
        "Supplier": c_para.get("Supplier", "LCSC"),
        "Supplier Footprint": package_name,
        "Designator": pre,
        "Add into BOM": "yes",
        "Convert to PCB": "yes",
    }
    device_uuid = writer.write_device_section(
        part_id, title, tags,
        symbol_uuid=symbol_uuid,
        footprint_uuid=footprint_uuid,
        attributes=dev_attrs)

    return {
        "lines": writer.lines,
        "device_uuid": device_uuid,
        "symbol_uuid": symbol_uuid,
        "footprint_uuid": footprint_uuid,
        "part_id": part_id,
        "title": title,
        "package": package_name,
        "next_ticket": writer.ticket,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert EasyEDA v6 component data to epru format")
    parser.add_argument("codes", nargs="*", help="LCSC part codes (e.g., C668215)")
    parser.add_argument("-o", "--output", help="Output file")
    parser.add_argument("--json", action="store_true", help="Output metadata as JSON")
    args = parser.parse_args()

    if not args.codes:
        parser.print_help()
        return

    all_lines = []
    metadata = []
    ticket = 1

    for code in args.codes:
        code = code.upper()
        if not code.startswith("C"):
            code = "C" + code

        print(f"Converting {code}...", file=sys.stderr)
        result = convert_component(code, ticket_start=ticket)

        if not result:
            print(f"  FAILED", file=sys.stderr)
            continue

        all_lines.extend(result["lines"])
        ticket = result["next_ticket"]

        info = {
            "lcsc_code": code,
            "part_id": result["part_id"],
            "device_uuid": result["device_uuid"],
            "symbol_uuid": result["symbol_uuid"],
        }
        metadata.append(info)
        print(f"  {result['title']}: device={result['device_uuid'][:8]}... "
              f"symbol={result['symbol_uuid'][:8]}...", file=sys.stderr)

    if args.json:
        print(json.dumps(metadata, indent=2))
    elif args.output:
        with open(args.output, "w") as f:
            f.write("\n".join(all_lines) + "\n")
        print(f"Written {len(all_lines)} lines to {args.output}", file=sys.stderr)
    else:
        for line in all_lines:
            print(line)


if __name__ == "__main__":
    main()
