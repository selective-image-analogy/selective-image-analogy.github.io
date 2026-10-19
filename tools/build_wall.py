# -*- coding: utf-8 -*-
"""Compose the masthead's result walls from the built result images.

Reads static/images (run build_images.py first) and writes two grids of SIA
outputs with rounded corners on a transparent ground, so the page colour shows
through the gaps in either theme. The page tilts and dims them in CSS.

  static/figures/wall.webp         9 x 5, the still wall
  static/figures/wall-motion.webp  9 x 8, the drifting wall; each column loops
                                   vertically, so the page can scroll the
                                   columns past one another

Each also comes as a light copy (wall-lite.webp, wall-motion-lite.webp): the
same wall at a fraction of the size and weight, which the page shows first so
that even a weak connection gets a wall, and a moving one, within a second.
The full-quality images then download in the background and replace them.

Both carry half a gap of margin on every side, so a column is exactly 1/9 of
the image width and a column repeats seamlessly when stacked on itself.
"""
import glob
import hashlib
import json
import os
import random
import re

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "static", "images")
FIG = os.path.join(ROOT, "static", "figures")

COLS = 9
TILE_W, TILE_H = 240, 320          # 3:4, the shape of every result crop
GAP, RADIUS = 14, 12
SEED = 7

STATIC_ROWS = 5                    # about what the tilted masthead shows
STATIC_PER_SAMPLE = 7              # subsets taken from each switchboard sample
STATIC_PER_SUBJECT = 3             # tiles of any one portrait subject; an animal
STATIC_PER_THING = 6               # or object may show more of its (distinct) results

MOTION_ROWS = 8                    # tiles in each column's loop
MOTION_PER_SAMPLE = 8

# The light copies: (fraction of the full size, webp quality). The still one
# is only a first paint, so it is the lighter; the moving one may be what a
# slow connection watches for a while before the full wall arrives.
STATIC_LITE = (1 / 4, 45)          # ~40 KB
MOTION_LITE = (1 / 3, 40)          # ~100 KB

# The wall leads with the objects, animals and scenes; portraits are capped
# so faces don't dominate the masthead.
STATIC_PEOPLE = 14                 # of the static wall's 45 tiles (about 30 %)
MOTION_PEOPLE_PER_COL = 3          # of each column's 8: neighbouring columns
                                   # share no family, and there are only 11
                                   # families of objects and animals

# Different query images that look alike on the wall: one family each, kept
# apart like results of the same query (ids from build_images.py).
FAMILIES = {
    "silver car": ["x3", "x51", "x71", "x72", "x74"],
    "dog in a field": ["x4", "x57", "x64"],
    "dragon": ["x59", "x76", "x77", "s2"],
    "pineapple": ["x53", "x70"],
    "apple": ["x2", "x67", "x68"],
    "man in an alley": ["x58", "s1"],
    "woman with a bun": ["x27", "s3"],
    "man on a street": ["x1", "x47"],
}
FAMILY_OF = {i: f for f, ids in FAMILIES.items() for i in ids}


def subjects():
    """id -> subject ("people", "creatures", ...) from the built data.js."""
    with open(os.path.join(ROOT, "static", "js", "data.js"), encoding="utf-8") as f:
        js = f.read()
    out = {}
    for name in ("SIA_SAMPLES", "SIA_EXAMPLES"):
        items = json.loads(re.search(r"window\.%s = (\[.*?\]);" % name, js, re.S).group(1))
        out.update({x["id"]: x["subject"] for x in items})
    return out


