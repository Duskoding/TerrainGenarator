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

Handler setting on AWS:  lambda_function.lambda_handler
"""

import base64
import io
import json
import traceback

from terrain import DEFAULT_SETTINGS, generate_map

# Keep requests from asking for an image so big that Lambda runs out of memory.
MAX_IMAGE_PIXELS = 2048


def lambda_handler(event, context):
    try:
        # Retrieve the HTTP method, query parameters, and body.
        method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
        # Example: /?seed=7&shape=continent -> query_params["seed"] == "7"
        # Like in Java, this is None if the request has no query parameters.
        query_params = event.get("queryStringParameters")
        body = event.get("body")

        settings = {}
        if query_params:
            settings.update(_parse_query_params(query_params))
        if method == "POST" and body:
            if event.get("isBase64Encoded"):
                body = base64.b64decode(body).decode("utf-8")
            settings.update(json.loads(body))

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
            "headers": {"Content-Type": "image/png"},
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
        default = DEFAULT_SETTINGS.get(key, 0 if key.startswith("offset_") else None)
        if isinstance(default, int):
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
    if s["shape"] not in ("island", "continent"):
        return 'shape must be "island" or "continent"'
    if not (1 <= s["size"] and 1 <= s["scale"] and s["size"] * s["scale"] <= MAX_IMAGE_PIXELS):
        return f"size * scale must be between 1 and {MAX_IMAGE_PIXELS}"
    if s["mountain_height"] <= 0:
        return "mountain_height must be greater than 0"
    return None


def _text_response(status_code, message):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/plain"},
        "body": message,
    }
