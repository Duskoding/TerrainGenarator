"""
Pixel-Art Terrain Generator
---------------------------
Generates a top-down pixel-art map from a few settings.

Requirements:  pip install numpy pillow
Run:           python terrain.py
Output:        map.png

How it works:
  1. Build a HEIGHTMAP: a grid of numbers (0 to 1) where each number is the
     elevation at that spot. We make it with "fractal value noise"
     (see section 1 below for what noise is).
  2. SHAPE it: an island (edges lowered into ocean), a continent (no change),
     or a world (big continents, ocean border).
  3. COLOR each cell by its height using a small pixel-art palette.
  4. SCALE the image up with nearest-neighbor so the pixels stay crisp.

lambda_function.py calls generate_map(settings) to serve maps on AWS Lambda.
"""

# NumPy lets us do math on a whole grid of numbers at once, instead of looping
# over every cell one by one. That is what makes this fast enough for Lambda.
import numpy as np
# Pillow (PIL) turns our grid of colors into a real image file (PNG).
from PIL import Image


# ---------------------------------------------------------------------------
# 1. NOISE
# ---------------------------------------------------------------------------
#
# WHAT IS NOISE?
#
# To make terrain we need "random" heights. But plain random numbers make
# TV static: every cell has nothing to do with its neighbor, so you would get
# a map of colored sprinkles, not hills and lakes.
#
#   Plain random (static):       Noise (smooth random):
#   9 1 7 2 8 0                  2 3 4 5 5 4
#   0 8 3 9 1 6                  3 4 5 6 6 5
#   7 2 9 0 5 3                  3 4 6 7 6 5
#
# NOISE is random numbers that change SMOOTHLY: cells next to each other have
# similar values, but over a longer distance the values drift up and down
# unpredictably. Real landscapes are like that: the ground right next to you
# is about the same height as where you stand, but a mile away it could be a
# valley or a mountain. That is why games (Minecraft and many others) use
# noise to build their worlds.
#
# There are several kinds of noise (Perlin, simplex, value...). We use the
# simplest one, VALUE NOISE, made in two steps:
#
#   Step 1: Imagine a grid of points at whole numbers (0, 1, 2, 3...).
#           Give every grid point a random height from 0 to 1.
#
#   Step 2: For any spot BETWEEN grid points, blend the heights of the
#           4 nearest grid points. The closer you are to a point, the more
#           its height counts. This blending is what makes it smooth.
#
#        0.2 ---------- 0.9         A spot halfway between all four corners
#         |              |          gets roughly their average (about 0.5).
#         |      *       |          A spot right next to the 0.9 corner gets
#         |              |          a value close to 0.9.
#        0.4 ---------- 0.6
#
# One layer of value noise gives smooth, blobby hills. Real terrain also has
# small bumps on top of big shapes, so we stack several layers (OCTAVES):
#
#   Layer 1: big, slow waves        -> continents and oceans
#   Layer 2: smaller, faster waves  -> hills and bays
#   Layer 3+: tiny, fast wiggles    -> rocky details and jagged coastlines
#
# Each new layer is twice as detailed and (with roughness 0.5) half as strong,
# so the small details decorate the big shapes instead of drowning them out.
# Stacked noise like this is called FRACTAL NOISE.
#
# The SEED is what makes it "random but repeatable": the random heights at
# the grid points are calculated from the seed, so the same seed always
# builds the same world, and a different seed builds a different one.
# ---------------------------------------------------------------------------

def _hash(ix, iy, seed):
    """Turn integer grid coordinates + seed into a repeatable random 0..1 value.
    Same inputs always give the same output, so the same seed = same world.

    This is how we give every grid point its "random height" (step 1 above)
    without storing a giant table of random numbers: we scramble the
    coordinates with math, and the scrambled result looks random."""
    # Multiply each input by a big, odd "magic" number and add them together.
    # Different numbers for x, y, and seed keep (1, 2) and (2, 1) from
    # giving the same answer. "& 0xFFFFFFFF" keeps only the lowest 32 bits,
    # so the number wraps around instead of growing forever.
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    # Mix the bits: shift them right and XOR (^) them back in, then multiply
    # again. Each step spreads a small change in the input across the whole
    # number, so neighboring grid points get totally unrelated values.
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    # Keep the lowest 16 bits (0..65535) and divide to get a value from 0 to 1.
    return (h & 0xFFFF) / 0xFFFF


def _smooth(t):
    """Smoothstep curve so blending between grid points looks soft, not blocky.

    t goes from 0 to 1 as you move from one grid point to the next.
    Plain blending (using t as is) leaves visible sharp corners at every grid
    line. Smoothstep starts slow, speeds up in the middle, and slows down
    again at the end, which hides the grid:

        t:          0.0   0.25   0.5   0.75   1.0
        smooth(t):  0.0   0.16   0.5   0.84   1.0
    """
    return t * t * (3 - 2 * t)


