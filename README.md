# easyeda-agent-skills

AI agent toolkit for programmatic generation of EasyEDA Pro (.epro2) schematic files.
Includes reverse-engineered file format spec, LCSC/EasyEDA API integration,
and v6→epru format converter.

## Capabilities

### Mode 1: From Scratch (Full Interactive Design)

Start with nothing, end with a complete .epro2 schematic:

1. **Search & select** components from LCSC (1M+ parts, real-time stock & pricing)
2. **Download & read** datasheets automatically — extract application circuits, capacitor/resistor values
3. **Fetch symbol data** from EasyEDA library API — pin names, numbers, positions
4. **Convert to Pro format** — v6 library data → epru DEVICE/SYMBOL sections
5. **Generate wiring** — place components, add peripheral circuits per datasheet, connect nets
6. **Output .epro2** — opens directly in EasyEDA Pro

### Mode 2: Modify Existing Schematic

Start from a user-exported .epro2 with components already placed:

1. **Parse** the existing file — extract all component positions and pin coordinates
2. **Add wiring** — generate WIRE/LINE records connecting pins via net labels
3. **Add power symbols** — GND, VCC, 3V3 with correct rotation
4. **Add peripheral circuits** — decoupling caps, resistors per datasheet
5. **Output .epro2** — preserves all original data, only adds new records

## Directory Structure

```
spec/
  epro2-format.md          # .epro2/.epru file format specification
  schematic-drawing.md     # Wiring conventions, power symbols, decoupling caps
  coordinate-system.md     # Coordinate system, rotation, alignment, label placement
  api-reference.md         # LCSC / EasyEDA API endpoints and data formats

tools/
  lcsc_fetch.py            # LCSC API client: search, specs, pin data, datasheet download
  v6_to_epru.py            # Convert EasyEDA v6 library data → Pro epru format
  parse_epro2.py           # Parse existing .epro2 files
  gen_wires.py             # Generate wire records from netlist JSON
  build_schematic.py       # EasyEDAWriter framework for programmatic schematic building

examples/
  usage.md                 # Walkthrough: parsing and building schematics
```

## Quick Start

```bash
# Search for components
python3 tools/lcsc_fetch.py --search "TP4054"

# Get component info + pin map
python3 tools/lcsc_fetch.py C668215

# Download datasheet PDF
python3 tools/lcsc_fetch.py C668215 --datasheet

# Convert LCSC component to epru format (DEVICE + SYMBOL sections)
python3 tools/v6_to_epru.py C668215

# Parse an existing schematic
python3 tools/parse_epro2.py mydesign.epro2 --pins

# Build wired schematic from existing file
python3 tools/build_schematic.py mydesign.epro2 -o output.epro2
```

## For AI Agents

Feed `spec/` files as context. Use `tools/` for programmatic operations.

1. **epro2-format.md** — File structure, all record types, JSON schemas
2. **schematic-drawing.md** — Wiring conventions, power symbols, decoupling cap patterns
3. **coordinate-system.md** — Rotation math, label placement rules (from 960-label analysis)
4. **api-reference.md** — LCSC/EasyEDA API endpoints, v6 pin format documentation

### Key Technical Details

- **v6 → epru pin rotation**: `epru_rot = (v6_rot + 180) % 360`
- **v6 → epru pin coordinates**: `epru_rel = v6_abs - v6_origin`
- **Power symbol partId**: always `"pid8a0e77bacb214e"`, UUIDs are project-specific
- **Net label**: `fontSize: 8`, `keyVisible: false`, `valueVisible: true`
- **Insert position**: new records go before the BLOB section

## How It Works Internally

When EasyEDA Pro's editor lets you search a LCSC code (e.g., C668215) and drag
the component onto a schematic, it internally:

1. Fetches v6-format symbol data from `easyeda.com/api/products/{code}/components`
2. Converts pin coordinates from absolute to relative (subtract origin)
3. Flips pin rotation by 180° (v6 points outward, epru points inward)
4. Generates DEVICE/SYMBOL/FOOTPRINT sections in epru line format
5. Writes to the .epru file inside the .epro2 ZIP

This toolkit replicates that same conversion process programmatically.

## License

MIT
