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
| `shape` | `"island"` | `"island"`, `"continent"`, or `"world"` |
| `width`, `height` | none | World maps only: cells across and down (default `size * 4` by `size * 2`) |
| `tile_x`, `tile_y` | none | Return only this tile (column, row), counting from 0 at the top left |
| `tile_size` | 64 | Tile width and height in cells |
| `offset_x`, `offset_y` | 0 | World position, so neighboring tiles line up |

```python
from terrain import generate_map
generate_map({"seed": 7, "shape": "continent"}).save("continent.png")
```

## World maps and tiles

`"shape": "world"` makes a whole world: a wide map with several continents,
open ocean, and ice at the top and bottom like the poles. With the default
`size` of 128 it is 512 x 256 cells, split into 8 x 4 tiles of 64 x 64 cells.

Send `tile_x` and `tile_y` to get one tile:

```python
generate_map({"shape": "world", "seed": 7, "tile_x": 3, "tile_y": 1})
```

The whole world is always generated first and then cut into the tile you asked
for, so tiles from the same seed line up perfectly at their edges.

### Explore page

Open `urlToYourLambda/explore` in a browser to walk around a world one tile at
a time, like a map in an exploration game:

- Move with the arrow buttons, the arrow keys, or WASD.
- The world map starts blank (parchment) and fills in as you visit tiles. It
  remembers what you explored, separately for each seed.
- Click an explored tile on the world map to jump back to it.
- **New world** picks a random seed. The seed is in the page link
  (`/explore?seed=7`), so you can share a world with someone.

## How it works

1. **Heightmap:** fractal value noise gives each cell an elevation between 0 and 1.
2. **Island shape (optional):** the edges are lowered so they become ocean.
3. **Coloring:** each cell gets a color from a small palette based on its height.
4. **Scaling:** the image is enlarged with nearest-neighbor resizing so the pixels stay crisp.

## AWS Lambda

`lambda_function.py` turns the generator into a web API. It follows the Java
[AWS Lambda notes](https://github.com/Duskoding/evolution-java/blob/main/amazon/aws_lambda.md)
step by step, using Python in place of Java:

| Java notes | This project |
|---|---|
| `RequestHandler.handleRequest(event, context)` | `lambda_handler(event, context)` in `lambda_function.py` |
| Gson turns JSON into objects | Python's built-in `json` module |
| `./gradlew shadowJar` builds a fat jar | `python build_lambda.py` builds `lambda.zip` |
| Runtime: Java 21 | Runtime: Python 3.12 |
| Handler: `com.example.HelloRequestHandler` | Handler: `lambda_function.lambda_handler` |
| `toResponseEvent(e)` sends back the stack trace | Same: status 500 with the stack trace |

### Request

Send the settings as JSON in a POST body (see `request.json`), or as query
parameters in a GET request, such as `?seed=7&shape=continent`. Any setting you
leave out uses its default.

**Random maps:** if you leave out `seed`, or send `"seed": "random"`, the Lambda
picks a random seed, so every request gives a new map. The seed it used comes
back in the `X-Seed` response header. Send that seed again to get the same map. Bad settings get a `400` with a message saying what
is wrong.

### Response

The response is a PNG image (`Content-Type: image/png`). Lambda can only return
text, so the image is sent as base64 with `isBase64Encoded: true`, and AWS turns
it back into an image before it reaches you.

### 1. Build the zip

The Python version of building a fat jar:

```bash
python build_lambda.py
```

This creates `lambda.zip` (about 24 MB), which holds the code plus numpy and
Pillow. The packages are downloaded for Linux, so it works when you build on a
Mac or Windows too. You can also right-click `build_lambda.py` in PyCharm and
choose **Run**.

### 2. Create the Lambda on AWS

1. Create a function. Give it a name, set **Runtime** to **Python 3.12**, and
   leave **Architecture** set to **x86_64**.
2. In the **Code** tab, click **Upload from**, choose **.zip file**, and pick
   `lambda.zip`.
3. Under **Runtime settings**, click **Edit** and set **Handler** to
   `lambda_function.lambda_handler`. That is the file name, a dot, then the
   function name. (This is the default for new Python functions.)
4. In **Configuration**, create a **Function URL** with **Auth type** set to
   **NONE**.

### 3. Test it

```bash
curl -X POST \
     -v \
     -H "Content-Type: application/json" \
     -d @request.json \
     urlToYourLambda \
     --output map.png
```

`--output map.png` is the one addition to the command in the class notes. It is
needed because the response is an image rather than JSON text.

### If it says "Task timed out"

This step is not in the class notes. It is only needed if you see that error.
Go to **Configuration**, then **General configuration**, click **Edit**, and
raise **Timeout** (for example, to 10 seconds) and **Memory** (for example, to
256 MB). Locally the handler runs in about 0.3 seconds and uses about 40 MB, so
the defaults should usually be enough.

### Updating from the command line

After you change the code, rebuild the zip and upload it:

```bash
python build_lambda.py
```

```bash
aws lambda update-function-code \
    --function-name yourFunctionName \
    --zip-file fileb://lambda.zip
```

To create the function from the command line instead of the console:

```bash
aws lambda create-function \
    --function-name yourFunctionName \
    --runtime python3.12 \
    --handler lambda_function.lambda_handler \
    --role arn:aws:iam::123456789012:role/your-lambda-role \
    --zip-file fileb://lambda.zip
```

## Roadmap

- [x] An AWS Lambda wrapper around `generate_map(settings)`
- [ ] AI that picks the settings from a plain-text description
