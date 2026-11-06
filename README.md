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

## AWS Lambda

`lambda_function.py` turns the generator into a web API. It follows the Java
[AWS Lambda notes](https://github.com/Duskoding/evolution-java/blob/main/amazon/aws_lambda.md)
step by step, using Python in place of Java:

| Java notes | This project |
|---|---|
| `RequestHandler.handleRequest(event, context)` | `lambda_handler(event, context)` in `lambda_function.py` |
| Gson turns JSON into objects | Python's built-in `json` module |
| `./gradlew shadowJar` builds a fat jar | `./build_lambda.sh` builds `lambda.zip` |
| Runtime: Java 21 | Runtime: Python 3.12 |
| Handler: `com.example.HelloRequestHandler` | Handler: `lambda_function.lambda_handler` |
| `toResponseEvent(e)` sends back the stack trace | Same: status 500 with the stack trace |

### Request

Send the settings as JSON in a POST body (see `request.json`), or as query
parameters in a GET request, such as `?seed=7&shape=continent`. Any setting you
leave out uses its default. Bad settings get a `400` with a message saying what
is wrong.

### Response

The response is a PNG image (`Content-Type: image/png`). Lambda can only return
text, so the image is sent as base64 with `isBase64Encoded: true`, and AWS turns
it back into an image before it reaches you.

### 1. Build the zip

The Python version of building a fat jar:

```bash
./build_lambda.sh
```

This creates `lambda.zip` (about 28 MB), which holds the code plus numpy and
Pillow. The packages are downloaded for Linux, so it works when you build on a
Mac or Windows too. On Windows, run it in Git Bash or WSL.

### 2. Create the Lambda on AWS

1. Create a function. Give it a name, set **Runtime** to **Python 3.12**, and
   leave **Architecture** set to **x86_64**.
2. In the **Code** tab, click **Upload from**, choose **.zip file**, and pick
   `lambda.zip`.
3. Under **Runtime settings**, click **Edit** and set **Handler** to
   `lambda_function.lambda_handler`. That is the file name, a dot, then the
   function name. (This is the default for new Python functions.)
4. In **Configuration**, open **General configuration**, click **Edit**, and
   raise **Memory** to 512 MB and **Timeout** to 30 seconds. The defaults
   (128 MB, 3 seconds) are too small for numpy.
5. In **Configuration**, create a **Function URL** with **Auth type** set to
   **NONE**.

### 3. Test it

```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -d @request.json \
     urlToYourLambda \
     --output map.png
```

You can also open `urlToYourLambda?seed=7&shape=continent` in a browser to see
the map.

### Updating from the command line

After you change the code, rebuild the zip and upload it:

```bash
./build_lambda.sh
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
    --memory-size 512 \
    --timeout 30 \
    --role arn:aws:iam::123456789012:role/your-lambda-role \
    --zip-file fileb://lambda.zip
```

## Roadmap

- [x] An AWS Lambda wrapper around `generate_map(settings)`
- [ ] AI that picks the settings from a plain-text description
