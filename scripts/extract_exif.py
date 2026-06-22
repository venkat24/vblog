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
from datetime import datetime
from pathlib import Path

EXIFTOOL = shutil.which("exiftool")

# Tags we pull off the image. The capture-date tags are tried in order.
TAGS = [
    "ExposureTime",
    "FNumber",
    "ISO",
    "FocalLength",
    "Make",
    "Model",
    "DateTimeOriginal",
    "CreateDate",
    "ModifyDate",
]

# EXIF date tags tried in priority order when resolving capture time.
DATE_TAGS = ["DateTimeOriginal", "CreateDate", "ModifyDate"]


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


def format_exif_datetime(value) -> str | None:
    """'2025:12:29 15:10:07' -> '2025-12-29T15:10:07' (TOML datetime)."""
    if not value:
        return None
    try:
        dt = datetime.strptime(str(value).strip(), "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def extract_date(image: Path, raw: dict | None = None) -> str | None:
    """Capture date from EXIF, or None if the image carries no usable date."""
    raw = raw if raw is not None else run_exiftool(image)
    for tag in DATE_TAGS:
        formatted = format_exif_datetime(raw.get(tag))
        if formatted:
            return formatted
    return None


def file_created_date(path: Path) -> str:
    """Filesystem creation date (birth time), falling back to mtime."""
    st = path.stat()
    ts = getattr(st, "st_birthtime", None) or st.st_mtime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")


def photo_date(image: Path, raw: dict | None = None) -> str:
    """Best available date: EXIF capture time, else the file's creation date."""
    return extract_date(image, raw) or file_created_date(image)


def extract_exif(image: Path, raw: dict | None = None) -> dict:
    """Return a dict of present EXIF fields. Missing fields are omitted."""
    raw = raw if raw is not None else run_exiftool(image)
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


def _is_key(line: str, key: str) -> bool:
    """True if a front-matter line assigns the given top-level key."""
    s = line.strip()
    return "=" in s and s.split("=", 1)[0].strip() == key


def _split_frontmatter(text: str):
    """Return (scalar_lines, exif_table_lines, rest_of_document).

    The [exif] table is always the last block in our front matter, so
    everything before it is treated as top-level scalar keys.
    """
    if not text.startswith("+++"):
        raise ValueError("file does not start with TOML (+++) front matter")
    parts = text.split("+++", 2)
    body = parts[1]
    rest = parts[2] if len(parts) > 2 else ""

    scalars, table = [], []
    in_table = False
    for line in body.splitlines():
        if line.strip() == "[exif]":
            in_table = True
        (table if in_table else scalars).append(line)
    while scalars and scalars[-1].strip() == "":
        scalars.pop()
    while table and table[-1].strip() == "":
        table.pop()
    return scalars, table, rest


def frontmatter_has(index_md: Path, key: str) -> bool:
    """True if the front matter already defines a top-level scalar `key`."""
    scalars, _, _ = _split_frontmatter(index_md.read_text())
    return any(_is_key(line, key) for line in scalars)


def update_frontmatter(
    index_md: Path,
    exif: dict | None = None,
    exif_date: str | None = None,
    *,
    set_exif: bool = True,
    set_date: bool = True,
) -> None:
    """Update a TOML (+++) front matter file in place.

    - When `set_exif`, the [exif] table is replaced with `exif` (removed if empty).
    - When `set_date` and `exif_date` is given, the top-level `exifDate` key is
      inserted or replaced. `exifDate` stays above the [exif] table so the file
      remains valid TOML (top-level keys must precede tables).
    Pass `set_exif=False` to leave an existing [exif] table untouched.
    """
    scalars, table, rest = _split_frontmatter(index_md.read_text())

    if set_date and exif_date:
        scalars = [line for line in scalars if not _is_key(line, "exifDate")]
        scalars.append(f"exifDate = {exif_date}")

    if set_exif:
        table = render_exif_block(exif).splitlines() if exif else []

    new_body = "\n".join(scalars)
    if table:
        new_body = f"{new_body}\n\n" + "\n".join(table) + "\n"
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
    raw = run_exiftool(image)
    exif = extract_exif(image, raw)
    date = photo_date(image, raw)
    update_frontmatter(index_md, exif, date)
    summary = ", ".join(f"{k}={v}" for k, v in exif.items()) or "(no exif)"
    print(f"ok: {index_md.parent.name} -> exifDate={date}; {summary}")
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
