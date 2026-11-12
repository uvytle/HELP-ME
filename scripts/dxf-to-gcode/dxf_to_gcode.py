#!/usr/bin/env python3
"""Convert a DXF drawing into G-code for a pen plotter built on an Ender 3 V3 SE.

The pen replaces the hotend. "Pen up / pen down" is done with the Z axis, so no
servo or extra hardware is needed. No heaters are turned on and nothing extrudes.

Usage:
    python dxf_to_gcode.py drawing.dxf                 # writes drawing.gcode
    python dxf_to_gcode.py drawing.dxf -o out.gcode

Run with --help for all options. See README.md for pen setup.
"""
import argparse
import math
import sys
from pathlib import Path

try:
    import ezdxf
    from ezdxf import disassemble
    from ezdxf.path import make_path
except ImportError:
    sys.exit("Missing dependency. Install it with:  pip install ezdxf")

# $INSUNITS code -> millimetres per drawing unit
UNIT_TO_MM = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 8: 0.0254}

# Ender 3 V3 SE bed is 220 x 220 mm.
BED = 220.0

# The pen is physically 1.75" right of and 1.25" toward the front of the nozzle, but the
# bed plate has been moved to compensate. So the pen at nozzle (0, 0) is the bottom-left
# (0, 0) of the usable paper area, and no software offset is needed (default 0). If the
# plate is ever put back, pass --pen-offset-x 44.45 --pen-offset-y -31.75 instead.
PEN_OFFSET_X = 0.0
PEN_OFFSET_Y = 0.0

# Usable plate area, mm, measured from the bottom-left corner (0, 0).
WORK_W = 185.0
WORK_H = 220.0


def collect_polylines(msp, flatten_dist):
    """Return a list of polylines ([(x, y), ...], is_closed) in drawing units.

    recursive_decompose explodes INSERT (blocks), hatches' edges, dimensions, etc.
    into plain primitives; make_path + flattening turns arcs, circles, ellipses,
    splines and polylines (incl. bulges) into straight segments.
    """
    out = []
    for e in disassemble.recursive_decompose(msp):
        try:
            path = make_path(e)
        except TypeError:
            continue  # TEXT, POINT, etc. - not drawable as strokes
        for sub in path.sub_paths():
            pts = [(v.x, v.y) for v in sub.flattening(flatten_dist)]
            if len(pts) >= 2:
                closed = math.dist(pts[0], pts[-1]) < 1e-6
                out.append((pts, closed))
    return out


def bounds(polys):
    xs = [p[0] for pl, _ in polys for p in pl]
    ys = [p[1] for pl, _ in polys for p in pl]
    return min(xs), min(ys), max(xs), max(ys)


def transform(polys, scale, dx, dy):
    return [([(x * scale + dx, y * scale + dy) for x, y in pl], c) for pl, c in polys]


def order_polylines(polys, start=(0.0, 0.0)):
    """Greedy nearest-neighbour ordering to cut pen-up travel. Open paths may be
    reversed; closed paths are left alone (the pen just starts at one end).

    Endpoints live in a coarse grid so each lookup only scans nearby cells; a plain
    scan of every stroke per step is far too slow for drawings with 10k+ strokes."""
    n = len(polys)
    if n == 0:
        return []
    xs = [p[0] for pl, _ in polys for p in (pl[0], pl[-1])]
    ys = [p[1] for pl, _ in polys for p in (pl[0], pl[-1])]
    x0, y0 = min(xs), min(ys)
    w, h = max(xs) - x0, max(ys) - y0
    cell = max(math.sqrt(max(w * h, 1e-9) / n) * 2, 1e-3, max(w, h) / 2000)
    gx, gy = int(w / cell) + 1, int(h / cell) + 1

    grid = {}
    for i, (pl, closed) in enumerate(polys):
        ends = [(pl[0], False)] if closed else [(pl[0], False), (pl[-1], True)]
        for (x, y), rev in ends:
            grid.setdefault((int((x - x0) / cell), int((y - y0) / cell)), []).append((i, rev, x, y))

    used = [False] * n
    ordered = []
    cur = start
    rmax = max(gx, gy)
    for _ in range(n):
        cx = min(max(int((cur[0] - x0) / cell), 0), gx - 1)
        cy = min(max(int((cur[1] - y0) / cell), 0), gy - 1)
        best = None
        best_d = float("inf")
        r = 0
        while r <= rmax:
            if best is not None and best_d <= (r - 1) * cell:
                break
            if r == 0:
                cells = [(cx, cy)]
            else:
                cells = ([(cx + dx, cy + dy) for dx in range(-r, r + 1) for dy in (-r, r)]
                         + [(cx + dx, cy + dy) for dy in range(-r + 1, r) for dx in (-r, r)])
            for key in cells:
                lst = grid.get(key)
                if not lst:
                    continue
                lst[:] = [e for e in lst if not used[e[0]]]
                for i, rev, x, y in lst:
                    d = math.hypot(cur[0] - x, cur[1] - y)
                    if d < best_d:
                        best, best_d = (i, rev), d
            r += 1
        i, rev = best
        used[i] = True
        pl, closed = polys[i]
        if rev:
            pl = pl[::-1]
        ordered.append((pl, closed))
        cur = pl[-1]
    return ordered


