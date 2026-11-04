# -*- coding: utf-8 -*-
"""Compose the masthead's result walls from the built result images.

Reads static/images (run build_images.py first) and writes two grids of SIA
outputs with rounded corners on a transparent ground, so the page colour shows
through the gaps in either theme. The page tilts and dims them in CSS.

  static/figures/wall.webp         9 x 5, the still wall
  static/figures/wall-motion.webp  9 x 16, the drifting wall; each column loops
                                   vertically, so the page can scroll the
                                   columns past one another

Each also comes as a light copy (wall-lite.webp, wall-motion-lite.webp): the
same wall at a fraction of the size and weight, which the page shows first so
that even a weak connection gets a wall, and a moving one, within a second.
The full-quality images then download in the background and replace them.

Both carry half a gap of margin on every side, so a column is exactly 1/9 of
the image width and a column repeats seamlessly when stacked on itself.
"""
import collections
import glob
import hashlib
import json
import math
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

MOTION_ROWS = 16                   # tiles in each column's loop (the longer, the later a
                                   # picture comes round again)
MOTION_FAMILY_GAP = 5              # rows between two tiles of one family in a column
MOTION_PER_SAMPLE = 8
MOTION_REPEAT = 2                  # times one picture shows in the whole loop at most

# The light copies: (fraction of the full size, webp quality). The still one
# is only a first paint, so it is the lighter; the moving one may be what a
# slow connection watches for a while before the full wall arrives.
STATIC_LITE = (1 / 4, 45)          # ~40 KB
MOTION_LITE = (1 / 3, 40)          # ~100 KB

# The wall leads with the objects, animals and scenes; portraits are capped
# so faces don't dominate the masthead.
STATIC_FACES_PER_ROW = 4           # portraits in one row of the still wall
STATIC_FACES_PER_COL = 3           # and in one column
STATIC_PEOPLE = 20                 # of the static wall's 45 tiles (about 45 %)
MOTION_PEOPLE_PER_COL = 7          # of each column's 16: neighbouring columns
                                   # share no family, and there are only 11
                                   # families of objects and animals

# Different query images that look alike on the wall: one family each, kept
# apart like results of the same query (ids from build_images.py).
FAMILIES = {
    "silver car": ["x3", "x51", "x74"],
    "dog in a field": ["x4"],
    "collie": ["x84", "s4"],
    "dragon": ["x59", "x77"],
    "red dragon": ["s2"],
    "apple": ["x2", "x68"],
    "pineapple": ["x70"],
    "mug": ["x86", "s8"],
    "crown and scowl": ["x87", "s9"],
    "man in an alley": ["x58", "s1"],
    "man on a street": ["x1", "x47"],
}
FAMILY_OF = {i: f for f, ids in FAMILIES.items() for i in ids}


# ---------------------------------------------------------------------------
# What is IN each result (a crown, sunglasses, a beard, a pencil sketch, a dog,
# ...), so that tiles which can be on screen together don't repeat a feature
# even when they are different people or pictures. Tags come from the edits a
# result carries over (data.js); the wall-only extras are tagged by hand.
FEATURES = [  # (substring of a kept edit's label, tag)
    ("crown", "crown"), ("sunglass", "sunglasses"), ("beard", "beard"), ("armor", "armor"),
    ("hat", "hat"), ("earring", "earrings"), ("scarf", "scarf"), ("necklace", "necklace"),
    ("wig", "hair"), ("hair", "hair"), ("clown", "clown"), ("lipstick", "lipstick"),
    ("t-shirt", "shirt"), ("sweater", "sweater"), ("carv", "carving"), ("halloween", "carving"),
    ("pencil", "pencil"), ("van gogh", "vangogh"), ("comic", "comic"), ("painting", "paint"),
    ("lava", "lava"), ("wings", "wings"), ("gold color", "gold"), ("sitting", "sit"),
    ("jump", "jump"), ("float", "float"), ("doors", "doors"), ("logo", "logo"),
    ("lights", "lights"), ("bench", "bench"), ("sad", "sad"), ("surprise", "surprise"),
    ("happy", "happy"), ("angry", "angry"), ("laugh", "laugh"),
]
# how much it hurts to see two tiles with the same tag at once
TAG_WEIGHT = {t: 6 for t in ("crown", "sunglasses", "beard", "armor", "hat", "earrings", "scarf",
                              "necklace", "hair", "clown", "lipstick", "shirt", "sweater", "doors", "logo")}
