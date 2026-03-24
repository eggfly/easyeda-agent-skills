#!/usr/bin/env python3
"""
Fetch component data from LCSC / EasyEDA APIs.

Retrieves:
- Component specs and parameters from LCSC
- Datasheet PDF URL
- Schematic symbol data (pin names, numbers, positions)
- Footprint data

Usage:
    python3 lcsc_fetch.py C668215              # Show component info
    python3 lcsc_fetch.py C668215 --pins       # Show pin map
    python3 lcsc_fetch.py C668215 --datasheet  # Download datasheet PDF
    python3 lcsc_fetch.py C668215 --json       # Full JSON output
    python3 lcsc_fetch.py --search "RT9080"    # Search components
"""

import json
import sys
import os
import argparse
import math
import urllib.request
import urllib.parse
import urllib.error

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
}


def api_get(url, params=None):
    """Make a GET request and return parsed JSON."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {url}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def search_components(keyword, page_size=10):
    """Search for components on EasyEDA Pro."""
    data = api_get("https://pro.easyeda.com/api/eda/product/search", {
        "keyword": keyword, "type": 3, "page": 1, "pageSize": page_size
    })
    if not data or "result" not in data:
        return []
    return data["result"].get("productList", [])


def get_lcsc_detail(lcsc_code):
    """Get detailed component info from LCSC."""
    data = api_get("https://wmsc.lcsc.com/ftps/wm/product/detail", {
        "productCode": lcsc_code
    })
    if not data or "result" not in data:
        return None
    return data["result"]


def get_easyeda_component(lcsc_code):
    """Get EasyEDA symbol/footprint data (v6 format)."""
    data = api_get(f"https://easyeda.com/api/products/{lcsc_code}/components", {
        "version": "6.5.44"
    })
    if not data or not data.get("success"):
        return None
    return data.get("result")


def parse_v6_pins(shapes):
    """Parse v6 format pin shapes into structured pin data.

    Returns list of dicts: {number, name, x, y, rotation, elec_type}
    """
    pins = []
    for s in shapes:
        if not s.startswith("P~"):
            continue
        parts = s.split("^^")
        if len(parts) < 5:
            continue

        # Part[0]: P~show~elec~spice_pin~x~y~rotation~id~locked
        header = parts[0].split("~")
        if len(header) < 7:
            continue

        pin_x = float(header[4])
        pin_y = float(header[5])
        pin_rot = int(header[6]) if header[6] else 0

        # Part[3]: visibility~tx~ty~trot~name~anchor~~~color
        name_parts = parts[3].split("~")
        pin_name = name_parts[4] if len(name_parts) > 4 else ""

        # Part[4]: visibility~tx~ty~trot~number~anchor~~~color
        num_parts = parts[4].split("~")
        pin_number = num_parts[4] if len(num_parts) > 4 else ""

        pins.append({
            "number": pin_number,
            "name": pin_name,
            "x": pin_x,
            "y": pin_y,
            "rotation": pin_rot,
        })

    return pins


def parse_v6_origin(head):
    """Get symbol origin from v6 head."""
    return head.get("x", 0), head.get("y", 0)


def pins_to_relative(pins, origin_x, origin_y):
    """Convert absolute v6 pin positions to relative (for epru SYMBOL)."""
    result = []
    for p in pins:
        result.append({
            **p,
            "rel_x": p["x"] - origin_x,
            "rel_y": p["y"] - origin_y,
        })
    return result


def download_datasheet(pdf_url, output_path):
    """Download datasheet PDF."""
    req = urllib.request.Request(pdf_url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(output_path, "wb") as f:
                f.write(data)
            return len(data)
    except Exception as e:
        print(f"Download error: {e}", file=sys.stderr)
        return 0


def print_search_results(products):
    """Print search results table."""
    print(f"{'LCSC':<14s} {'MPN':<22s} {'Mfr':<15s} {'Package':<14s} {'Stock':>8s}  {'Price':>8s}")
    print("-" * 90)
    for p in products:
        price = p.get("price", [[0, "?"]])[0]
        price_str = f"${price[1]}" if len(price) > 1 else "?"
        print(f"{p.get('number','?'):<14s} {p.get('mpn','?'):<22s} "
              f"{p.get('manufacturer','?'):<15s} {p.get('package','?'):<14s} "
              f"{p.get('stockNumber', p.get('stock', '?')):>8}  {price_str:>8s}")


def print_component_info(detail, eda_data=None):
    """Print component info summary."""
    print(f"Part: {detail.get('productModel', '?')} ({detail.get('productCode', '?')})")
    print(f"Manufacturer: {detail.get('brandNameEn', '?')}")
    print(f"Package: {detail.get('encapStandard', '?')}")
    print(f"Description: {detail.get('productNameEn', '?')}")
    print(f"Stock: {detail.get('stockNumber', '?')}")
    print(f"Datasheet: {detail.get('pdfUrl', 'N/A')}")

    params = detail.get("paramVOList", [])
    if params:
        print(f"\nParameters:")
        for p in params:
            val = p.get("paramValueEn", "-")
            if val and val != "-":
                print(f"  {p.get('paramNameEn', '?'):<30s} {val}")

    if eda_data:
        shapes = eda_data.get("dataStr", {}).get("shape", [])
        pins = parse_v6_pins(shapes)
        if pins:
            origin = parse_v6_origin(eda_data.get("dataStr", {}).get("head", {}))
            pins_rel = pins_to_relative(pins, origin[0], origin[1])
            print(f"\nPins ({len(pins)}):")
            print(f"  {'#':<6s} {'Name':<12s} {'RelX':>6s} {'RelY':>6s} {'Rot':>5s}")
            print(f"  {'-'*38}")
            for p in sorted(pins_rel, key=lambda x: int(x["number"]) if x["number"].isdigit() else 0):
                print(f"  {p['number']:<6s} {p['name']:<12s} {p['rel_x']:>6.0f} {p['rel_y']:>6.0f} {p['rotation']:>5d}")


def main():
    parser = argparse.ArgumentParser(description="Fetch LCSC/EasyEDA component data")
    parser.add_argument("code", nargs="?", help="LCSC part code (e.g., C668215)")
    parser.add_argument("--search", "-s", help="Search keyword")
    parser.add_argument("--pins", action="store_true", help="Show pin map")
    parser.add_argument("--datasheet", action="store_true", help="Download datasheet PDF")
    parser.add_argument("--json", action="store_true", help="Full JSON output")
    parser.add_argument("--output", "-o", help="Output directory for downloads")
    args = parser.parse_args()

    if args.search:
        products = search_components(args.search)
        if not products:
            print("No results found.")
            return
        print_search_results(products)
        return

    if not args.code:
        parser.print_help()
        return

    lcsc_code = args.code.upper()
    if not lcsc_code.startswith("C"):
        lcsc_code = "C" + lcsc_code

    # Fetch data
    print(f"Fetching {lcsc_code}...", file=sys.stderr)
    detail = get_lcsc_detail(lcsc_code)
    eda_data = get_easyeda_component(lcsc_code)

    if not detail:
        print(f"Component {lcsc_code} not found on LCSC.", file=sys.stderr)
        return

    if args.json:
        output = {
            "lcsc": detail,
            "eda": eda_data,
        }
        if eda_data:
            shapes = eda_data.get("dataStr", {}).get("shape", [])
            pins = parse_v6_pins(shapes)
            origin = parse_v6_origin(eda_data.get("dataStr", {}).get("head", {}))
            output["pins"] = pins_to_relative(pins, origin[0], origin[1])
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    if args.datasheet:
        pdf_url = detail.get("pdfUrl")
        if not pdf_url:
            print("No datasheet URL available.", file=sys.stderr)
            return
        out_dir = args.output or "."
        out_path = os.path.join(out_dir, f"{lcsc_code}.pdf")
        size = download_datasheet(pdf_url, out_path)
        if size:
            print(f"Downloaded {out_path} ({size} bytes)")
        return

    print_component_info(detail, eda_data)


if __name__ == "__main__":
    main()
