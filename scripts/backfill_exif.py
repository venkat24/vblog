#!/usr/bin/env python3
"""One-time EXIF backfill for the existing photo library.

Unlike the generic ``extract_exif.py``, this script encodes project-specific
assumptions about how photos *without* complete EXIF were shot. Run it once to
populate the library; new imports should use the generic extractor via the
import-photos skill instead.

Rules (applied per photo):
  1. Full EXIF (aperture present)      -> use the extracted data as-is.
  2. Shutter/ISO present, no aperture  -> shot on a manual 35mm lens; assume
                                          f/8 at 35mm focal length.
  3. No EXIF at all                     -> shot on film; Olympus XA, 35mm focal
                                          length, Kodak Gold 200, aperture unknown.

Usage:
    backfill_exif.py [albums-root]   # defaults to content/albums
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_exif import extract_exif, update_frontmatter  # noqa: E402

FILM_STOCK = "Kodak Gold 200"
FILM_CAMERA = "Olympus XA"
DEFAULT_FOCAL = "35mm"
MANUAL_LENS_APERTURE = "f/8"


def apply_rules(exif: dict) -> dict:
    """Layer the special-case fallbacks on top of the raw extracted EXIF."""
    has_shutter = "shutter" in exif
    has_aperture = "aperture" in exif

    if has_aperture:
        # Case 1: complete enough, leave it alone.
        return exif

    if has_shutter:
        # Case 2: digital body + manual 35mm lens.
        exif["aperture"] = MANUAL_LENS_APERTURE
        exif["focalLength"] = DEFAULT_FOCAL
        return exif

    # Case 3: film scan with no usable EXIF.
    return {
        "camera": FILM_CAMERA,
        "focalLength": DEFAULT_FOCAL,
        "film": FILM_STOCK,
    }


def find_photos(root: Path):
    for index_md in sorted(root.glob("*/*/index.md")):
        images = sorted(index_md.parent.glob("*.jpg")) + sorted(
            index_md.parent.glob("*.jpeg")
        )
        if images:
            yield index_md, images[0]


def main(argv) -> int:
    root = Path(argv[0]) if argv else Path("content/albums")
    if not root.is_dir():
        sys.exit(f"error: {root} is not a directory")

    counts = {"full": 0, "manual": 0, "film": 0}
    for index_md, image in find_photos(root):
        raw = extract_exif(image)
        result = apply_rules(dict(raw))
        if "film" in result:
            counts["film"] += 1
        elif "shutter" not in raw and "aperture" in result:
            counts["manual"] += 1  # unlikely, but track it
        elif "aperture" in raw:
            counts["full"] += 1
        else:
            counts["manual"] += 1
        update_frontmatter(index_md, result)
        summary = ", ".join(f"{k}={v}" for k, v in result.items())
        print(f"{index_md.parent.name:18} {summary}")

    print(f"\nDone. full={counts['full']} manual={counts['manual']} film={counts['film']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
