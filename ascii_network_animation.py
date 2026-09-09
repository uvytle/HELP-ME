"""Create an animated GIF showing a panopticon becoming a network."""

import math
import os
import random
import struct

WIDTH, HEIGHT = 320, 320
FRAME_DELAY = 6  # GIF delay in hundredths of a second

# A small fixed palette keeps the GIF encoder dependency-free.
PALETTE = [
    (8, 12, 24),       # 0 background
    (20, 35, 65),      # 1 dim connection
    (35, 75, 125),     # 2 connection
    (45, 150, 210),    # 3 blue
    (50, 205, 170),    # 4 teal
    (100, 220, 120),   # 5 green
    (235, 220, 75),    # 6 yellow
    (255, 165, 55),    # 7 orange
    (245, 85, 80),     # 8 red
    (210, 80, 220),    # 9 purple
    (245, 245, 245),   # 10 white
    (125, 145, 175),   # 11 gray
    (70, 90, 120),     # 12 blue gray
    (175, 225, 245),   # 13 pale blue
    (255, 205, 120),   # 14 pale orange
    (255, 255, 255),   # 15 bright white
]
GIF_PALETTE = [(0, 0, 0)] * 15 + [(255, 255, 255)]


def blank_frame():
    return [bytearray([0]) * WIDTH for _ in range(HEIGHT)]


def pixel(frame, x, y, color):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        frame[y][x] = color


def line(frame, x1, y1, x2, y2, color):
    """Draw a clipped integer line."""
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    error = dx - dy
    while True:
        pixel(frame, x1, y1, color)
        if x1 == x2 and y1 == y2:
            break
        twice = 2 * error
        if twice > -dy:
            error -= dy
            x1 += sx
        if twice < dx:
            error += dx
            y1 += sy


def disc(frame, cx, cy, radius, color):
    radius_squared = radius * radius
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius_squared:
                pixel(frame, x, y, color)


def circle_points(cx, cy, radius_x, radius_y, count):
    """Return points for a visually circular ring in terminal output."""
    return [(int(round(cx + radius_x * math.cos(2 * math.pi * i / count))),
             int(round(cy + radius_y * math.sin(2 * math.pi * i / count))))
            for i in range(count)]


