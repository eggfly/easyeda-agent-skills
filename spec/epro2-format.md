# EasyEDA Pro (.epro2) File Format Specification

Version: Reverse-engineered from EasyEDA Pro v3.2.91 (2026)

## 1. File Structure

An `.epro2` file is a **ZIP archive** containing:

```
├── project2.json              # Project metadata
├── <ProjectName>.epru         # Main data file (all schematics, symbols, footprints)
└── IMAGE/
    ├── <uuid1>.webp           # Schematic page thumbnail
    ├── <uuid2>.webp           # ...
    └── ...
```

### project2.json

```json
{
  "title": "MyProject",
  "cbb_project": false,
  "editorVersion": "",
  "introduction": "",
  "description": "",
  "tags": "[]"
}
```

## 2. EPRU File Format

The `.epru` file is a **line-based text format** where each line is one record:

```
{header_json}||{body_json}|
```

- **Header**: `{"type":"TYPE","ticket":N,"id":"ID"}` or `{"type":"TYPE","ticket":N,"id":"ID","firstTicket":M}`
- **Body**: Type-specific JSON properties
- **Separator**: `||` between header and body
- **Terminator**: `|` at end of line
- **Encoding**: UTF-8

### 2.1 Header Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Record type (see Section 3) |
| `ticket` | integer | Auto-incrementing sequence number, globally unique within file |
| `id` | string | Unique identifier for this record |
| `firstTicket` | integer | (Optional) Original ticket number when record was first created |

### 2.2 ID Format

- **DOCHEAD ids**: Same as `uuid` in body, or special like `"META"`, `"CANVAS"`
- **Component/Wire ids**: 16-character lowercase hex string (e.g., `"69e5b1e4092c068b"`)
- **Symbol element ids**: Short format like `"e4"`, `"e8"`, `"e12"` (within SYMBOL sections)

## 3. Document Sections

The epru file contains multiple document sections, each starting with a DOCHEAD record.

### Section Order (typical)

```
DEVICE sections (1 per component type)     — electrical parameters
SYMBOL sections (1 per symbol type)         — schematic graphics + pin coordinates
FOOTPRINT sections (1 per footprint type)   — PCB pad layout
SCH sections (1 per board)                  — schematic hierarchy metadata
SCH_PAGE sections (1 per schematic page)    — actual schematic content
PCB sections (if applicable)                — PCB layout
BOARD sections (if applicable)              — board outline
CONFIG section                              — project configuration
FONT section                                — embedded fonts
BLOB section                                — binary data
```

### 3.1 DOCHEAD Record

```json
// Header
{"type":"DOCHEAD","ticket":1}
// Body
{
  "docType": "SCH_PAGE",           // Section type
  "client": "d81da101ffe7890f",    // Client identifier
  "uuid": "b6e9ac82c7f3e894",     // Section UUID
  "updateTime": 1774331394606,     // Unix timestamp (ms)
  "version": "1774331394606",
  "editVersion": "3.2.91",         // EasyEDA Pro version (in DEVICE sections)
  "user": {...}                    // User info (in DEVICE sections)
}
```

## 4. Record Types in SCH_PAGE

### 4.1 CANVAS

Page canvas settings. Always the first record after DOCHEAD.

```json
// Header: {"type":"CANVAS","ticket":1,"id":"CANVAS"}
// Body:
{"originX":0,"originY":0}
```

### 4.2 COMPONENT

Places a component instance on the schematic.

```json
// Header: {"type":"COMPONENT","ticket":35,"id":"69e5b1e4092c068b"}
// Body:
{
  "partId": "MyComponent.1",      // Reference to DEVICE section / library part
  "x": 350,                       // X position
  "y": -550,                      // Y position (negative = upward in editor)
  "rotation": 0,                  // 0, 90, 180, 270 degrees
  "isMirror": false,              // Horizontal mirror
  "attrs": {},                    // Additional attributes
  "zIndex": 1                     // Drawing order
}
```

**Special partIds:**
- `"pid8a0e77bacb214e"` — Built-in power/port symbol (GND, VCC, +5V, etc.)
- `"1"` — Custom/user-defined multi-pin component
- `"<PartName>.1"` — Library component (e.g., `"TP4054_C668215.1"`)

### 4.3 ATTR

Attribute attached to a parent record (COMPONENT, WIRE, or PIN).

