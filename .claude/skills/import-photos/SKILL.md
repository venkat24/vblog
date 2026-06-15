---
name: import-photos
description: Import new photos into a Hugo album in this photo blog — copy the image into the album, create its gallery page, and extract camera EXIF (shutter, aperture, ISO, focal length) into front matter. Use when the user wants to add, import, or bring photos into an album / the blog.
---

# Import photos

Adds one or more photos to an album under `content/albums/<album>/`, following the
repository's existing conventions, and populates each photo's camera EXIF data.

## Layout recap

Each album is a directory of per-photo "page bundles":

```
content/albums/<album>/
  _index.md                 # album metadata (title, cover image)
  <album>-01/
    index.md                # the photo's front matter
    <album>-01.jpg          # the image (named to match the folder)
```

A photo's `index.md` front matter looks like:

```toml
+++
title = "<album>-NN"
image = "<album>-NN.jpg"
type = "gallery"
description = ""
weight = NN
size = "half"        # "full", "half", or "third" — controls album grid width

[exif]                # added automatically by the extractor (see below)
camera = "Fujifilm X-T50"
shutter = "1/210"
aperture = "f/8"
iso = 125
focalLength = "268mm"
+++
```

Set `featured = true` to surface the photo on the homepage's "Latest photos" grid.

## Steps to import a photo

1. **Pick the album.** Confirm the target album dir under `content/albums/`. If it
   is a brand-new album, create `content/albums/<album>/_index.md` with a `title`
   and a cover `image`.

2. **Find the next sequence number.** Look at the existing `<album>-NN` folders and
   use the next integer (zero-padded to two digits).

3. **Create the bundle and copy the image:**

   ```sh
   mkdir -p content/albums/<album>/<album>-NN
   cp "<source-image>" content/albums/<album>/<album>-NN/<album>-NN.jpg
   ```

4. **Create `index.md`** with the front matter shown above (omit the `[exif]`
   table — the next step writes it). Choose `size` and `weight` to fit the album's
   layout; ask the user if the desired layout isn't obvious.

5. **Extract EXIF** into the front matter:

   ```sh
   python3 scripts/extract_exif.py content/albums/<album>/<album>-NN
   ```

   You can pass several photo directories (or image files) at once. The extractor
   records whatever EXIF the image actually contains and is safe to re-run
   (it replaces any existing `[exif]` table).

6. **Verify** by starting the dev server (`hugo server -D`, or the `hugo` launch
   config) and opening the photo page — the specs appear beneath the image.

## Notes

- `scripts/extract_exif.py` is intentionally generic: it reports only the EXIF
  present in the file and makes **no** assumptions about missing fields. Requires
  `exiftool` on PATH (`brew install exiftool`).
- The one-time `scripts/backfill_exif.py` (which *does* encode project-specific
  fallbacks for film scans and manual lenses) is for the original library import
  only — do not use it for routine imports.