def value_noise(x, y, seed):
    """Smooth random noise at WORLD coordinates x, y (NumPy arrays).
    Picks random values at whole-number grid corners and blends between them.

    x and y are whole grids of coordinates, so this calculates the noise for
    every cell of the map at once."""
    # Find the grid square each point is in: the top-left corner is the
    # point's coordinates rounded down (e.g. x = 3.7 -> corner x0 = 3).
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    # How far across the square the point is, from 0 (left/top edge) to
    # 1 (right/bottom edge), passed through smoothstep to hide the grid lines.
    tx = _smooth(x - x0)
    ty = _smooth(y - y0)

    # Random values at the 4 corners around each point
    v00 = _hash(x0,     y0,     seed)   # top-left
    v10 = _hash(x0 + 1, y0,     seed)   # top-right
    v01 = _hash(x0,     y0 + 1, seed)   # bottom-left
    v11 = _hash(x0 + 1, y0 + 1, seed)   # bottom-right

    # Blend left-right, then top-bottom.
    # "a + (b - a) * t" slides from a (when t = 0) to b (when t = 1).
    top = v00 + (v10 - v00) * tx          # blend along the top edge
    bottom = v01 + (v11 - v01) * tx       # blend along the bottom edge
    return top + (bottom - top) * ty      # blend between those two results


def fractal_noise(x, y, seed, octaves=5, roughness=0.5):
    """Stack several layers ("octaves") of noise.
    Big, slow layers make continents; small, fast layers add detail.
    roughness controls how strong the small details are (0 = smooth, 1 = jagged)."""
    total = np.zeros_like(x, dtype=float)   # running sum, starts at 0 everywhere
    amplitude = 1.0     # how much this layer counts (its "strength")
    frequency = 1.0     # how zoomed-in this layer is (its "detail")
    max_total = 0.0     # the highest the sum could possibly be
    for i in range(octaves):
        # Multiplying the coordinates by frequency squeezes more grid squares
        # into the same space = smaller, more detailed features.
        # Each layer uses a different seed (seed + i * 101) so the layers
        # don't all have their hills in the same places.
        total += value_noise(x * frequency, y * frequency, seed + i * 101) * amplitude
        max_total += amplitude
        amplitude *= roughness   # next layer is weaker (half as strong at 0.5)
        frequency *= 2           # ...and twice as detailed
    # Dividing by the biggest possible sum keeps the result between 0 and 1,
    # no matter how many octaves we used.
    return total / max_total


# ---------------------------------------------------------------------------
# 2. HEIGHTMAP
# ---------------------------------------------------------------------------
#
# A heightmap is a grid with one number per cell: how high the ground is.
# 0 is the deepest ocean floor and 1 is the highest mountain peak.
# Later, section 3 turns those numbers into colors.
# ---------------------------------------------------------------------------

def map_dimensions(settings):
    """Width and height of the map in cells.
    Island and continent maps are square (size x size). A world map is twice
    as wide as it is tall, like a real world map, unless width/height are given."""
    size = settings["size"]
    if settings["shape"] == "world":
        default_w, default_h = size * 4, size * 2
    else:
        default_w, default_h = size, size
    # "a or b" means: use a, unless a is None (or 0), then use b.
    return settings.get("width") or default_w, settings.get("height") or default_h


