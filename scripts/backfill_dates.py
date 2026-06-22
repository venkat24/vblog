#!/usr/bin/env python3
"""Backfill the top-level `exifDate` used to sort the homepage photo grid.

For every photo missing an `exifDate`, set it from the image's EXIF capture
time, or — when the image carries no usable EXIF date (e.g. film scans) — from
the file's creation date in the repo. Photos that already have an `exifDate`
are left untouched, so manually-set dates are preserved.

This only writes the `exifDate` scalar; it never modifies the [exif] table.

Usage:
    backfill_dates.py [albums-root]   # defaults to content/albums
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_exif import (  # noqa: E402
    extract_date,
    file_created_date,
    frontmatter_has,
    run_exiftool,
    update_frontmatter,
)


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

    counts = {"exif": 0, "file": 0, "kept": 0}
    for index_md, image in find_photos(root):
        if frontmatter_has(index_md, "exifDate"):
            counts["kept"] += 1
            continue
        raw = run_exiftool(image)
        from_exif = extract_date(image, raw)
        date = from_exif or file_created_date(image)
        source = "exif" if from_exif else "file"
        counts[source] += 1
        update_frontmatter(index_md, exif_date=date, set_exif=False, set_date=True)
        print(f"{index_md.parent.name:18} exifDate={date}  ({source})")

    print(
        f"\nDone. set-from-exif={counts['exif']} "
        f"set-from-file={counts['file']} already-had-date={counts['kept']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
