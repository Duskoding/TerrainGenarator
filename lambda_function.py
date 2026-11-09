"""
AWS Lambda handler for the terrain generator.

This is the Python version of the Java RequestHandler from the class notes
(evolution-java/amazon/aws_lambda.md). It works the same way:

  1. Read the HTTP method, query parameters, and body from the event.
  2. Turn the JSON body into settings (Python's json module does Gson's job).
  3. Call generate_map(settings).
  4. Return an HTTP response. Here the body is a PNG image instead of JSON.
  5. If anything goes wrong, print the stack trace to the AWS log and send it
     back to the client with status 500 (same as toResponseEvent in the notes).

It also serves the explore page: open <function url>/explore to walk around
a world map one tile at a time.

Handler setting on AWS:  lambda_function.lambda_handler
"""

import base64
import io
import json
import random
import traceback
from pathlib import Path

from terrain import DEFAULT_SETTINGS, generate_map, map_dimensions, tile_grid

# Keep requests from asking for an image so big that Lambda runs out of memory.
MAX_IMAGE_PIXELS = 2048
# The whole map is generated even for one tile, so cap its size too.
MAX_MAP_CELLS = 1024
# Random seeds are picked from 0 up to this number.
MAX_RANDOM_SEED = 999_999
# Settings that are whole numbers but have no number default (default None)
INT_SETTINGS = {"width", "height", "tile_x", "tile_y", "offset_x", "offset_y"}

# Read the explore page once, when Lambda starts (not on every request)
EXPLORE_PAGE = (Path(__file__).parent / "explore.html").read_text(encoding="utf-8")


def lambda_handler(event, context):
    try:
        # Retrieve the HTTP method, query parameters, and body.
        method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
        # Example: /?seed=7&shape=continent -> query_params["seed"] == "7"
        # Like in Java, this is None if the request has no query parameters.
        query_params = event.get("queryStringParameters")
        body = event.get("body")
        path = event.get("rawPath", "/")

        if path.rstrip("/") == "/explore":
            return _explore_page_response()

        settings = {}
        if query_params:
            settings.update(_parse_query_params(query_params))
        if method == "POST" and body:
            if event.get("isBase64Encoded"):
                body = base64.b64decode(body).decode("utf-8")
            settings.update(json.loads(body))

        # No seed (or "seed": "random") means a brand-new random map.
        if settings.get("seed", "random") == "random":
            settings["seed"] = random.randint(0, MAX_RANDOM_SEED)

        error = _validate(settings)
        if error:
            return _text_response(400, error)

        # Do the work: settings in, image out.
        image = generate_map(settings)

        # Lambda responses are text, so binary data (the PNG) is sent as
        # base64 and isBase64Encoded tells AWS to turn it back into bytes.
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return {
            "statusCode": 200,
            # Send the seed back so a map you like can be made again.
            "headers": {"Content-Type": "image/png", "X-Seed": str(settings["seed"])},
            "isBase64Encoded": True,
            "body": base64.b64encode(buffer.getvalue()).decode("ascii"),
        }
    except Exception:
        # This prints the stack trace to the AWS log file (CloudWatch).
        traceback.print_exc()
        # This outputs the stack trace to the client.
        return _text_response(500, traceback.format_exc())


def _parse_query_params(query_params):
    """Query parameters always arrive as strings, so turn numbers back into
    numbers (e.g. "0.4" -> 0.4) to match the types in DEFAULT_SETTINGS."""
    settings = {}
    for key, value in query_params.items():
        default = DEFAULT_SETTINGS.get(key)
        if key == "seed" and value == "random":
            settings[key] = value
        elif key in INT_SETTINGS or isinstance(default, int):
            settings[key] = int(value)
        elif isinstance(default, float):
            settings[key] = float(value)
        else:
            settings[key] = value
    return settings


def _validate(settings):
    """Return an error message for bad settings, or None if they are OK."""
    allowed = set(DEFAULT_SETTINGS) | {"offset_x", "offset_y"}
    unknown = set(settings) - allowed
    if unknown:
        return f"Unknown settings: {sorted(unknown)}. Allowed: {sorted(allowed)}"
    s = {**DEFAULT_SETTINGS, **settings}
    if not isinstance(s["seed"], int) or isinstance(s["seed"], bool):
        return 'seed must be a whole number or "random"'
    if s["shape"] not in ("island", "continent", "world"):
        return 'shape must be "island", "continent", or "world"'
    for key in INT_SETTINGS:
        if s.get(key) is not None and not isinstance(s[key], int):
            return f"{key} must be a whole number"
    if s["size"] < 1 or s["scale"] < 1 or s["tile_size"] < 1:
        return "size, scale, and tile_size must be at least 1"
    width, height = map_dimensions(s)
    if width > MAX_MAP_CELLS or height > MAX_MAP_CELLS:
        return f"the map can be at most {MAX_MAP_CELLS} cells across"
    if (s["tile_x"] is None) != (s["tile_y"] is None):
        return "send both tile_x and tile_y, or neither"
    if s["tile_x"] is not None:
        columns, rows = tile_grid(s)
        if not (0 <= s["tile_x"] < columns and 0 <= s["tile_y"] < rows):
            return f"this map has {columns} x {rows} tiles: tile_x 0-{columns - 1}, tile_y 0-{rows - 1}"
        width = height = s["tile_size"]
    if width * s["scale"] > MAX_IMAGE_PIXELS or height * s["scale"] > MAX_IMAGE_PIXELS:
        return f"the image can be at most {MAX_IMAGE_PIXELS} pixels across (lower scale or size)"
    if s["mountain_height"] <= 0:
        return "mountain_height must be greater than 0"
    return None


def _explore_page_response():
    """The explore page needs to know how many tiles the default world has."""
    world = {**DEFAULT_SETTINGS, "shape": "world"}
    columns, rows = tile_grid(world)
    html = (EXPLORE_PAGE
            .replace("{{COLUMNS}}", str(columns))
            .replace("{{ROWS}}", str(rows))
            .replace("{{MAX_SEED}}", str(MAX_RANDOM_SEED)))
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": html,
    }


def _text_response(status_code, message):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/plain"},
        "body": message,
    }
