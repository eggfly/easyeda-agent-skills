# EasyEDA Pro Coordinate System & Rotation Reference

## 1. Coordinate System

### 1.1 Axes

- **X-axis**: positive = right
- **Y-axis**: positive = down (in internal coordinates)
- **Editor display**: Y is inverted — negative Y values appear **upward** in the GUI
- **Origin**: typically (0, 0), configurable via CANVAS record

### 1.2 Units

All coordinates are in **EasyEDA schematic units** (1 unit = 10 mil = 0.254mm).
Common grid snap: 10 units.

## 2. Component Rotation

### 2.1 Rotation Values

Components support four rotation values: `0`, `90`, `180`, `270` (degrees, counterclockwise).

### 2.2 Pin Absolute Position Calculation

To compute a pin's absolute position from its relative position within a SYMBOL:

```python
def pin_abs_position(comp_x, comp_y, comp_rotation, pin_rel_x, pin_rel_y):
    """
    comp_x, comp_y: COMPONENT x, y
    comp_rotation: COMPONENT rotation (0, 90, 180, 270)
    pin_rel_x, pin_rel_y: PIN x, y from SYMBOL section
    """
    if comp_rotation == 0:
        return (comp_x + pin_rel_x, comp_y + pin_rel_y)
    elif comp_rotation == 90:
        return (comp_x - pin_rel_y, comp_y + pin_rel_x)
    elif comp_rotation == 180:
        return (comp_x - pin_rel_x, comp_y - pin_rel_y)
    elif comp_rotation == 270:
        return (comp_x + pin_rel_y, comp_y - pin_rel_x)
```

### 2.3 Mirror Transform

When `isMirror: true`, apply X-flip before rotation:

```python
if is_mirror:
    pin_rel_x = -pin_rel_x
# Then apply rotation as above
```

## 3. PIN Rotation (in SYMBOL sections)

PIN rotation indicates the direction the pin **points toward** (away from the component body):

| Rotation | Pin Points | Wire Connects From |
|----------|-----------|-------------------|
| 0 | Left | Left side |
| 90 | Down | Below |
| 180 | Right | Right side |
| 270 | Up | Above |

## 4. Net Label Rotation

### 4.1 Statistical Analysis

Based on analysis of ~960 net labels across multiple real-world projects:

**Horizontal wires (Y1 == Y2):**
- `rotation: 0` — **98.6%** of cases (846/858)
- `rotation: 90` — 1.4% (rare exceptions)

**Vertical wires (X1 == X2):**
- `rotation: 0` — **59%** (53/90) — text reads horizontally
- `rotation: 90` — **41%** (37/90) — text reads along wire

### 4.2 Recommended Defaults

| Wire Direction | Label Rotation | Notes |
|---------------|---------------|-------|
| Horizontal | 0 | Almost always correct |
| Vertical | 0 | Most common; text reads horizontally |
| Vertical (alternative) | 90 | Text aligned with wire direction |

### 4.3 Label Placement Relative to Wire

The NET label position (`x`, `y` in the NET ATTR) should be at one endpoint of the wire,
typically the endpoint **away from the pin** (i.e., the free end of the stub).

```
Pin ─────── Label
(start)     (end, label position)
```

For horizontal wires extending right: label at `(endX, endY)`
For horizontal wires extending left: label at `(startX, startY)` (whichever is the free end)

## 5. Text Alignment

### 5.1 Alignment Values

The `align` field in ATTR records uses compound values:

```
{HORIZONTAL}_{VERTICAL}
```

**Horizontal**: `LEFT`, `CENTER`, `RIGHT`
**Vertical**: `TOP`, `MIDDLE`, `BOTTOM`

Common combinations:
- `LEFT_BOTTOM` — default for most labels
- `LEFT_TOP`
- `CENTER_MIDDLE` — centered text
- `RIGHT_BOTTOM` — right-aligned

### 5.2 Alignment Context

| Element | Typical Alignment |
|---------|------------------|
| Designator (U1, R1) | `LEFT_BOTTOM` |
| Value (100nF) | `LEFT_BOTTOM` |
| Net label | `LEFT_BOTTOM` or `null` (default) |
| Pin Name | varies by pin direction |

## 6. Font Sizes

### 6.1 Statistical Distribution

Based on analysis of net labels:
- `fontSize: 8` — **59.5%** (most common for net labels)
- `fontSize: null` — **32.6%** (uses editor default, typically ~10)
- `fontSize: 10` — **5.2%**
- Other sizes — rare

### 6.2 Recommended Defaults

| Element | fontSize |
|---------|---------|
| Net label | 8 |
| Designator | null (default) |
| Component value | null (default) |
| Pin name/number | null (default) |

## 7. NET Label Visibility

### 7.1 Standard Configuration

Based on analysis of ~960 net labels:

```json
{
  "keyVisible": false,    // 90.8% use false — hides "NET" prefix
  "valueVisible": true    // Shows the actual net name
}
```

### 7.2 Empty Net Names

Unnamed nets use `"value": ""` (empty string). These are typically direct
pin-to-pin connections that don't need a visible label.

## 8. Power Symbol Rotation Patterns

### 8.1 GND Symbols

GND symbol rotation varies by placement context:

| Rotation | Usage | Frequency |
|----------|-------|-----------|
| 90 | GND to the right of pin | Common |
| 0 | GND below pin (standard) | Common |
| 270 | GND to the left of pin | Less common |
| 180 | GND above pin (rare) | Rare |

### 8.2 VCC/+5V/3V3 Symbols

| Rotation | Usage | Frequency |
|----------|-------|-----------|
| 90 | Arrow pointing left (toward IC) | Most common |
| 270 | Arrow pointing right | Less common |
| 0 | Arrow pointing up | Occasional |
| 180 | Arrow pointing down | Rare |

## 9. Common Coordinate Patterns

### 9.1 Component Grid

Components are typically placed on a 10-unit grid:
- X: multiples of 10 (e.g., 350, 500, 650)
- Y: multiples of 10 (e.g., -550, -600, -700)

### 9.2 Wire Endpoints

Wires always connect at pin endpoints, which are also on the 10-unit grid.
Non-grid-aligned wires will cause DRC warnings in EasyEDA Pro.