def query_key(folder):
    """Results that share a query image show the same subject; never let two
    of them touch on the wall."""
    with open(os.path.join(folder, "b.webp"), "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def collect(per_sample):
    """(image, family, is a portrait) for every result the wall may use. A
    family is the query image, or the FAMILIES group it looks like."""
    subject = subjects()
    tiles = []
    def family(d):
        return FAMILY_OF.get(os.path.basename(d)) or query_key(d)
    for d in sorted(glob.glob(os.path.join(IMG, "examples", "x*"))):
        tiles.append((os.path.join(d, "out.webp"), family(d),
                      subject[os.path.basename(d)] == "people"))
    for d in sorted(glob.glob(os.path.join(IMG, "samples", "s*"))):
        key, people = family(d), subject[os.path.basename(d)] == "people"
        subs = glob.glob(os.path.join(d, "subsets", "*.webp"))
        # the fullest transfers first: they differ most from the query
        subs.sort(key=lambda p: (-os.path.basename(p).count("1"), p))
        tiles += [(p, key, people) for p in subs[:per_sample]]
    return tiles


def arrange_static(tiles, rng, tries=3000):
    """Row-major fill so no family touches itself (diagonals included) or
    sits two apart in a row, no family crowds the wall (a portrait subject at most
    STATIC_PER_SUBJECT tiles, an animal or object at most STATIC_PER_THING of
    its distinct results), no image repeats and portraits stay within
    STATIC_PEOPLE."""
    distinct = {}
    for t in tiles:
        distinct.setdefault(t[1], set()).add(t[0])
    cap = {k: min(len(v), STATIC_PER_THING) for k, v in distinct.items()}
    cap.update({t[1]: STATIC_PER_SUBJECT for t in tiles if t[2]})
    for _ in range(tries):
        pool = tiles[:]
        rng.shuffle(pool)
        grid, seen, ok, faces = [], {}, True, 0
        for i in range(COLS * STATIC_ROWS):
            if not pool:
                pool = tiles[:]
                rng.shuffle(pool)
            r, c = divmod(i, COLS)
            # the tiles around this one (the wall is tilted, so diagonals
            # count) and two to its left: none may be the same family
            near = {grid[rr * COLS + cc][1] for rr in (r - 1, r) for cc in (c - 2, c - 1, c, c + 1)
                    if 0 <= rr and 0 <= cc < COLS and rr * COLS + cc < i}
            row_faces = sum(g[2] for g in grid[r * COLS:])
            col_faces = sum(grid[i2][2] for i2 in range(c, len(grid), COLS))
            fits = [t for t in pool if t[1] not in near
                    and seen.get(t[1], 0) < cap[t[1]]
                    and t[0] not in (g[0] for g in grid)
                    and not (t[2] and (faces >= STATIC_PEOPLE or row_faces >= 3 or col_faces >= 2))]
            # weighted by the tiles each subject still has to place, so the
            # big ones are spread out rather than stranded at the end
            pick = None
            if fits:
                w = [cap[t[1]] - seen.get(t[1], 0) for t in fits]
                pick = rng.choices(fits, weights=w)[0]
            if pick is None:
                ok = False
                break
            pool.remove(pick)
            grid.append(pick)
            seen[pick[1]] = seen.get(pick[1], 0) + 1
            faces += pick[2]
        if ok:
            return [grid[r * COLS:(r + 1) * COLS] for r in range(STATIC_ROWS)]
    raise RuntimeError("could not arrange the static wall")


def arrange_motion(tiles, rng, tries=200):
    """Column by column. Neighbouring columns slide past each other, so any
    tile meets every tile of the columns beside it: they share no family. The
    columns two apart move in step (app.js gives all one pace), so there a
    family may recur only three or more rows away. Within a column no family
    shows twice. Each column holds
    MOTION_PEOPLE_PER_COL portraits at rows that don't touch (counting the
    wrap from the last tile back to the first); over the whole wall an image
    shows at most three times (so never in neighbouring columns), the less
    used ones first."""
    people = [t for t in tiles if t[2]]
    things = [t for t in tiles if not t[2]]

    def face_rows():
        while True:
            rows = sorted(rng.sample(range(MOTION_ROWS), MOTION_PEOPLE_PER_COL))
            gaps = [(b - a) % MOTION_ROWS for a, b in zip(rows, rows[1:] + rows[:1])]
            if min(gaps) > 1:
                return set(rows)

    def build_column(cols, used):
        faces, col, taken = face_rows(), [], {}
        for r in range(MOTION_ROWS):
            beside = {u[1] for u in cols[-1]} if cols else set()
            # two columns over moves in step with this one: a family may
            # recur there only three or more rows away (around the loop)
            over = {cols[-2][(r + k) % MOTION_ROWS][1] for k in range(-2, 3)} if len(cols) > 1 else set()
            # and four columns over, not the very same image on the same row
            twin = cols[-4][r][0] if len(cols) > 3 else None
            n = lambda t: used.get(t[0], 0) + taken.get(t[0], 0)
            cand = [t for t in (people if r in faces else things)
                    if n(t) < 3 and t[1] not in beside and t[1] not in over and t[0] != twin
                    and all(t[1] != u[1] for u in col)]
            if not cand:
                return None
            pick = rng.choices(cand, weights=[(3 - n(t)) ** 2 for t in cand])[0]
            col.append(pick)
            taken[pick[0]] = taken.get(pick[0], 0) + 1
        return col

    for _ in range(tries):
        used, cols = {}, []
        while len(cols) < COLS:
            # a stuck column is retried on its own before the wall starts over
            col = next((c for c in (build_column(cols, used) for _ in range(300)) if c), None)
            if col is None:
                break
            cols.append(col)
            for t in col:
                used[t[0]] = used.get(t[0], 0) + 1
        if len(cols) == COLS:
            return [[cols[c][r] for c in range(COLS)] for r in range(MOTION_ROWS)]
    raise RuntimeError("could not arrange the motion wall")


def compose(rows, dest, quality, lite):
    pitch_w, pitch_h = TILE_W + GAP, TILE_H + GAP
    w, h = COLS * pitch_w, len(rows) * pitch_h
    wall = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mask = Image.new("L", (TILE_W, TILE_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, TILE_W - 1, TILE_H - 1), RADIUS, fill=255)
    cache = {}
    for r, row in enumerate(rows):
        for c, (path, _, _) in enumerate(row):
            if path not in cache:
                im = Image.open(path).convert("RGB")
                # centre-crop to 3:4 (a few results are 368 px wide), then scale
                tw = round(im.height * TILE_W / TILE_H)
                if im.width > tw:
                    x = (im.width - tw) // 2
                    im = im.crop((x, 0, x + tw, im.height))
                cache[path] = im.resize((TILE_W, TILE_H), Image.LANCZOS)
            wall.paste(cache[path], (c * pitch_w + GAP // 2, r * pitch_h + GAP // 2), mask)
    wall.save(dest, "WEBP", quality=quality, method=6)
    n = sum(len(row) for row in rows)
    print("wrote %s  %dx%d  %d tiles (%d distinct)  %.0f KB"
          % (os.path.relpath(dest, ROOT), w, h, n, len(cache), os.path.getsize(dest) / 1024))

    # the light copy, scaled with premultiplied alpha so the transparent gaps
    # don't darken the tiles' edges
    scale, lite_quality = lite
    small = wall.convert("RGBa").resize((round(w * scale), round(h * scale)), Image.LANCZOS).convert("RGBA")
    lite_dest = dest.replace(".webp", "-lite.webp")
    small.save(lite_dest, "WEBP", quality=lite_quality, method=6)
    print("wrote %s  %dx%d  %.0f KB"
          % (os.path.relpath(lite_dest, ROOT), small.width, small.height, os.path.getsize(lite_dest) / 1024))


def main():
    if not glob.glob(os.path.join(IMG, "examples", "x*")):
        raise SystemExit("no result images found under static/images — run build_images.py first")
    os.makedirs(FIG, exist_ok=True)
    rng = random.Random(SEED)
    compose(arrange_static(collect(STATIC_PER_SAMPLE), rng), os.path.join(FIG, "wall.webp"), 72, STATIC_LITE)
    compose(arrange_motion(collect(MOTION_PER_SAMPLE), rng), os.path.join(FIG, "wall-motion.webp"), 66, MOTION_LITE)


if __name__ == "__main__":
    main()