def nozzle_xy(x, y, args):
    """Convert a wanted pen-tip position to the nozzle position the printer must go to."""
    return x - args.pen_offset_x, y - args.pen_offset_y


def pen_reachable(args):
    """(x0, y0, x1, y1) of the usable pen area: the work area, trimmed to where the
    nozzle can actually go (0..BED) once any software pen offset is applied."""
    return (max(0.0, args.pen_offset_x), max(0.0, args.pen_offset_y),
            min(args.work_w, BED + args.pen_offset_x), min(args.work_h, BED + args.pen_offset_y))


def write_reference_dxf(path, rect):
    """Reference drawing in mm: the usable pen rectangle, bottom-left at (0, 0)."""
    doc = ezdxf.new("R2010")
    doc.units = 4  # millimetres
    doc.header["$MEASUREMENT"] = 1
    doc.layers.add("PEN_DRAWABLE_AREA", color=1)
    msp = doc.modelspace()
    x0, y0, x1, y1 = rect
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                       dxfattribs={"layer": "PEN_DRAWABLE_AREA"})
    doc.saveas(path)


def heaters_off(w):
    """Hotend and bed to 0 C (and fan off) so nothing warms or warps the paper."""
    w("M104 S0 ; hotend off\n")
    w("M140 S0 ; bed off\n")
    w("M107 ; fan off\n")


