# EasyEDA Pro Schematic Drawing Conventions

Learned from analyzing multiple real-world EasyEDA Pro v3.x projects.

## 1. Wiring Conventions

### 1.1 Net Label Wire Stubs

Every net label is attached to a short wire stub extending from a pin endpoint.

**Standard stub lengths:**
- Horizontal pins: **30 units** (for readability) or **5 units** (for tight layouts)
- Vertical pins: **20-30 units**

```
Pin endpoint (465,-525) → wire end (495,-525)  [30-unit horizontal stub]
    add_wire(465, -525, 495, -525, "USB_DP")
```

### 1.2 Direct Pin-to-Pin Wires

When two components are close enough, wire directly without net labels:

```python
# Cap pin to IC pin — direct wire, no label needed
add_wire(615, -480, 610, -480)
```

### 1.3 L-shaped Wires (Two-Segment)

Use L-shaped wires when pins aren't aligned horizontally or vertically:

```python
# Horizontal first, then vertical
add_wire_L(x1, y1, x2, y2, corner="h_first")
# Results in two LINE segments sharing one WIRE group
```

### 1.4 Multi-Segment Wires

A single WIRE can contain multiple LINE entries for complex routing:

```
WIRE id=xxx
  LINE: (250,-440) → (190,-440)       # segment 1
  LINE: (250,-400) → (590,-400)       # segment 2
  LINE: (250,-400) → (250,-440)       # segment 3 (vertical connection)
```

All segments share the same `lineGroup` and NET label.

### 1.5 Net Naming Conventions

| Net Category | Pattern | Example |
|-------------|---------|---------|
| Keyboard rows | ROWn | ROW0, ROW1, ... |
| Keyboard cols | COLn | COL0, COL1, ... |
| USB data | USB_D+, USB_D- | USB_D+, USB_D- |
| I2C | SCL, SDA | SCL, SDA |
| SPI | MOSI, MISO, SCK, CS | SPI_MOSI |
| SWD debug | SWDIO, SWCLK | SWDIO, SWCLK |
| UART | TX, RX | UART_TX, UART_RX |
| Power nets | 3V3, +5V, GND, VBAT | VBAT_LOAD |
| Control signals | descriptive | BL_CTRL, RST, BOOT0 |
| GPIO (Pro Micro style) | Dn | D0, D1, D2, ... |

## 2. Power Symbol Patterns

### 2.1 Built-in Power Symbols

All built-in power symbols use `partId: "pid8a0e77bacb214e"`.

They are differentiated by:
- **Symbol UUID** — arrow (VCC/3V3/+5V) vs bar (GND)
- **Device UUID** — paired with Symbol UUID
- **Name ATTR** — display name ("+5V", "GND", "3V3")
- **Global Net Name ATTR** — actual net assignment

### 2.2 Power Pin Connection Pattern

Power symbols always connect via a short wire stub:

```python
# VCC pin → 3V3 power symbol (placed left of pin)
add_power(pin_x - 20, pin_y, "3V3")
add_wire(pin_x - 20, pin_y, pin_x, pin_y)

# GND pin → GND symbol (placed below pin)
add_power(pin_x, pin_y + 10, "GND")
add_wire(pin_x, pin_y + 10, pin_x, pin_y)
```

### 2.3 Power Symbol Rotation

| Symbol Type | Typical Rotation | Visual Direction |
|-------------|-----------------|------------------|
| VCC/3V3/+5V | 90 | Arrow points left (toward IC) |
| GND | 270 | Bar points down |

> Note: Rotation can vary based on placement context. See `coordinate-system.md`.

### 2.4 Named Power Symbols

Projects may define dedicated partIds for frequently used power nets:
- `GND.1`, `3V3.1`, `VCC.1`, `+5V.1`
- Custom: `VBAT.1`, `VCC_IO.1`, etc.

These have their own SYMBOL/DEVICE sections in the epru file.

