# dxf-to-gcode

Turns a DXF drawing into G-code for a pen plotter built on an **Ender 3 V3 SE**
(pen clamped where the nozzle was; Z axis lifts/lowers the pen).

## Install & run

```
pip install ezdxf
python dxf_to_gcode.py drawing.dxf --fit --center
```

That writes `drawing.gcode` next to the DXF. Copy it to the printer's SD card and print it.
Useful options: `--z-down`, `--z-up`, `--draw-speed`, `--units`, `--flip-y`,
`--manual-z` (see `--help`).

## What it handles
LINE, ARC, CIRCLE, ELLIPSE, SPLINE, LWPOLYLINE/POLYLINE (incl. arc bulges), and blocks
(INSERT) — curves are flattened to short segments. TEXT/POINT are skipped (explode text to
curves in your CAD program first). Strokes are reordered nearest-neighbour to cut pen-up travel.
Layers/colors are ignored: everything is drawn with one pen.

## Pen setup (do this once)
1. Mount the pen so the tip is a few mm below where the nozzle tip was, spring-loaded if possible.
2. Remove/raise nothing else; heaters are turned off by the G-code.
3. **Z heights.** The script does a normal `G28` (the CR Touch probes the bed centre), then
   uses Z = **14.0 mm** with the pen on the paper (work) and **17.0 mm** with it lifted
   (travel). Change them with `--z-down` / `--z-up`; lower `--z-down` a fraction of a mm to
   press harder. Make sure the pen can't hit the bed anywhere, including the probe point at
   the bed centre. `--manual-z` homes X/Y only and treats the Z at start as the travel height.
4. **Pen offset.** The pen sits 1.75" to the right of and 1.25" toward the front of the nozzle
   (built in as `--pen-offset-x 44.45 --pen-offset-y -31.75`). All coordinates in the G-code
   are shifted so the *pen* lands where the drawing says. Because the nozzle can't leave the
   bed, the pen can only reach X 44.4–220 and Y 0–188 mm; the drawing area defaults to that
   region minus a 5 mm margin. Measure your real offset and change the two values if it differs.
5. Tape the paper down inside that reachable area.

## Draw the outer edge of the usable area
```
python dxf_to_gcode.py --perimeter
```
Writes `pen_perimeter.gcode`: a rectangle around the furthest the pen can reach (X 44.45–220,
Y 0–188.25 mm with the default offset). Handy for checking paper placement and the pen offset.
`--perimeter-inset 3` pulls it in 3 mm if the carriage bumps its limits at the very edge.

## Setup pause
Every file starts by moving the pen to the front-left corner of the reachable area, lowering it
onto the paper, and pausing (`M0`). Use that time to change the speed % or nudge Z from the
printer's menu, then click to start. `--no-pause` skips it.