TAG_WEIGHT.update({t: 4 for t in ("carving", "pencil", "vangogh", "comic", "paint", "lava", "wings",
                                    "gold", "jump", "float", "sit", "lights", "bench")})
TAG_WEIGHT.update({t: 3 for t in ("car", "fruit", "lamp", "mug")})
TAG_WEIGHT["dog"] = 3       # the biggest group of pictures; keep them spread out
TAG_WEIGHT.update({"dragon": 14, "lava": 5, "gold": 5, "wings": 5, "car": 9})   # few dragon and car queries, so they crowd easily
TAG_WEIGHT.update({t: 2 for t in ("sad", "surprise", "happy", "angry", "laugh")})
SUBJECT_TAG = {"dog": {"x4", "x15", "x80", "x82", "x84", "x85", "s4"},
               "dragon": {"x59", "x77", "s2"}, "car": {"x3", "x51", "x74"},
               "fruit": {"x2", "x68", "x70", "x83"}, "lamp": {"s13"}, "mug": {"x86", "s8"}}
EXTRA_TAGS = {  # wall_extra/<family>/keepN.png -> tags
    "melon": {"1": {"fruit", "carving"}, "2": {"fruit"}, "12": {"fruit", "carving"}, "23": {"fruit", "pencil"}},
    "table_lamp": {"1": {"lamp", "bench"}, "2": {"lamp"}, "12": {"lamp", "bench"}, "23": {"lamp", "paint"}},
    "german_shepherd": {"1": {"dog", "shirt"}, "2": {"dog", "sit"}, "3": {"dog", "paint"},
                        "12": {"dog", "shirt", "sit"}, "13": {"dog", "shirt", "paint"}, "23": {"dog", "sit", "paint"}},
    "blue_suv": {"1": {"car", "lights"}, "2": {"car", "doors"}},
    "green_suv": {"1": {"car", "lights"}, "2": {"car", "doors"}},
    "pottery_table": {"2": {"comic"}},
    "blue_dragon": {"1": {"dragon", "lava"}, "3": {"dragon", "gold"}, "13": {"dragon", "gold", "lava"},
                    "23": {"dragon", "gold", "wings"}},
}


def result_meta():
    """(examples: id -> labels of the edits it keeps, samples: id -> its edit labels)."""
    with open(os.path.join(ROOT, "static", "js", "data.js"), encoding="utf-8") as f:
        js = f.read()
    ex = json.loads(re.search(r"window\.SIA_EXAMPLES = (\[.*?\]);", js, re.S).group(1))
    sm = json.loads(re.search(r"window\.SIA_SAMPLES = (\[.*?\]);", js, re.S).group(1))
    return ({x["id"]: [e["label"] for e in x["edits"] if e["kept"]] for x in ex},
            {x["id"]: [e["label"] for e in x["edits"]] for x in sm})


