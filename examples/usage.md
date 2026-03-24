# Example: Parsing and Building an EasyEDA Pro Schematic

## 1. Parse an Existing Schematic

```bash
# Show component summary
python3 tools/parse_epro2.py mydesign.epro2

# Show all pin absolute coordinates
python3 tools/parse_epro2.py mydesign.epro2 --pins

# Show existing wires and net labels
python3 tools/parse_epro2.py mydesign.epro2 --wires

# Show power symbols
python3 tools/parse_epro2.py mydesign.epro2 --power

# Export everything as JSON for scripting
python3 tools/parse_epro2.py mydesign.epro2 --json > schematic_data.json
```

## 2. Preview Pin Map for Wire Generation

```bash
python3 tools/gen_wires.py mydesign.epro2 --dry-run
```

Output:
```
Pin position map:
==================================================
  C1.#1                     (   680,  -250)
  C1.#2                     (   720,  -250)
  U1.VCC                    (   350,  -450)
  U1.GND                    (   230,  -560)
  ...
```

## 3. Generate Wires from Netlist JSON

Create a `netlist.json`:
```json
{
  "wires": [
    {"from": "U1.D+", "to": "J1.DP1", "net": "USB_DP"},
    {"from": "U1.D-", "to": "J1.DN1", "net": "USB_DN"},
    {"from": "U1.VCC", "to": "C1.#1", "net": ""}
  ]
}
```

```bash
python3 tools/gen_wires.py mydesign.epro2 --netlist netlist.json -o wires.txt
```

## 4. Build Schematic Programmatically

```python
from tools.build_schematic import EasyEDAWriter, inject_lines
from tools.parse_epro2 import load_epro2, get_max_ticket, pin_abs_position

# Load existing schematic
components, wires, symbols = load_epro2("mydesign.epro2")
max_ticket = get_max_ticket("mydesign.epro2")

# Build pin position map
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

# Create writer
w = EasyEDAWriter(start_ticket=max_ticket + 1, start_z=200)

# Add wires with net labels
w.add_wire(100, -200, 150, -200, "SDA")
w.add_wire(100, -220, 150, -220, "SCL")

# Add power symbols (requires project-specific UUIDs)
# Extract these from the existing SYMBOL/DEVICE sections
GND_SYM = "b5fc023152e63698"   # from your project
GND_DEV = "94150318f6d1792d"   # from your project
VCC_SYM = "fa489ef6ae369c9a"   # from your project
VCC_DEV = "69734524f66a8ada"   # from your project

w.add_power(100, -300, "GND", sym_uuid=GND_SYM, dev_uuid=GND_DEV)
w.add_wire(100, -300, 100, -280)  # short stub to pin
w.add_power(100, -150, "3V3", sym_uuid=VCC_SYM, dev_uuid=VCC_DEV)
w.add_wire(100, -150, 100, -170)  # short stub to pin

# Add multi-segment wire (L-shaped)
w.add_multi_wire([
    (200, -300, 250, -300),   # horizontal segment
    (250, -300, 250, -350),   # vertical segment
], net_name="DATA")

# Inject into epro2 file
inject_lines("mydesign.epro2", "mydesign_wired.epro2", w.lines)
```

## 5. Extracting Power Symbol UUIDs

Power symbol UUIDs are project-specific. To extract them from an existing project:

```python
import json
from tools.parse_epro2 import load_epro2

components, wires, symbols = load_epro2("mydesign.epro2")

for c in components:
    if c.part_id == "pid8a0e77bacb214e" and c.name:
        print(f"Net: {c.name:8s}  Symbol: {c.symbol_uuid}  Device: {c.device_uuid}")
```

Output:
```
Net: GND       Symbol: b5fc023152e63698  Device: 94150318f6d1792d
Net: 3V3       Symbol: fa489ef6ae369c9a  Device: 69734524f66a8ada
Net: +5V       Symbol: fa489ef6ae369c9a  Device: 69734524f66a8ada
```

Use these UUIDs when calling `add_power()`.
