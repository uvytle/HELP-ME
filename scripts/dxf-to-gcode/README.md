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
`--pause-for-paper`, `--home-z` (see `--help`).

## What it handles
LINE, ARC, CIRCLE, ELLIPSE, SPLINE, LWPOLYLINE/POLYLINE (incl. arc bulges), and blocks
(INSERT) — curves are flattened to short segments. TEXT/POINT are skipped (explode text to
curves in your CAD program first). Strokes are reordered nearest-neighbour to cut pen-up travel.
Layers/colors are ignored: everything is drawn with one pen.

## Pen setup (do this once)
1. Mount the pen so the tip is a few mm below where the nozzle tip was, spring-loaded if possible.
2. Remove/raise nothing else; heaters are turned off by the G-code.
3. By default the script homes **X/Y only** and treats the Z height at start as pen-up (`Z5`),
   because the V3 SE homes Z with the CR Touch probe, which isn't meant for a pen. Before
   starting: use the printer menu to move Z so the pen is ~5 mm above the paper, then start.
   Tune `--z-down` (default `0` = 5 mm lower than start) until the pen just touches; negative
   values press harder. Or pass `--home-z` to use a normal `G28` instead.
4. Tape the paper down. The default drawing area is X/Y 10–210 mm of the 220 mm bed.