def feature_tags(labels, rid):
    tags = {t for lab in labels for sub, t in FEATURES if sub in lab.lower()}
    tags |= {t for t, ids in SUBJECT_TAG.items() if rid in ids}
    return frozenset(tags)


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
    kept_ex, labels_sm = result_meta()
    tiles = []
    def family(d):
        return FAMILY_OF.get(os.path.basename(d)) or query_key(d)
    for d in sorted(glob.glob(os.path.join(IMG, "examples", "x*"))):
        rid = os.path.basename(d)
        tiles.append((os.path.join(d, "out.webp"), family(d), subject[rid] == "people",
                      feature_tags(kept_ex[rid], rid)))
    for d in sorted(glob.glob(os.path.join(IMG, "samples", "s*"))):
        key, people = family(d), subject[os.path.basename(d)] == "people"
        subs = glob.glob(os.path.join(d, "subsets", "*.webp"))
        # the fullest transfers first: they differ most from the query
        subs.sort(key=lambda p: (-os.path.basename(p).count("1"), p))
        rid = os.path.basename(d)
        def sub_tags(path):
            mask = os.path.splitext(os.path.basename(path))[0]
            return feature_tags([l for l, m in zip(labels_sm[rid], mask) if m == "1"], rid)
        tiles += [(p, key, people, sub_tags(p)) for p in subs[:per_sample]]
    # wall-only results of other query images (new figures/wall_extra/<family>/*.png):
    # extra objects and animals, so the denser wall has enough non-portrait variety
    for d in sorted(glob.glob(os.path.join(ROOT, "new figures", "wall_extra", "*", ""))):
        fam = "extra:" + os.path.basename(os.path.dirname(d))
        name = os.path.basename(os.path.dirname(d))
        tiles += [(p, fam, False, frozenset(EXTRA_TAGS.get(name, {}).get(
                      os.path.basename(p)[4:-4], ())))
                  for p in sorted(glob.glob(os.path.join(d, "*.png")))]
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
                    and not (t[2] and (faces >= STATIC_PEOPLE or row_faces >= STATIC_FACES_PER_ROW or col_faces >= STATIC_FACES_PER_COL))]
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
    family may recur only three or more rows away. Within a column a family
    recurs only MOTION_FAMILY_GAP or more rows apart. Each column holds
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
                    and all(t[1] != u[1] or min(r - i, MOTION_ROWS - (r - i)) >= MOTION_FAMILY_GAP
                            for i, u in enumerate(col))]
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


# ---------------------------------------------------------------------------
# Refinement: the family rules above keep look-alike *queries* apart; this pass
# also keeps tiles that show the same *thing* (three crowns, two pairs of
# sunglasses, two pencil sketches, ...) from being on screen together, by
# simulated annealing over the tile positions.
VIEW_ROWS = 5            # rows of the moving wall on screen at once (a tall screen)
VIEW_COLS = 8            # and columns (the wall is a little wider than the screen)


SCARCE = frozenset({"dragon", "paint"})
MOTION_THEME_CAP = 5     # slots of the 144 one subject (a person, ...) may fill
# ... and for the subjects that make up most of the objects and animals, all their
# different queries together (every dog, every dragon, every car, ...). Each is a
# share of the loop, so it can't take over a screen.
THEME_TAGS = ("dragon", "dog", "car", "fruit", "lamp", "mug")
# (the object/animal slots are 81 of 144 and there are only 63 such pictures, so these must add up to
# at least 81; fewer queries to draw on than that is what limits the variety)
THEME_CAPS = {"dragon": 10, "dog": 22, "car": 13, "fruit": 14, "lamp": 10, "mug": 8}
ONCE = frozenset({"lamp"})     # shown once per loop: their few pictures would repeat on screen


def theme(t):
    for tag in THEME_TAGS:
        if tag in t[3]:
            return tag
    return t[1]


def pair_cost(a, b):
    if a[0] == b[0]:
        return 200.0                              # the very same picture
    # the same query (or look-alike): for an object or animal that is nearly the same
    # picture (a subtle edit), so it counts as a duplicate; two portraits differ more
    c = (10.0 if a[2] else 30.0) if a[1] == b[1] else 0.0
    return c + sum(TAG_WEIGHT.get(t, 1) for t in a[3] & b[3])