def central_frame(frame_number, thinning=False):
    frame = blank_frame()
    center = (WIDTH // 2, HEIGHT // 2 + 5)
    nodes = circle_points(center[0], center[1], 68, 68, 12)
    active = (frame_number // 2) % len(nodes)
    rng = random.Random(frame_number + 90)

    for index, point in enumerate(nodes):
        visible = not thinning or rng.random() > 0.35
        if visible:
            line(frame, center[0], center[1], point[0], point[1],
                 4 if index == active else (2 if thinning else 1))
        disc(frame, point[0], point[1], 5,
             14 if index == active else (3 if thinning else 5))

    disc(frame, center[0], center[1], 13, 8 if not thinning else 7)
    disc(frame, center[0], center[1], 7, 15)
    return frame


def blend_frames(first, second, amount):
    """Crossfade two indexed-color frames using the fixed palette."""
    # Only 256 palette-index pairs are possible. Cache each conversion once
    # instead of searching the palette for every one of the 64,000 pixels.
    conversions = {}
    frame = blank_frame()
    for y in range(HEIGHT):
        first_row = first[y]
        second_row = second[y]
        output_row = frame[y]
        for x in range(WIDTH):
            pair = (first_row[x], second_row[x])
            color = conversions.get(pair)
            if color is None:
                first_color = PALETTE[pair[0]]
                second_color = PALETTE[pair[1]]
                target = tuple(int(first_color[channel] * (1 - amount) +
                                   second_color[channel] * amount)
                               for channel in range(3))
                color = min(
                    range(len(PALETTE)),
                    key=lambda index: sum(
                        (PALETTE[index][channel] - target[channel]) ** 2
                        for channel in range(3)))
                conversions[pair] = color
            output_row[x] = color
    return frame


def append_crossfade(frames, first, second, steps):
    """Append an eased crossfade without duplicating the starting frame."""
    for step in range(1, steps + 1):
        progress = step / float(steps)
        eased = progress * progress * (3.0 - 2.0 * progress)
        frames.append(blend_frames(first, second, eased))


def network_positions(count, seed):
    rng = random.Random(seed)
    return [[rng.randrange(30, WIDTH - 30), rng.randrange(35, HEIGHT - 25)]
            for _ in range(count)]


def network_frame(frame_number, mature=False):
    count = 24 if mature else 15
    positions = network_positions(count, 17 if mature else 13)
    edges = [(index, random.Random(index * 31 + 4).randrange(index))
             for index in range(1, count)]

    for index, point in enumerate(positions):
        if not mature and index < 4:
            continue
        point[0] += int(5 * math.sin(frame_number * 0.16 + index))
        point[1] += int(3 * math.cos(frame_number * 0.19 + index))

    frame = blank_frame()
    degrees = [0] * count
    for first, second in edges:
        degrees[first] += 1
        degrees[second] += 1
        line(frame, positions[first][0], positions[first][1],
             positions[second][0], positions[second][1], 1 if mature else 2)

    maximum = max(degrees) or 1
    labels = [3, 6, 8, 9]  # data, algorithm, permissions, behavior
    for index, point in enumerate(positions):
        if not mature and index < 4:
            color = labels[index]
            radius = 8
        else:
            color = 10 if degrees[index] * 2 >= maximum else 13
            radius = 5 if mature else 4
        disc(frame, point[0], point[1], radius, color)
        disc(frame, point[0], point[1], max(2, radius - 3), 15)
    return frame


def lzw_pixels(frame):
    """Encode pixels as valid, deliberately simple GIF LZW data."""
    clear, end = 16, 17
    codes = []
    for row in frame:
        for value in row:
            codes.extend((clear, value))
    codes.append(end)

    # The clear code resets the dictionary, so all codes remain five bits.
    data = bytearray()
    accumulator = 0
    bits = 0
    for code in codes:
        accumulator |= code << bits
        bits += 5
        while bits >= 8:
            data.append(accumulator & 255)
            accumulator >>= 8
            bits -= 8
    if bits:
        data.append(accumulator & 255)
    return bytes(data)


def subblocks(data):
    result = bytearray()
    for start in range(0, len(data), 255):
        chunk = data[start:start + 255]
        result.append(len(chunk))
        result.extend(chunk)
    result.append(0)
    return bytes(result)


def write_gif(frames, path):
    """Write indexed frames as a looping GIF without external packages."""
    output = bytearray(b'GIF89a')
    output.extend(struct.pack('<HH', WIDTH, HEIGHT))
    output.extend((0xF3, 0, 0))  # global table, 16 colors, no sorting
    output.extend(bytes(channel for color in GIF_PALETTE for channel in color))

    # Loop forever so the animation can be viewed directly in a browser.
    output.extend(b'!\xFF\x0B' + b'NETSCAPE2.0' +
                  bytes((3, 1)) + struct.pack('<H', 0) + bytes((0,)))
    for frame in frames:
        ascii_pixels = ascii_gif_frame(frame)
        output.extend(b'!\xF9\x04\x00')
        output.extend(struct.pack('<H', FRAME_DELAY))
        output.extend(b'\x00\x00')
        output.extend(b',')
        output.extend(struct.pack('<HHHH', 0, 0, WIDTH, HEIGHT))
        output.append(0)  # use the global color table
        output.append(4)  # minimum LZW code size
        output.extend(subblocks(lzw_pixels(ascii_pixels)))
    output.append(0x3B)
    with open(path, 'wb') as gif_file:
        gif_file.write(output)


def ascii_frame(frame, block_width=4, block_height=4):
    """Convert a pixel frame into compact terminal-friendly ASCII art."""
    shades = ' .:-=+*#%$@'
    rows = []
    for top in range(0, HEIGHT, block_height):
        row = []
        for left in range(0, WIDTH, block_width):
            brightness = 0
            samples = 0
            for y in range(top, min(top + block_height, HEIGHT)):
                for x in range(left, min(left + block_width, WIDTH)):
                    red, green, blue = PALETTE[frame[y][x]]
                    brightness += (red * 3 + green * 6 + blue) // 10
                    samples += 1
            level = brightness // max(1, samples)
            row.append(shades[min(len(shades) - 1, level * len(shades) // 256)])
        rows.append(''.join(row).rstrip())
    return '\n'.join(rows)


ASCII_GLYPHS = {
    '.': ('00000', '00000', '00000', '00000', '00100', '00100', '00000'),
    ':': ('00000', '00100', '00100', '00000', '00100', '00100', '00000'),
    '-': ('00000', '00000', '00000', '01110', '00000', '00000', '00000'),
    '=': ('00000', '00000', '01110', '00000', '01110', '00000', '00000'),
    '+': ('00000', '00100', '00100', '01110', '00100', '00100', '00000'),
    '*': ('00000', '10101', '01110', '11111', '01110', '10101', '00000'),
    '#': ('01010', '11111', '01010', '01010', '11111', '01010', '00000'),
    '%': ('11000', '11001', '00010', '00100', '01000', '10011', '00011'),
    '$': ('00100', '01111', '10100', '01110', '00101', '11110', '00100'),
    '@': ('01110', '10001', '10111', '10101', '10111', '10000', '01111'),
}


def ascii_gif_frame(frame, block_width=8, block_height=8):
    """Render the same ASCII shades as a raster frame for the GIF."""
    result = blank_frame()
    for row_index, row in enumerate(ascii_frame(
            frame, block_width, block_height).splitlines()):
        for column_index, character in enumerate(row):
            if character == ' ':
                continue
            glyph = ASCII_GLYPHS[character]
            color = 15  # monochrome GIF: white glyphs on a black background
            origin_x = column_index * block_width + 1
            origin_y = row_index * block_height
            for glyph_y, glyph_row in enumerate(glyph):
                for glyph_x, filled in enumerate(glyph_row):
                    if filled == '1':
                        pixel(result, origin_x + glyph_x, origin_y + glyph_y,
                              color)
    return result


def main():
    frames = []
    for frame_number in range(20):
        frames.append(central_frame(frame_number))

    append_crossfade(frames, frames[-1], central_frame(0, thinning=True), 32)
    for frame_number in range(1, 20):
        frames.append(central_frame(frame_number, thinning=True))

    append_crossfade(frames, frames[-1], network_frame(0, mature=False), 64)

    for frame_number in range(1, 25):
        frames.append(network_frame(frame_number, mature=False))

    # Grow the network gradually instead of switching to the mature layout
    # in one frame, which would relocate many ASCII characters at once.
    growth_start = frames[-1]
    growth_end = network_frame(0, mature=True)
    append_crossfade(frames, growth_start, growth_end, 64)

    for frame_number in range(1, 30):
        frames.append(network_frame(frame_number, mature=True))

    # Make the loop itself continuous instead of jumping from the network
    # back to the first panopticon frame.
    append_crossfade(frames, frames[-1], central_frame(0), 64)

    display_frames = frames
    output_path = os.path.join(os.path.dirname(__file__), 'panopticon_network.gif')
    write_gif(frames, output_path)
    print('Saved GIF to {}'.format(output_path))
    print('\x1b[2J\x1b[H', end='')
    for index, frame in enumerate(display_frames):
        print('\x1b[HFrame {}/{}'.format(index + 1, len(display_frames)))
        print(ascii_frame(frame, block_width=8, block_height=8), end='', flush=True)
        import time
        time.sleep(FRAME_DELAY / 100.0)


if __name__ == '__main__':
    main()
