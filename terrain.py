"""
Pixel-Art Terrain Generator (Stage 1)
-------------------------------------
Generates a top-down pixel-art map from a few settings.

Requirements:  pip install numpy pillow
Run:           python terrain.py
Output:        map.png

How it works:
  1. Build a HEIGHTMAP: a grid of numbers (0 to 1) where each number is the
     elevation at that spot. We make it with "fractal value noise".
  2. (Optional) Shape it into an island by lowering the edges.
  3. COLOR each cell by its height using a small pixel-art palette.
  4. SCALE the image up with nearest-neighbor so the pixels stay crisp.

Later, Lambda will call generate_map(settings) and the AI will fill in the
settings from the user's text description.
"""

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# 1. NOISE
# ---------------------------------------------------------------------------

def _hash(ix, iy, seed):
    """Turn integer grid coordinates + seed into a repeatable random 0..1 value.
    Same inputs always give the same output, so the same seed = same world."""
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFF) / 0xFFFF


def _smooth(t):
    """Smoothstep curve so blending between grid points looks soft, not blocky."""
    return t * t * (3 - 2 * t)


def value_noise(x, y, seed):
    """Smooth random noise at WORLD coordinates x, y (NumPy arrays).
    Picks random values at whole-number grid corners and blends between them."""
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    tx = _smooth(x - x0)
    ty = _smooth(y - y0)

    # Random values at the 4 corners around each point
    v00 = _hash(x0,     y0,     seed)
    v10 = _hash(x0 + 1, y0,     seed)
    v01 = _hash(x0,     y0 + 1, seed)
    v11 = _hash(x0 + 1, y0 + 1, seed)

    # Blend left-right, then top-bottom
    top = v00 + (v10 - v00) * tx
    bottom = v01 + (v11 - v01) * tx
    return top + (bottom - top) * ty


def fractal_noise(x, y, seed, octaves=5, roughness=0.5):
    """Stack several layers ("octaves") of noise.
    Big, slow layers make continents; small, fast layers add detail.
    roughness controls how strong the small details are (0 = smooth, 1 = jagged)."""
    total = np.zeros_like(x, dtype=float)
    amplitude = 1.0
    frequency = 1.0
    max_total = 0.0
    for i in range(octaves):
        total += value_noise(x * frequency, y * frequency, seed + i * 101) * amplitude
        max_total += amplitude
        amplitude *= roughness
        frequency *= 2
    return total / max_total  # keep result between 0 and 1


# ---------------------------------------------------------------------------
# 2. HEIGHTMAP
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
    ys, xs = np.mgrid[0:height_cells, 0:width]
    world_x = (xs + offset_x) / size * zoom
    world_y = (ys + offset_y) / size * zoom

    height = fractal_noise(world_x, world_y, settings["seed"],
                           octaves=5, roughness=settings["roughness"])

    if settings["shape"] == "world":
        # A second, much bigger and slower layer groups the land into a few
        # large continents with open ocean between them.
        continents = fractal_noise(world_x / 4, world_y / 4, settings["seed"] + 500,
                                   octaves=3, roughness=0.5)
        height = height * 0.4 + continents * 0.6

    # Stretch so values use the full 0..1 range
    height = (height - height.min()) / (height.max() - height.min())

    # 0 in the middle of the map, 1 at the edges (an oval for wide maps)
    center_x = (width - 1) / 2
    center_y = (height_cells - 1) / 2
    dx = (xs - center_x) / center_x
    dy = (ys - center_y) / center_y

    if settings["shape"] == "island":
        # Island: push everything down the farther it is from the middle
        dist = np.sqrt(dx ** 2 + dy ** 2)
        height = height * np.clip(1 - dist ** 2, 0, 1)
        height = height / height.max()  # rescale so the highest point is 1 again
    elif settings["shape"] == "world":
        # World: keep the land in the middle, but only sink a thin border
        # so the map is framed by ocean and continents don't get cut off.
        edge = np.maximum(np.abs(dx), np.abs(dy))      # 0 middle, 1 at any edge
        border = np.clip((1 - edge) / 0.12, 0, 1)      # fades over the outer 12%
        height = height * _smooth(border)
        height = height / height.max()

    # Mountain height: >1 makes peaks taller/more common, <1 flattens the land
    height = height ** (1 / settings["mountain_height"])
    return height


# ---------------------------------------------------------------------------
# 3. COLORING (pixel-art palette)
# ---------------------------------------------------------------------------

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
    img = np.zeros((*height.shape, 3), dtype=np.uint8)

    # Height bands, from lowest to highest. Land bands are spaced
    # evenly between the water level and the top.
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
        mask = (height > lower) & (height <= upper)
        img[mask] = PALETTE[name]
        lower = upper

    # Pixel-art touch: sprinkle darker "trees" on some grass cells
    rng = np.random.default_rng(settings["seed"])
    grass_mask = (img == PALETTE["grass"]).all(axis=2)
    trees = grass_mask & (rng.random(height.shape) < 0.08)
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
    wobble = fractal_noise(xs / 20, ys / 20, settings["seed"] + 7, octaves=3) - 0.5
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
    return -(-width // tile), -(-height_cells // tile)   # round up


def cut_tile(pixels, settings):
    """Cut one tile out of the full map.
    The WHOLE map is always generated first and then cut, so the edges of
    neighboring tiles line up perfectly (same coastlines, same trees)."""
    tile = settings["tile_size"]
    left = settings["tile_x"] * tile
    top = settings["tile_y"] * tile
    return pixels[top:top + tile, left:left + tile]


def generate_map(settings=None):
    """Main function: settings in, PIL Image out.
    This is the function Lambda calls."""
    s = {**DEFAULT_SETTINGS, **(settings or {})}
    height = make_heightmap(s)
    pixels = color_map(height, s)
    if s["tile_x"] is not None and s["tile_y"] is not None:
        pixels = cut_tile(pixels, s)
    img = Image.fromarray(np.ascontiguousarray(pixels), "RGB")
    # NEAREST keeps the pixels sharp and blocky (pixel-art look)
    rows, cols = pixels.shape[:2]
    return img.resize((cols * s["scale"], rows * s["scale"]), Image.NEAREST)


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