def anneal(assign, neighbors, pool, cap, rng, iters, t0=8.0, t1=0.05, theme_cap=None):
    """assign: slot -> tile; neighbors: slot -> [(slot, weight)] that can be seen
    together; a tile may be used `cap` times in all; portraits stay in portrait
    slots. Returns the improved assignment."""
    tiles = list(pool)
    index = {t[0]: i for i, t in enumerate(tiles)}
    for t in assign:
        if t[0] not in index:
            index[t[0]] = len(tiles)
            tiles.append(t)
    n = len(tiles)
    P = [[pair_cost(tiles[i], tiles[j]) for j in range(n)] for i in range(n)]
    a = [index[t[0]] for t in assign]
    people = [tiles[i][2] for i in a]
    by_class = {True: [i for i in range(n) if tiles[i][2]], False: [i for i in range(n) if not tiles[i][2]]}
    use = collections.Counter(a)
    # themes with few pictures to draw on (the dragons, the flat-paint dogs) show
    # each picture once only, so they don't make up a fifth of the wall
    limit = [1 if tiles[i][3] & (SCARCE | ONCE) else cap for i in range(n)]
    S = len(a)
    th = [theme(tiles[i]) for i in range(n)]
    tuse = collections.Counter(th[i] for i in a)
    tcap = lambda x: (theme_cap(x) if theme_cap else S)
    # repair: no subject may fill more than `tcap` slots
    for s in rng.sample(range(S), S):
        if tuse[th[a[s]]] > tcap(th[a[s]]):
            opts = [u for u in by_class[people[s]] if tuse[th[u]] < tcap(th[u]) and use[u] < limit[u]]
            if opts:
                u = rng.choice(opts)
                tuse[th[a[s]]] -= 1; use[a[s]] -= 1
                tuse[th[u]] += 1; use[u] += 1; a[s] = u

    def local(s, i):
        row = P[i]
        return sum(w * row[a[m]] for m, w in neighbors[s])

    for it in range(iters):
        T = t0 * (t1 / t0) ** (it / iters)
        s = rng.randrange(S)
        if rng.random() < 0.6:
            u = rng.choice(by_class[people[s]])
            if u == a[s] or use[u] >= limit[u] or (th[u] != th[a[s]] and tuse[th[u]] >= tcap(th[u])):
                continue
            d = local(s, u) - local(s, a[s])
            if d <= 0 or rng.random() < math.exp(-d / T):
                use[a[s]] -= 1
                use[u] += 1
                tuse[th[a[s]]] -= 1
                tuse[th[u]] += 1
                a[s] = u
        else:
            s2 = rng.randrange(S)
            if s2 == s or people[s] != people[s2] or a[s] == a[s2]:
                continue
            x, y = a[s], a[s2]
            before = local(s, x) + local(s2, y)
            a[s], a[s2] = y, x
            d = local(s, y) + local(s2, x) - before
            if not (d <= 0 or rng.random() < math.exp(-d / T)):
                a[s], a[s2] = x, y
    return [tiles[i] for i in a], P, [index[t[0]] for t in assign]


def conflicts(assign, neighbors, min_weight=4):
    """co-visible pairs (counted once, weight 1 only) that share a heavy tag."""
    out = 0
    for s, row in enumerate(neighbors):
        for m, w in row:
            if m > s and w >= 1.0 and any(TAG_WEIGHT.get(t, 1) >= min_weight
                                          for t in assign[s][3] & assign[m][3]):
                out += 1
    return out


def refine_motion(rows, pool, rng):
    R, C = len(rows), COLS
    slot = lambda c, r: c * R + r
    assign = [None] * (R * C)
    for r in range(R):
        for c in range(C):
            assign[slot(c, r)] = rows[r][c]
    neighbors = [[] for _ in assign]
    p_opp = (2 * VIEW_ROWS - 1) / R
    for c in range(C):
        for r in range(R):
            for c2 in range(C):
                if abs(c - c2) > VIEW_COLS - 1:
                    continue
                for r2 in range(R):
                    if (c, r) == (c2, r2):
                        continue
                    if (c - c2) % 2 == 0:       # columns that move in step
                        d = min((r - r2) % R, (r2 - r) % R)
                        w = 1.0 if d < VIEW_ROWS else 0.0
                    else:                        # columns that move the other way
                        w = p_opp
                    if w:
                        neighbors[slot(c, r)].append((slot(c2, r2), w))
    before = conflicts(assign, neighbors)
    best, _, _ = anneal(assign, neighbors, pool, MOTION_REPEAT, rng, 700000, theme_cap=lambda x: THEME_CAPS.get(x, MOTION_THEME_CAP))
    after = conflicts(best, neighbors)
    print("moving wall: %d -> %d pairs that can be seen together share an accessory/style tag" % (before, after))
    byt = collections.Counter()
    for s_, row in enumerate(neighbors):
        for m, w in row:
            if m > s_ and w >= 1.0:
                for t in best[s_][3] & best[m][3]:
                    if TAG_WEIGHT.get(t, 1) >= 4:
                        byt[t] += 1
    print("   by tag:", dict(byt))
    tc = collections.Counter(theme(t) for t in best)
    print("   slots by subject:", {k: tc[k] for k in THEME_TAGS}, "| portraits:", sum(1 for t in best if t[2]), "of", len(best))
    return [[best[slot(c, r)] for c in range(C)] for r in range(R)]