## 3. Decoupling Capacitor Patterns

### 3.1 Placement Rules

- One **100nF** (0603) per VCC pin, placed adjacent to IC
- One **10uF** (0805) bulk cap per power rail entry point
- One **1uF** near LDO output
- Charger IC: input cap + output cap per datasheet
- DC-DC converter: input/output caps + inductor per datasheet

### 3.2 Cap Connection Pattern

Caps are placed vertically near the IC, with short direct wires:

```
  3V3 ──┬── IC.VCC
        │
       [C] 100nF
        │
       GND
```

In EasyEDA source:
```python
# C placed at (x, y), rotation=90 (vertical)
# Pin 1 at top → power net
# Pin 2 at bottom → GND

# Power rail to cap pin 1
add_wire(cap_pin1_x, cap_pin1_y, ic_vcc_x, ic_vcc_y)
# Cap pin 2 to GND
add_power(cap_pin2_x, cap_pin2_y + 10, "GND")
add_wire(cap_pin2_x, cap_pin2_y, cap_pin2_x, cap_pin2_y + 10)
```

### 3.3 Typical Decoupling Requirements

| Component Type | Cap | Value | Purpose |
|---------------|-----|-------|---------|
| MCU VCC | C_VCC | 100nF + 10uF | Module decoupling |
| MCU DC-DC | C_DCH | 100nF | DC-DC decoupling |
| Charger input | C_CHG_IN | 4.7uF | Charger input filtering |
| Charger output | C_CHG_OUT | 4.7uF | Battery-side filtering |
| LDO input | C_LDO_IN | 1uF | LDO input |
| LDO output | C_LDO_OUT | 1uF-10uF + 100nF | LDO output stability |

## 4. Keyboard Matrix Conventions

### 4.1 Matrix Symbol

The keyboard matrix can be encapsulated as a single custom symbol.
Pins exposed: R0-Rn (rows), C0-Cm (columns).

Inside the symbol, each key switch is a momentary switch + diode:
```
COLn ──[Switch]──┤>|──── ROWn
                  (diode)
```

### 4.2 Matrix-to-MCU Net Labels

Keyboard matrix pins connect to MCU GPIOs via net labels:

```python
# Keyboard symbol ROW pins → ROW net labels
add_wire(kb_row0_x, kb_row0_y, kb_row0_x - 30, kb_row0_y, "ROW0")

# MCU GPIO pins → same ROW net labels
add_wire(mcu_gpio_x, mcu_gpio_y, mcu_gpio_x + 30, mcu_gpio_y, "ROW0")
```

## 5. Component Placement Style

### 5.1 Spacing

- ICs: 100-200 units apart
- Caps near IC: 20-30 units from IC pin
- Power symbols: 10-20 units from wire junction
- Net labels: start at pin endpoint, extend 5-30 units

### 5.2 Rotation Conventions

| Component | Default Rotation | Notes |
|-----------|-----------------|-------|
| IC/Module | 0 | Pins as designed |
| Resistor horizontal | 0 | Pin1 left, Pin2 right |
| Resistor vertical | 90 | Pin1 top, Pin2 bottom |
| Capacitor horizontal | 0 | |
| Capacitor vertical | 90 | Pin1 top, Pin2 bottom |
| Power symbol VCC/+5V | 90 | Arrow points left |
| Power symbol GND | 270 | Bar points down |
| LED | 0 | Anode left/right per symbol |

## 6. Schematic Page Organization

For complex projects, organize by function:
- Page 1: Main MCU + peripheral connections
- Page 2: Secondary ICs (USB hub, keyboard matrix)
- Page 3: Power management (DC-DC, LDO, battery charger)
- Additional pages: LCD, connectors, debug, etc.

For simple projects, one page with grouped areas:
- Top-left: USB-C + ESD
- Center: MCU/BLE module
- Right: Power (charger, LDO, switch)
- Bottom-right: Debug (SWD), LEDs, test points