def write_gcode(polys, args, out):
    w = out.write
    w("; Pen plotter G-code generated by dxf_to_gcode.py\n")
    w(f"; pen up Z={args.z_up}  pen down Z={args.z_down}  draw F={args.draw_speed}  travel F={args.travel_speed}\n")
    w("G21 ; millimetres\n")
    w("G90 ; absolute positioning\n")
    heaters_off(w)
    if not args.manual_z:
        w("G28 ; home all axes (Z uses the probe, so the bed centre is probed)\n")
    else:
        w("G28 X Y ; home X/Y only\n")
        w("M211 S0 ; software endstops off so Z can go below the assumed start height\n")
        w(f"G92 Z{args.z_up} ; ASSUMES the pen was manually lowered/raised to the pen-up height before starting\n")
    w(f"G0 Z{args.z_up} F{args.z_speed} ; pen up\n")
    if not args.no_pause:
        # Park the pen on the front-left corner of the area it can reach, touching the
        # paper, and wait so speed and Z height can be tuned from the printer's menu.
        rx0, ry0, _, _ = pen_reachable(args)
        px, py = nozzle_xy(rx0, ry0, args)
        w(f"G0 X{px:.3f} Y{py:.3f} F{args.travel_speed} ; front-left corner for setup\n")
        w(f"G1 Z{args.z_down} F{args.z_speed} ; pen down so you can check the height\n")
        w("M0 Adjust speed and Z height, then click to start\n")
        w(f"G0 Z{args.z_up} F{args.z_speed} ; pen up\n")

    pen_down = False
    pos = None
    for pl, closed in polys:
        x0, y0 = pl[0]
        if pos is None or math.dist(pos, (x0, y0)) > args.join_tol:
            if pen_down:
                w(f"G0 Z{args.z_up} F{args.z_speed}\n")
                pen_down = False
            nx, ny = nozzle_xy(x0, y0, args)
            w(f"G0 X{nx:.3f} Y{ny:.3f} F{args.travel_speed}\n")
        if not pen_down:
            w(f"G1 Z{args.z_down} F{args.z_speed}\n")
            pen_down = True
            w(f"F{args.draw_speed}\n")
        for x, y in pl[1:]:
            nx, ny = nozzle_xy(x, y, args)
            w(f"G1 X{nx:.3f} Y{ny:.3f}\n")
        pos = pl[-1]

    w(f"G0 Z{args.z_up} F{args.z_speed} ; pen up\n")
    w(f"G0 X0 Y{BED - 20:.0f} F{args.travel_speed} ; park out of the way\n")
    heaters_off(w)
    w("M84 ; motors off\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dxf", nargs="?", help="input DXF (not needed with --perimeter)")
    ap.add_argument("--perimeter", action="store_true",
                    help="no DXF: draw a rectangle around the outermost area the pen can reach")
    ap.add_argument("--perimeter-inset", type=float, default=0.0,
                    help="pull the --perimeter rectangle in by this many mm (default 0 = the very edge)")
    ap.add_argument("-o", "--output", help="output .gcode (default: next to the DXF)")
    ap.add_argument("--units", choices=["auto", "mm", "cm", "in", "ft", "m"], default="auto",
                    help="DXF drawing units. auto = read from file, assume mm if unset")
    ap.add_argument("--scale", type=float, default=1.0, help="extra scale factor (default 1)")
    ap.add_argument("--fit", action="store_true", help="scale down (never up) to fit the drawing area")
    ap.add_argument("--center", action="store_true", help="centre the drawing in the drawing area")
    ap.add_argument("--work-w", type=float, default=WORK_W, help="usable width from the bottom-left, mm (default 185)")
    ap.add_argument("--work-h", type=float, default=WORK_H, help="usable height from the bottom-left, mm (default 220)")
    ap.add_argument("--pen-offset-x", type=float, default=PEN_OFFSET_X,
                    help="software correction: pen tip is this many mm RIGHT of the nozzle. Default 0 "
                         "because the bed plate was moved to compensate (physical offset is 44.45 = 1.75in)")
    ap.add_argument("--pen-offset-y", type=float, default=PEN_OFFSET_Y,
                    help="software correction: pen tip is this many mm BEHIND the nozzle (negative = toward "
                         "the front). Default 0, see above (physical offset is -31.75 = 1.25in)")
    ap.add_argument("--origin-x", type=float, help="drawing area left edge, mm (default: reachable area + 5)")
    ap.add_argument("--origin-y", type=float, help="drawing area front edge, mm (default: reachable area + 5)")
    ap.add_argument("--area-w", type=float, help="drawing area width, mm (default: reachable area - 10)")
    ap.add_argument("--area-h", type=float, help="drawing area height, mm (default: reachable area - 10)")
    ap.add_argument("--z-up", type=float, default=17.0, help="Z travel height, pen lifted (default 17)")
    ap.add_argument("--z-down", type=float, default=14.0,
                    help="Z work height, pen on paper (default 14; lower it a fraction of a mm to press harder)")
    ap.add_argument("--draw-speed", type=int, default=2000, help="drawing feedrate mm/min (default 2000)")
    ap.add_argument("--travel-speed", type=int, default=6000, help="pen-up feedrate mm/min (default 6000)")
    ap.add_argument("--z-speed", type=int, default=600, help="Z feedrate mm/min (default 600)")
    ap.add_argument("--flatten", type=float, default=0.05,
                    help="max curve error in mm when approximating arcs/splines (default 0.05)")
    ap.add_argument("--join-tol", type=float, default=0.05,
                    help="don't lift the pen if the next stroke starts within this many mm (default 0.05)")
    ap.add_argument("--manual-z", action="store_true",
                    help="home X/Y only and treat the Z height at start as --z-up (default: full G28, which "
                         "probes Z at the bed centre)")
    ap.add_argument("--no-pause", action="store_true",
                    help="skip the setup pause at the front-left corner before drawing starts")
    ap.add_argument("--flip-y", action="store_true", help="mirror Y (if your drawing comes out upside-down)")
    args = ap.parse_args()

    rx0, ry0, rx1, ry1 = pen_reachable(args)

    if args.perimeter:
        i = args.perimeter_inset
        x0, y0, x1, y1 = rx0 + i, ry0 + i, rx1 - i, ry1 - i
        polys = [([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], True)]
        out_path = Path(args.output) if args.output else Path("pen_perimeter.gcode")
        with open(out_path, "w", newline="\n") as f:
            write_gcode(polys, args, f)
        print(f"Wrote {out_path}: rectangle X {x0:.2f}-{x1:.2f}, Y {y0:.2f}-{y1:.2f} mm "
              f"({x1 - x0:.1f} x {y1 - y0:.1f})")
        dxf_path = out_path.with_suffix(".dxf")
        write_reference_dxf(dxf_path, (x0, y0, x1, y1))
        print(f"Wrote {dxf_path}: same rectangle, in millimetres")
        return

    if not args.dxf:
        ap.error("give a DXF file, or use --perimeter")
    doc = ezdxf.readfile(args.dxf)
    if args.units == "auto":
        mm_per_unit = UNIT_TO_MM.get(doc.header.get("$INSUNITS", 0), 1.0)
    else:
        mm_per_unit = {"mm": 1.0, "cm": 10.0, "in": 25.4, "ft": 304.8, "m": 1000.0}[args.units]

    polys = collect_polylines(doc.modelspace(), args.flatten / mm_per_unit)
    if not polys:
        sys.exit("No drawable geometry found in the DXF (text and points are skipped).")

    if args.flip_y:
        polys = [([(x, -y) for x, y in pl], c) for pl, c in polys]

    margin = 0.0
    if args.origin_x is None:
        args.origin_x = rx0 + margin
    if args.origin_y is None:
        args.origin_y = ry0 + margin
    if args.area_w is None:
        args.area_w = rx1 - rx0 - 2 * margin
    if args.area_h is None:
        args.area_h = ry1 - ry0 - 2 * margin

    scale = mm_per_unit * args.scale
    minx, miny, maxx, maxy = bounds(polys)
    w, h = (maxx - minx) * scale, (maxy - miny) * scale
    if args.fit and (w > args.area_w or h > args.area_h):
        scale *= min(args.area_w / w, args.area_h / h)
        w, h = (maxx - minx) * scale, (maxy - miny) * scale
    ox = args.origin_x + ((args.area_w - w) / 2 if args.center else 0)
    oy = args.origin_y + ((args.area_h - h) / 2 if args.center else 0)
    polys = transform(polys, scale, ox - minx * scale, oy - miny * scale)

    fx0, fy0, fx1, fy1 = bounds(polys)
    if fx0 < rx0 - 1e-6 or fy0 < ry0 - 1e-6 or fx1 > rx1 + 1e-6 or fy1 > ry1 + 1e-6:
        sys.exit(f"Drawing ({fx1 - fx0:.1f} x {fy1 - fy0:.1f} mm) is outside the area the pen can reach "
                 f"(X {rx0:.1f}-{rx1:.1f}, Y {ry0:.1f}-{ry1:.1f} mm, because of the pen offset). "
                 "Use --fit or --scale.")

    polys = order_polylines(polys)
    out_path = Path(args.output) if args.output else Path(args.dxf).with_suffix(".gcode")
    with open(out_path, "w", newline="\n") as f:
        write_gcode(polys, args, f)

    print(f"Pen can reach X {rx0:.1f}-{rx1:.1f}, Y {ry0:.1f}-{ry1:.1f} mm (offset X{args.pen_offset_x:+.2f} Y{args.pen_offset_y:+.2f})")
    print(f"Wrote {out_path}: {len(polys)} strokes, drawing {fx1 - fx0:.1f} x {fy1 - fy0:.1f} mm "
          f"at X{fx0:.1f}-{fx1:.1f} Y{fy0:.1f}-{fy1:.1f}")


if __name__ == "__main__":
    main()

