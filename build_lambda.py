"""
Builds lambda.zip: the code plus numpy and pillow, all in one file.
This is the Python version of `./gradlew shadowJar` (the "fat jar").

Run:  python build_lambda.py

The packages are downloaded for Linux (the computer Lambda runs on), so this
works on Windows, Mac, and Linux.
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PYTHON_VERSION = "3.12"  # must match the Lambda runtime (Python 3.12)
CODE_FILES = ["terrain.py", "lambda_function.py"]

project = Path(__file__).resolve().parent
build_dir = project / "build" / "package"
zip_path = project / "lambda.zip"

# Start fresh
shutil.rmtree(project / "build", ignore_errors=True)
zip_path.unlink(missing_ok=True)
build_dir.mkdir(parents=True)

# Download Linux versions of numpy and pillow into the build folder
subprocess.run(
    [
        sys.executable, "-m", "pip", "install",
        "--platform", "manylinux2014_x86_64",
        "--implementation", "cp",
        "--python-version", PYTHON_VERSION,
        "--only-binary=:all:",
        "--no-compile",
        "--target", str(build_dir),
        "-r", str(project / "requirements.txt"),
    ],
    check=True,
)

# Add our own code
for name in CODE_FILES:
    shutil.copy(project / name, build_dir / name)

# Zip everything in the build folder (files must be at the top of the zip)
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for file in build_dir.rglob("*"):
        if file.is_file():
            zf.write(file, file.relative_to(build_dir).as_posix())

size_mb = zip_path.stat().st_size / 1_000_000
print(f"Created lambda.zip ({size_mb:.0f} MB)")
