# Pixel-Art Terrain Generator

Generates a top-down pixel-art map (islands, lakes, forests, mountains, snow) from a few settings.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python terrain.py
```

This saves `map.png`.

## Settings

Pass any of these to `generate_map(settings)`. Settings you leave out use the defaults.

| Setting | Default | Meaning |
|---|---|---|
| `seed` | 4821 | The same seed always gives the same map |
| `size` | 128 | The map is `size` x `size` cells |
| `scale` | 4 | Each cell becomes a `scale` x `scale` pixel block |
| `zoom` | 4 | Higher values give more, smaller features |
| `water_level` | 0.40 | 0 to 1: how much of the map is water |
| `mountain_height` | 1.0 | 0.5 = flat, 1 = normal, 2 = very mountainous |
| `roughness` | 0.5 | 0 to 1: how jagged the terrain is |
| `shape` | `"island"` | `"island"` or `"continent"` |
| `offset_x`, `offset_y` | 0 | World position, so neighboring tiles line up |

```python
from terrain import generate_map
generate_map({"seed": 7, "shape": "continent"}).save("continent.png")
```

## How it works

1. **Heightmap:** fractal value noise gives each cell an elevation between 0 and 1.
2. **Island shape (optional):** the edges are lowered so they become ocean.
3. **Coloring:** each cell gets a color from a small palette based on its height.
4. **Scaling:** the image is enlarged with nearest-neighbor resizing so the pixels stay crisp.

## Roadmap

- An AWS Lambda wrapper around `generate_map(settings)`
- AI that picks the settings from a plain-text description