def make_heightmap(settings):
    """Create the grid of elevations (0 = deepest, 1 = highest)."""
    size = settings["size"]
    zoom = settings["zoom"]            # how many noise "features" fit across `size` cells
    offset_x = settings.get("offset_x", 0)   # world position (used for tiles later)
    offset_y = settings.get("offset_y", 0)
    width, height_cells = map_dimensions(settings)

    # World coordinates for every pixel. Because noise uses WORLD coordinates,
    # neighboring maps (tiles) will line up perfectly when we expand later.
    # Dividing by `size` (not width) means a wider map shows MORE land
    # instead of stretching the same land.
    #
    # np.mgrid makes two grids the size of the map: ys holds each cell's row
    # number and xs holds each cell's column number.
    ys, xs = np.mgrid[0:height_cells, 0:width]
    # Convert cell numbers to noise coordinates. With size 128 and zoom 4,
    # the map spans noise coordinates 0 to 4, so the biggest noise layer has
    # about 4 hills/valleys across the map. Higher zoom = more, smaller features.
    world_x = (xs + offset_x) / size * zoom
    world_y = (ys + offset_y) / size * zoom

    # The main terrain: 5 layers of noise, from big shapes to small details.
    height = fractal_noise(world_x, world_y, settings["seed"],
                           octaves=5, roughness=settings["roughness"])

    if settings["shape"] == "world":
        # A second, much bigger and slower layer groups the land into a few
        # large continents with open ocean between them.
        # Dividing the coordinates by 4 "zooms out" this layer, so its
        # features are 4 times bigger than the main terrain's.
        continents = fractal_noise(world_x / 4, world_y / 4, settings["seed"] + 500,
                                   octaves=3, roughness=0.5)
        # Mix them: 60% continent shape, 40% detailed terrain.
        height = height * 0.4 + continents * 0.6

    # Stretch so values use the full 0..1 range.
    # Stacked noise rarely reaches exactly 0 or 1 (it bunches up around 0.5),
    # so we move the lowest value to 0 and the highest to 1. Otherwise there
    # would be no deep ocean and no snowy peaks.
    height = (height - height.min()) / (height.max() - height.min())

    # 0 in the middle of the map, 1 at the edges (an oval for wide maps)
    center_x = (width - 1) / 2
    center_y = (height_cells - 1) / 2
    dx = (xs - center_x) / center_x     # -1 at the left edge, +1 at the right
    dy = (ys - center_y) / center_y     # -1 at the top edge, +1 at the bottom

    if settings["shape"] == "island":
        # Island: push everything down the farther it is from the middle
        dist = np.sqrt(dx ** 2 + dy ** 2)   # distance from the center (0 to ~1.4)
        # (1 - dist^2) is 1 in the middle and drops to 0 at the edges.
        # Multiplying by it keeps the middle tall and sinks the edges into ocean.
        height = height * np.clip(1 - dist ** 2, 0, 1)
        height = height / height.max()  # rescale so the highest point is 1 again
    elif settings["shape"] == "world":
        # World: keep the land in the middle, but only sink a thin border
        # so the map is framed by ocean and continents don't get cut off.
        edge = np.maximum(np.abs(dx), np.abs(dy))      # 0 middle, 1 at any edge
        border = np.clip((1 - edge) / 0.12, 0, 1)      # fades over the outer 12%
        height = height * _smooth(border)
        height = height / height.max()
    # "continent" shape: no change, the land runs right off the edges.

    # Mountain height: >1 makes peaks taller/more common, <1 flattens the land.
    # Raising numbers between 0 and 1 to a power bends them without changing
    # 0 or 1: e.g. 0.5 ** (1 / 2) = 0.71 (raised up), 0.5 ** (1 / 0.5) = 0.25
    # (pushed down).
    height = height ** (1 / settings["mountain_height"])
    return height


# ---------------------------------------------------------------------------
# 3. COLORING (pixel-art palette)
# ---------------------------------------------------------------------------

# Each terrain type and its color as (red, green, blue), each from 0 to 255.
PALETTE = {
    "deep_water":    (32, 60, 140),
    "shallow_water": (58, 110, 200),
    "sand":          (230, 210, 140),
    "grass":         (90, 180, 70),
    "forest":        (40, 120, 50),
    "rock":          (120, 110, 100),
    "snow":          (245, 245, 250),
    "ice":           (215, 235, 245),
}


def color_map(height, settings):
    """Pick a palette color for each cell based on its height."""
    water = settings["water_level"]
    # An empty image: one (red, green, blue) color for every cell, all black.
    img = np.zeros((*height.shape, 3), dtype=np.uint8)

    # Height bands, from lowest to highest. Land bands are spaced
    # evenly between the water level and the top.
    # Each entry means "cells up to this height get this color".
    # Example with water_level 0.4 (so land = 0.6):
    #   0.00 - 0.24  deep water
    #   0.24 - 0.40  shallow water
    #   0.40 - 0.44  sand (a thin beach along every coast)
    #   0.44 - 0.64  grass
    #   0.64 - 0.79  forest
    #   0.79 - 0.91  rock
    #   0.91 - 1.00  snow
    land = 1 - water
    bands = [
        (water * 0.6,          "deep_water"),
        (water,                "shallow_water"),
        (water + land * 0.06,  "sand"),
        (water + land * 0.40,  "grass"),
        (water + land * 0.65,  "forest"),
        (water + land * 0.85,  "rock"),
        (1.01,                 "snow"),
    ]

    lower = -1
    for upper, name in bands:
        # mask is a grid of True/False: True for every cell in this band.
        # img[mask] = color paints all of those cells at once.
        mask = (height > lower) & (height <= upper)
        img[mask] = PALETTE[name]
        lower = upper

    # Pixel-art touch: sprinkle darker "trees" on some grass cells
    # The random generator is seeded too, so the trees are in the same
    # places every time you use the same seed.
    rng = np.random.default_rng(settings["seed"])
    grass_mask = (img == PALETTE["grass"]).all(axis=2)   # True where the cell is grass
    trees = grass_mask & (rng.random(height.shape) < 0.08)   # 8% of grass cells
    img[trees] = PALETTE["forest"]

    # World maps get frozen poles at the top and bottom
    if settings["shape"] == "world":
        add_ice_caps(img, height, settings)

    return img