```json
// Header: {"type":"ATTR","ticket":39,"id":"b5865928c760edeb"}
// Body:
{
  "x": 240,                       // Display position X (null if not displayed)
  "y": -650,                      // Display position Y
  "rotation": 0,                  // Text rotation
  "color": null,                  // Text color (null = default)
  "fontFamily": null,             // Font (null = default)
  "fontSize": null,               // Font size (null = default ~10, common: 8, 10)
  "fontWeight": false,            // Bold
  "italic": false,
  "underline": false,
  "strikeout": false,             // (only in some ATTRs)
  "align": "LEFT_BOTTOM",         // Text alignment (see Section 7)
  "value": "U1",                  // Attribute value
  "key": "Designator",            // Attribute key (see below)
  "keyVisible": null,             // Show key text
  "valueVisible": true,           // Show value text
  "fillColor": null,
  "parentId": "69e5b1e4092c068b", // Parent record ID
  "zIndex": 2,
  "locked": false
}
```

**Standard ATTR keys for COMPONENT:**

| Key | Value Type | Description |
|-----|-----------|-------------|
| `Symbol` | UUID string | Reference to SYMBOL section |
| `Device` | UUID string | Reference to DEVICE section |
| `Designator` | "U1", "R1" | Component reference designator |
| `Name` | "+5V", "GND" | Display name (power symbols) |
| `Global Net Name` | "+5V", "GND" | Net assignment for power symbols |
| `Unique ID` | "gge1" | Internal unique ID |
| `Footprint` | UUID/null | PCB footprint reference |
| `Value` | "100nF" | Component value |
| `LCSC Part Name` | string | LCSC library part name |
| `Reuse Block` | null | Reuse block membership |
| `Group ID` | null | Group membership |
| `Channel ID` | null | Multi-channel ID |

### 4.4 WIRE

A wire connection group. Contains one or more LINE segments.

```json
// Header: {"type":"WIRE","ticket":179,"id":"ed87731459a83fb8"}
// Body:
{"zIndex":33}
```

### 4.5 LINE

A line segment within a WIRE group.

```json
// Header: {"type":"LINE","ticket":180,"id":"850608f270531717"}
// Body:
{
  "fillColor": null,
  "fillStyle": null,
  "strokeColor": null,             // null = default green
  "strokeStyle": null,             // null = solid
  "strokeWidth": null,             // null = default
  "startX": 950, "startY": -690,  // Start point
  "endX": 990, "endY": -690,      // End point
  "lineGroup": "ed87731459a83fb8"  // Parent WIRE ID
}
```

### 4.6 WIRE ATTRs

Each WIRE has two standard ATTRs:

**Relevance ATTR** (always present):
```json
{"key": "Relevance", "value": "[]", "parentId": "WIRE_ID", "zIndex": 0}
```

**NET ATTR** (net name label):
```json
{
  "x": 950, "y": -690,           // Label display position
  "rotation": 0,                  // Label text rotation (see coordinate-system.md)
  "value": "USB_DP",              // Net name (empty string "" = unnamed net)
  "keyVisible": false,
  "valueVisible": true,
  "key": "NET",
  "fontSize": 8,                  // Common: 8 (default if null)
  "parentId": "WIRE_ID",
  "zIndex": 2
}
```

## 5. Record Types in SYMBOL Sections

### 5.1 PIN

Defines a pin on a schematic symbol. Coordinates are **relative to symbol origin**.

```json
// Header: {"type":"PIN","ticket":N,"id":"eN"}
// Body:
{
  "partId": "MyComponent.1",
  "groupId": "",
  "locked": false,
  "zIndex": 4,
  "display": true,                // Pin visibility
  "x": -120, "y": -50,           // Relative position from symbol center
  "length": 10,                   // Pin stub length (in schematic units)
  "rotation": 0,                  // 0=points left, 90=points down, 180=points right, 270=points up
  "color": null,
  "pinShape": "NONE"              // Pin shape indicator
}
```

### 5.2 PIN ATTRs

Each PIN has three ATTRs:

```json
{"key": "Pin Name", "value": "P1.11"}     // Functional name
{"key": "Pin Number", "value": "1"}         // Physical pin number
{"key": "Pin Type", "value": "Undefined"}   // Electrical type: Undefined, Power, Input, Output, Bidirectional, Passive
```

### 5.3 Other Symbol Elements

| Type | Description |
|------|-------------|
| `RECT` | Rectangle shape |
| `POLYLINE` | Multi-point line |
| `ARC` | Arc shape |
| `TEXT` | Static text label |
| `ELE_PLACEHOLDER` | Empty placeholder between pins |

