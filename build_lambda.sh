#!/usr/bin/env bash
# Builds lambda.zip: the code plus numpy and pillow, all in one file.
# This is the Python version of `./gradlew shadowJar` (the "fat jar").
#
# The packages are downloaded for Linux (the computer Lambda runs on), so this
# works even if you build on a Mac or Windows.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_VERSION=3.12   # must match the Lambda runtime (Python 3.12)

rm -rf build lambda.zip
mkdir -p build/package

python3 -m pip install \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version "$PYTHON_VERSION" \
    --only-binary=:all: \
    --target build/package \
    -r requirements.txt

cp terrain.py lambda_function.py build/package/

(cd build/package && zip -qr ../../lambda.zip .)
echo "Created lambda.zip ($(du -h lambda.zip | cut -f1))"