def add_ice_caps(img, height, settings):
    """Cover the top and bottom of a world map in ice, like the poles.
    The edge of the ice is wobbly (using noise) so it looks natural."""
    rows, cols = height.shape
    ys, xs = np.mgrid[0:rows, 0:cols]
    latitude = np.abs(ys - (rows - 1) / 2) / ((rows - 1) / 2)   # 0 equator, 1 pole
    # Noise again! Without it the ice edge would be a perfectly straight line.
    # Subtracting 0.5 makes the wobble go both ways (-0.5 to +0.5).
    wobble = fractal_noise(xs / 20, ys / 20, settings["seed"] + 7, octaves=3) - 0.5
    # Ice wherever we are close enough to a pole (the wobble moves the line
    # up and down a little along the way).
    ice = latitude + wobble * 0.25 > 0.88
    img[ice] = PALETTE["ice"]


# ---------------------------------------------------------------------------
# 4. PUT IT TOGETHER
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "seed": 4821,           # same seed = same map
    "size": 128,            # map is size x size cells (small = chunky pixels)
    "scale": 4,             # each cell becomes a scale x scale block in the image
    "zoom": 4,              # bigger = more, smaller features
    "water_level": 0.40,    # 0..1, how much of the map is water
    "mountain_height": 1.0, # 0.5 = flat, 1 = normal, 2 = very mountainous
    "roughness": 0.5,       # 0..1, how jagged the terrain is
    "shape": "island",      # "island", "continent", or "world"
    "width": None,          # world maps only: cells across (default size * 4)
    "height": None,         # world maps only: cells tall (default size * 2)
    "tile_x": None,         # set tile_x and tile_y to get just one tile of the map
    "tile_y": None,         #   (column, row), counting from 0 at the top left
    "tile_size": 64,        # each tile is tile_size x tile_size cells
}


def tile_grid(settings):
    """How many tiles fit across and down the map: (columns, rows)."""
    width, height_cells = map_dimensions(settings)
    tile = settings["tile_size"]
    # -(-a // b) divides and rounds UP, so a partial tile at the edge still
    # counts as a tile (plain a // b would round down and drop it).
    return -(-width // tile), -(-height_cells // tile)


def cut_tile(pixels, settings):
    """Cut one tile out of the full map.
    The WHOLE map is always generated first and then cut, so the edges of
    neighboring tiles line up perfectly (same coastlines, same trees)."""
    tile = settings["tile_size"]
    left = settings["tile_x"] * tile    # first column of the tile, in cells
    top = settings["tile_y"] * tile     # first row of the tile, in cells
    # [rows, columns] slicing: take tile_size rows and tile_size columns.
    return pixels[top:top + tile, left:left + tile]


def generate_map(settings=None):
    """Main function: settings in, PIL Image out.
    This is the function Lambda calls."""
    # Start from the defaults, then replace any setting the caller gave us.
    s = {**DEFAULT_SETTINGS, **(settings or {})}
    height = make_heightmap(s)        # step 1 + 2: heights
    pixels = color_map(height, s)     # step 3: colors
    if s["tile_x"] is not None and s["tile_y"] is not None:
        pixels = cut_tile(pixels, s)  # only keep the requested tile
    # Pillow needs the pixel data in one continuous block of memory, which a
    # cut-out tile isn't, so ascontiguousarray makes a tidy copy first.
    img = Image.fromarray(np.ascontiguousarray(pixels), "RGB")
    # NEAREST keeps the pixels sharp and blocky (pixel-art look)
    # (other resize methods would blur the colors together).
    rows, cols = pixels.shape[:2]
    return img.resize((cols * s["scale"], rows * s["scale"]), Image.NEAREST)


# This part only runs when you run this file directly (python terrain.py),
# not when another file (like lambda_function.py) imports it.
if __name__ == "__main__":
    # Try changing these! (Later, the AI will choose them from a description.)
    my_settings = {
        "seed": 4821,
        "water_level": 0.40,
        "mountain_height": 1.2,
        "roughness": 0.5,
        "shape": "island",
    }
    image = generate_map(my_settings)
    image.save("map.png")
    print("Saved map.png")