## 6. Record Types in DEVICE Sections

DEVICE sections define electrical properties and pin-to-symbol mapping.

```json
// DOCHEAD body includes:
{
  "docType": "DEVICE",
  "uuid": "d73521bbdd2896b2"    // Referenced by COMPONENT's Device ATTR
}
```

## 7. Power Symbol System

### 7.1 Built-in Power Symbols

All use `partId: "pid8a0e77bacb214e"`. Differentiated by Symbol and Device UUIDs + Name ATTR.

**Example Project A UUIDs:**

| Net Type | Symbol UUID | Device UUID |
|----------|-------------|-------------|
| VCC/3V3/+5V (arrow) | `fa489ef6ae369c9a` | `69734524f66a8ada` |
| GND (bar) | `b5fc023152e63698` | `94150318f6d1792d` |

**Example Project B UUIDs (different project, different UUIDs):**

| Net Type | Symbol UUID | Device UUID |
|----------|-------------|-------------|
| GND | `0e264c83e6a9320f` | `0287fff5dce8ab92` |
| VCC (generic) | `a929bab6b41d09cf` | `0f79643fee32371b` |

> **Important**: Power symbol UUIDs are **project-specific**. They are embedded in the
> SYMBOL/DEVICE sections of each epru file. When generating for an existing project,
> extract the UUIDs from the file. When creating from scratch, you need to include
> the SYMBOL and DEVICE section definitions.

### 7.2 Named Power Symbols

Projects may use dedicated partIds for frequently used power nets:
- `GND.1`, `3V3.1`, `VCC.1`, `+5V.1`
- Custom nets: `VBAT.1`, `VCC_IO.1`, etc.

These have their own SYMBOL/DEVICE sections in the epru.

## 8. Generating Valid Records

### 8.1 Ticket Numbering

- Tickets must be globally unique and monotonically increasing within the file
- When appending to an existing file, start from `max_existing_ticket + 1`
- Each record (COMPONENT, ATTR, WIRE, LINE) consumes one ticket

### 8.2 ID Generation

```python
import secrets
new_id = secrets.token_hex(8)  # "ed87731459a83fb8"
```

### 8.3 zIndex

- Components: start from 1, increment per component
- Each component's ATTRs use relative zIndex within the component
- Wires: typically higher zIndex than components (placed on top)
- New elements appended to file should use zIndex > max existing

### 8.4 Minimal WIRE Template

```
{"type":"WIRE","ticket":T1,"id":"WIRE_ID"}||{"zIndex":Z}|
{"type":"LINE","ticket":T2,"id":"LINE_ID"}||{"fillColor":null,"fillStyle":null,"strokeColor":null,"strokeStyle":null,"strokeWidth":null,"startX":X1,"startY":Y1,"endX":X2,"endY":Y2,"lineGroup":"WIRE_ID"}|
{"type":"ATTR","ticket":T3,"id":"REL_ID"}||{"x":null,"y":null,"rotation":null,"color":null,"fontFamily":null,"fontSize":null,"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"[]","keyVisible":null,"valueVisible":null,"key":"Relevance","fillColor":null,"parentId":"WIRE_ID","zIndex":0}|
{"type":"ATTR","ticket":T4,"id":"NET_ID"}||{"x":LX,"y":LY,"rotation":R,"color":null,"fontFamily":null,"fontSize":null,"fontWeight":null,"italic":null,"underline":null,"align":null,"value":"NET_NAME","keyVisible":false,"valueVisible":true,"key":"NET","fillColor":null,"parentId":"WIRE_ID","zIndex":2}|
```

### 8.5 Multi-Segment WIRE

Multiple LINE records can share the same `lineGroup` (WIRE ID).
All segments form one logical wire with a single NET label.

```
{"type":"WIRE",...}||{"zIndex":Z}|
{"type":"LINE",...}||{..."startX":X1,"startY":Y1,"endX":MX,"endY":MY,"lineGroup":"WID"}|
{"type":"LINE",...}||{..."startX":MX,"startY":MY,"endX":X2,"endY":Y2,"lineGroup":"WID"}|
{"type":"ATTR",...}||{..."key":"Relevance",...}|
{"type":"ATTR",...}||{..."key":"NET","value":"NET_NAME",...}|
```

### 8.6 Inserting Records

New records should be inserted **before the BLOB section** (which is always last).
The BLOB section starts with `{"docType":"BLOB"}` in its DOCHEAD.
