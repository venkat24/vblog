#!/usr/bin/env python3
"""Extract camera EXIF data from photos and write it into Hugo front matter.

This is a GENERIC extractor: it records whatever EXIF the image actually
contains and nothing more. It makes no assumptions about missing fields.
Special-case fallbacks (film stock, manual lenses, etc.) deliberately live
elsewhere so this stays reusable for any photo import.

Usage:
    extract_exif.py <album-photo-dir-or-image> [...]

Each argument may be either an image file or a photo directory containing an
``index.md`` plus the image. For every photo found, an ``[exif]`` table is
written (or refreshed) in the sibling ``index.md``.

Requires exiftool on PATH.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

EXIFTOOL = shutil.which("exiftool")

# Tags we pull off the image, in the order we render them.
TAGS = ["ExposureTime", "FNumber", "ISO", "FocalLength", "Make", "Model"]


def run_exiftool(image: Path) -> dict:
    """Return the raw exiftool JSON dict for an image (empty if none)."""
    if not EXIFTOOL:
        sys.exit("error: exiftool not found on PATH (try `brew install exiftool`)")
    args = [EXIFTOOL, "-json"] + [f"-{t}" for t in TAGS] + [str(image)]
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    data = json.loads(out or "[]")
    return data[0] if data else {}


def format_camera(make, model) -> str | None:
    """Combine make/model into a clean label, e.g. 'Fujifilm X-T50'."""
    make = (str(make).strip() if make else "")
    model = (str(model).strip() if model else "")
    if not make and not model:
        return None
    # Title-case all-caps makers like FUJIFILM; leave model as the camera reports.
    if make.isupper():
        make = make.title()
    # Avoid 'Nikon NIKON Z6' style duplication.
    if model and make and model.lower().startswith(make.lower()):
        return model
    return f"{make} {model}".strip()


def format_focal_length(value) -> str | None:
    """'268.2 mm' or 268.2 -> '268mm'."""
    if value is None:
        return None
    m = re.search(r"[\d.]+", str(value))
    if not m:
        return None
    return f"{round(float(m.group()))}mm"


def format_aperture(value) -> str | None:
    """8.0 -> 'f/8', 5.6 -> 'f/5.6'."""
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    text = f"{n:.1f}".rstrip("0").rstrip(".")
    return f"f/{text}"


def extract_exif(image: Path) -> dict:
    """Return a dict of present EXIF fields. Missing fields are omitted."""
    raw = run_exiftool(image)
    exif: dict = {}

    camera = format_camera(raw.get("Make"), raw.get("Model"))
    if camera:
        exif["camera"] = camera
    if raw.get("ExposureTime") is not None:
        exif["shutter"] = str(raw["ExposureTime"])
    aperture = format_aperture(raw.get("FNumber"))
    if aperture:
        exif["aperture"] = aperture
    if raw.get("ISO") is not None:
        try:
            exif["iso"] = int(raw["ISO"])
        except (TypeError, ValueError):
            pass
    focal = format_focal_length(raw.get("FocalLength"))
    if focal:
        exif["focalLength"] = focal
    return exif


# Order in which keys are rendered into the [exif] table.
RENDER_ORDER = ["camera", "shutter", "aperture", "iso", "focalLength", "film"]


def render_exif_block(exif: dict) -> str:
    """Render an [exif] TOML table from a dict of fields."""
    lines = ["[exif]"]
    for key in RENDER_ORDER:
        if key not in exif:
            continue
        val = exif[key]
        if isinstance(val, int):
            lines.append(f"{key} = {val}")
        else:
            lines.append(f'{key} = "{val}"')
    return "\n".join(lines)


def update_frontmatter(index_md: Path, exif: dict) -> None:
    """Insert or replace the [exif] table in a TOML (+++) front matter file."""
    text = index_md.read_text()
    if not text.startswith("+++"):
        raise ValueError(f"{index_md} does not start with TOML (+++) front matter")

    # Split into: opening fence, front matter body, rest of document.
    parts = text.split("+++", 2)
    body = parts[1]
    rest = parts[2] if len(parts) > 2 else ""

    # Drop any existing [exif] table (always the last table in our files).
    lines = body.splitlines()
    cleaned = []
    for line in lines:
        if line.strip() == "[exif]":
            break
        cleaned.append(line)
    # Trim trailing blank lines from the remaining scalar keys.
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()

    new_body = "\n".join(cleaned)
    block = render_exif_block(exif) if exif else ""
    if block:
        new_body = f"{new_body}\n\n{block}\n"
    else:
        new_body = f"{new_body}\n"

    index_md.write_text(f"+++{new_body}+++{rest}")


def resolve_photo(arg: Path):
    """Given a dir or image path, return (index_md, image_path) or None."""
    if arg.is_dir():
        index_md = arg / "index.md"
        images = sorted(arg.glob("*.jpg")) + sorted(arg.glob("*.jpeg"))
        image = images[0] if images else None
    else:
        image = arg
        index_md = arg.parent / "index.md"
    if image is None or not image.exists():
        return None
    if not index_md.exists():
        return None
    return index_md, image


def process(arg: Path) -> dict | None:
    resolved = resolve_photo(arg)
    if not resolved:
        print(f"skip: {arg} (no index.md or image)")
        return None
    index_md, image = resolved
    exif = extract_exif(image)
    update_frontmatter(index_md, exif)
    summary = ", ".join(f"{k}={v}" for k, v in exif.items()) or "(no exif)"
    print(f"ok: {index_md.parent.name} -> {summary}")
    return exif


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 1
    for a in argv:
        process(Path(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
