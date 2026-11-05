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

def make_heightmap(settings):
    """Create the grid of elevations (0 = deepest, 1 = highest)."""
    size = settings["size"]
    zoom = settings["zoom"]            # how many noise "features" fit across the map
    offset_x = settings.get("offset_x", 0)   # world position (used for tiles later)
    offset_y = settings.get("offset_y", 0)

    # World coordinates for every pixel. Because noise uses WORLD coordinates,
    # neighboring maps (tiles) will line up perfectly when we expand later.
    ys, xs = np.mgrid[0:size, 0:size]
    world_x = (xs + offset_x) / size * zoom
    world_y = (ys + offset_y) / size * zoom

    height = fractal_noise(world_x, world_y, settings["seed"],
                           octaves=5, roughness=settings["roughness"])

    # Stretch so values use the full 0..1 range
    height = (height - height.min()) / (height.max() - height.min())

    # Island shape: push the edges down so they become ocean
    if settings["shape"] == "island":
        center = (size - 1) / 2
        dist = np.sqrt((xs - center) ** 2 + (ys - center) ** 2) / center  # 0 middle, 1 edge
        height = height * np.clip(1 - dist ** 2, 0, 1)
        height = height / height.max()  # rescale so the highest point is 1 again

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
}


def color_map(height, settings):
    """Pick a palette color for each cell based on its height."""
    water = settings["water_level"]
    size = height.shape[0]
    img = np.zeros((size, size, 3), dtype=np.uint8)

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

    return img


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
    "shape": "island",      # "island" or "continent"
}


def generate_map(settings=None):
    """Main function: settings in, PIL Image out.
    This is the function Lambda will call later."""
    s = {**DEFAULT_SETTINGS, **(settings or {})}
    height = make_heightmap(s)
    pixels = color_map(height, s)
    img = Image.fromarray(pixels, "RGB")
    # NEAREST keeps the pixels sharp and blocky (pixel-art look)
    return img.resize((s["size"] * s["scale"],) * 2, Image.NEAREST)


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