def refine_static(rows, pool, rng):
    R, C = len(rows), COLS
    assign = [t for row in rows for t in row]
    neighbors = [[] for _ in assign]
    for r in range(R):
        for c in range(C):
            for r2 in range(R):
                for c2 in range(C):
                    if (r, c) != (r2, c2):
                        near = max(abs(r - r2), abs(c - c2)) <= 3
                        neighbors[r * C + c].append((r2 * C + c2, 1.0 if near else 0.35))
    before = conflicts(assign, neighbors)
    best, _, _ = anneal(assign, neighbors, pool, 1, rng, 120000)
    print("still wall: %d -> %d pairs share an accessory/style tag" % (before, conflicts(best, neighbors)))
    return [best[r * C:(r + 1) * C] for r in range(R)]



def simulate(rows, label="moving wall"):
    """Walk the drift: at each moment, which tiles are on screen? Columns alternate
    up/down at one pace (app.js), the screen shows about 7 columns x 4 rows of the
    16-row loop. Reports the most tiles of one subject on screen at once."""
    R, C = len(rows), COLS
    SHOW_COLS, SHOW_ROWS = range(1, 8), 4       # a 1500 x 1000 screen: ~7 columns x 4 rows (~28 tiles)
    worst = collections.Counter(); mean = collections.Counter(); frames = 0
    dup_frames = fam_dup_frames = 0
    for step in range(R * 8):
        phase = step / 8.0
        seen = []
        for c in SHOW_COLS:
            off = phase if c % 2 == 0 else -phase
            top = round(off) % R
            for k in range(SHOW_ROWS):
                seen.append(rows[(top + k) % R][c])
        frames += 1
        cnt = collections.Counter(theme(t) for t in seen if theme(t) in THEME_TAGS)
        for k in THEME_TAGS:
            worst[k] = max(worst[k], cnt[k]); mean[k] += cnt[k]
        paths = [t[0] for t in seen]
        dup_frames += len(paths) != len(set(paths))
        fams = collections.Counter(t[1] for t in seen if not t[2])
        fam_dup_frames += any(v > 1 for v in fams.values())
    print("%s, over the whole drift: most on screen at once %s" % (label, dict(worst)))
    print("   average on screen %s" % {k: round(mean[k] / frames, 1) for k in THEME_TAGS})
    print("   moments with an identical picture twice: %d%%; with two pictures of one object/animal scene: %d%%"
          % (100 * dup_frames // frames, 100 * fam_dup_frames // frames))


def compose(rows, dest, quality, lite):
    pitch_w, pitch_h = TILE_W + GAP, TILE_H + GAP
    w, h = COLS * pitch_w, len(rows) * pitch_h
    wall = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mask = Image.new("L", (TILE_W, TILE_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, TILE_W - 1, TILE_H - 1), RADIUS, fill=255)
    cache = {}
    for r, row in enumerate(rows):
        for c, (path, *_) in enumerate(row):
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
    pool = collect(STATIC_PER_SAMPLE)
    compose(refine_static(arrange_static(pool, rng), pool, rng), os.path.join(FIG, "wall.webp"), 72, STATIC_LITE)
    pool = collect(MOTION_PER_SAMPLE)
    rows = refine_motion(arrange_motion(pool, rng), pool, rng)
    simulate(rows)
    compose(rows, os.path.join(FIG, "wall-motion.webp"), 66, MOTION_LITE)


if __name__ == "__main__":
    main()
