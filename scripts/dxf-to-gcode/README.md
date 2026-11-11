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
4. **Pen offset & work area.** The pen sits 1.75" right of and 1.25" toward the front of the
   nozzle, but the bed plate was moved to compensate, so the software offset is 0: the pen at
   nozzle (0, 0) is the bottom-left (0, 0) of the paper area, and the usable area is
   **185 × 220 mm** (`--work-w`, `--work-h`). The drawing area defaults to that minus a 5 mm
   margin. If the plate is ever moved back, use `--pen-offset-x 44.45 --pen-offset-y -31.75`.
5. Tape the paper down inside that reachable area.

## Draw the outer edge of the usable area
```
python dxf_to_gcode.py --perimeter
```
Writes `pen_perimeter.gcode`: a rectangle around the full usable area, (0, 0) to (185, 220) mm.
Handy for checking paper placement. `--perimeter-inset 3` pulls it in 3 mm if the carriage bumps
its limits at the very edge.

It also writes `pen_perimeter.dxf` (millimetres, bottom-left at (0, 0)): one layer,
`PEN_DRAWABLE_AREA`, the 185 x 220 rectangle. Open it in CAD as a reference to design inside.

## Setup pause
Every file starts by moving the pen to the front-left corner (0, 0), lowering it onto the
paper, and pausing (`M0`). Use that time to change the speed % or nudge Z from the printer's
menu, then click to start. `--no-pause` skips it.
