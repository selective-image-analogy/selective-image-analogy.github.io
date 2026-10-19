# -*- coding: utf-8 -*-
"""Build the Method section's pipeline figure as SVG from its draw.io source.

`new figures/Architecture.drawio` is the authors' working page: the paper's
Fig. 2 plus scratch drawings around it. This keeps the cells inside FIG_RECT,
exports them to PDF with draw.io desktop (so the text is set in the figure's
own fonts), turns the PDF into SVG with pdftocairo (glyphs become outlines, so
the page needs no fonts), shrinks the embedded photos to what the page can
show, and writes static/figures/architecture.svg.

The figure has no background, so it sits on the page itself; for the dark
theme each still figure also gets a "-dark" twin whose bare black lines and
labels are drawn light (see darken).

It also splits that figure in two for the page's living version (see
split_live): architecture-base.svg, the figure without the parts that move,
and architecture-live.svg, a transparent layer of just those parts, animated
by CSS inside it. Stacked, they are the figure. Only the small layer is
redrawn as it moves, and under prefers-reduced-motion it holds still.

Needs draw.io desktop (https://github.com/jgraph/drawio-desktop; set DRAWIO to
its binary if it is not on PATH), pdftocairo (poppler) and the fonts the
figure uses: Comic Sans MS, Architects Daughter, Open Sans, Arial and Times New
Roman. Without them draw.io silently substitutes others and the labels change.
On a headless Linux box it runs draw.io under xvfb-run.

    python tools/build_arch.py          # everything
    python tools/build_arch.py data     # only the two training-data figures
    python tools/build_arch.py teaser   # only the teaser
"""
import base64
import hashlib
import io
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "new figures", "Architecture.drawio")
OUT = os.path.join(ROOT, "static", "figures", "architecture.svg")
OUT_BASE = os.path.join(ROOT, "static", "figures", "architecture-base.svg")
OUT_LIVE = os.path.join(ROOT, "static", "figures", "architecture-live.svg")
# the dark-theme versions of the still figures ("-dark" before ".svg")
DARK_INK = "#E2E8F0"
DARK_BG = (0x1A / 255, 0x22 / 255, 0x33 / 255)   # the page's dark surface
DARK_CONTRAST = 4.5                      # what ink on the bare page must reach against it
DARK_LINE = 1.6                          # their lines on the bare page, thicker by this
DARK_BEAD = "#C7D2FE"                    # beads running over the bare page, dark theme

# The paper figure on the draw.io page, in page units (x0, y0, x1, y1). A
# top-level cell is kept when its centre falls inside.
FIG_RECT = (2225, 1335, 3890, 2040)
# Pixels kept across a figure's width in its embedded photos: the pipeline
# figure is shown ~1100 px wide, enlarged up to 1.8x on hover, on 2x screens.
FIGURE_PX = 4200

# The training-data figures come from the paper's own PDFs, which diagrams.net
# exported from figures/Stage1-3.drawio and phase4.drawio: the draw.io command
# line does not set their LaTeX labels reliably, those exports do. They get the
# same treatment as the pipeline figure: SVG, photos shrunk, no background, a
# dark twin. (source in new figures/, output stem in static/figures/)
DATA_FIGURES = [("DataGeneration.pdf", "data-generation"), ("DataFormat.pdf", "data-format")]
DATA_FIGURE_PX = 3200                    # shown smaller: the lightbox is the most they need

# The teaser (the paper's Fig. 1) comes from its draw.io source, a copy of
# figures/teaser_SIA_final_draft1.drawio, the file behind teaser_SIA_V6.pdf.
# Its living layer is a build that plays once (see live_teaser). In that copy
# the authors' on/off switch picture is replaced by two draw.io toggles in the
# site's switch colours (off red, on green); copy the file again and redo that.
TEASER_SRC = os.path.join(ROOT, "new figures", "Teaser.drawio")
TEASER_PX = 2400                         # shown up to ~1200 px wide, on 2x screens
TEASER_LITE = (900, 55)                  # the light living layer's photos: px across, quality
TEASER_CARD_PX = 1600                    # teaser.jpg, the link-preview image (og:image)
ACCENT, ACCENT_DARK = "#3B5BDB", "#8EA8FF"   # the page's accent, light and dark


def crop_page(src, dst):
    """Write a copy of the draw.io file holding only the figure's cells."""
    tree = ET.parse(src)
    root = tree.getroot().find(".//root")

    def cell(c):
        return c if c.tag == "mxCell" else c.find("mxCell")

    cells = {c.get("id"): c for c in root}

    def parent(c):
        return cell(c).get("parent")

    def geometry(c):
        return cell(c).find("mxGeometry")

    def box(cid):
        """Absolute bounds of a vertex (children are relative to their group)."""
        c = cells.get(cid)
        g = geometry(c) if c is not None else None
        if g is None:
            return None
        x, y = float(g.get("x", 0)), float(g.get("y", 0))
        p = parent(c)
        while p not in (None, "0", "1"):
            pg = geometry(cells[p])
            x, y = x + float(pg.get("x", 0)), y + float(pg.get("y", 0))
            p = parent(cells[p])
        return x, y, x + float(g.get("width", 0)), y + float(g.get("height", 0))

    x0, y0, x1, y1 = FIG_RECT
    alive = {"0", "1"}
    for cid, c in cells.items():
        if cid in ("0", "1") or parent(c) != "1":
            continue
        if cell(c).get("edge") == "1":
            pts = [(float(p.get("x", 0)), float(p.get("y", 0))) for p in geometry(c).iter("mxPoint")]
            for end in ("source", "target"):
                b = box(cell(c).get(end)) if cell(c).get(end) else None
                if b:
                    pts += [b[:2], b[2:]]
            if not pts:
                continue
            b = (min(p[0] for p in pts), min(p[1] for p in pts),
                 max(p[0] for p in pts), max(p[1] for p in pts))
        else:
            b = box(cid)
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            alive.add(cid)
    # the kept groups' cells, at any depth
    grew = True
    while grew:
        grew = False
        for cid, c in cells.items():
            if cid not in alive and parent(c) in alive and parent(c) not in ("0", "1"):
                alive.add(cid)
                grew = True
    for cid, c in cells.items():
        if cid not in alive:
            root.remove(c)
    tree.write(dst, encoding="utf-8")
    return len(alive) - 2


def drawio_command():
    exe = os.environ.get("DRAWIO") or shutil.which("drawio") or shutil.which("draw.io")
    for guess in (r"C:\Program Files\draw.io\draw.io.exe",
                  "/Applications/draw.io.app/Contents/MacOS/draw.io", "/opt/drawio/drawio"):
        if not exe and os.path.exists(guess):
            exe = guess
    if not exe:
        sys.exit("draw.io desktop not found; set DRAWIO to its binary")
    cmd = [exe]
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    return cmd


def export_pdf(drawio, pdf):
    env = dict(os.environ)
    if sys.platform.startswith("linux") and os.geteuid() == 0:
        env["ELECTRON_DISABLE_SANDBOX"] = "1"    # Chromium refuses root otherwise
    subprocess.run(drawio_command() + ["-x", "-f", "pdf", "--crop", "-o", pdf, drawio],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(pdf):
        raise RuntimeError("draw.io wrote no PDF")


IMAGE = re.compile(r'<image id="([^"]+)" x="0" y="0" width="(\d+)" height="(\d+)" '
                   r'xlink:href="data:image/png;base64,([^"]+)"/>\n?')
USE = re.compile(r'<use xlink:href="#([^"]+)"[^>]*?transform="matrix\(([^)]+)\)"')


def shrink_images(svg, px_per_pt, quality=82):
    """Merge identical embedded images and re-encode each as WebP, sized to
    the largest it is drawn at times px_per_pt."""
    drawn = {}
    for m in USE.finditer(svg):
        a, b, c, d = (float(v) for v in m.group(2).split(",")[:4])
        sx, sy = math.hypot(a, b), math.hypot(c, d)
        old = drawn.get(m.group(1), (0, 0))
        drawn[m.group(1)] = (max(old[0], sx), max(old[1], sy))
    masks = set(re.findall(r'<mask id="[^"]+">\s*<g[^>]*>\s*<use xlink:href="#([^"]+)"', svg))

    first, alias = {}, {}
    def encode(m):
        iid, w, h, data = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        key = hashlib.sha1(data.encode()).hexdigest()
        if key in first:
            alias[iid] = first[key]
            return ""
        first[key] = iid
        sx, sy = drawn.get(iid, (1, 1))
        scale = min(1.0, max(w * sx, h * sy) * px_per_pt / max(w, h))
        im = Image.open(io.BytesIO(base64.b64decode(data)))
        im = im.convert("L" if iid in masks else "RGB")
        if scale < 1:
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=90 if iid in masks else quality, method=6)
        return ('<image id="%s" x="0" y="0" width="%d" height="%d" xlink:href="data:image/webp;base64,%s"/>\n'
                % (iid, w, h, base64.b64encode(buf.getvalue()).decode()))

    svg = IMAGE.sub(encode, svg)
    for dup, keep in alias.items():
        svg = svg.replace('xlink:href="#%s"' % dup, 'xlink:href="#%s"' % keep)
    return svg, len(first), len(alias)


SVG_NS, XLINK_NS = "http://www.w3.org/2000/svg", "http://www.w3.org/1999/xlink"
HREF = "{%s}href" % XLINK_NS
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

# fills that pick out the moving parts (pdftocairo writes colours as rgb(%))
PINK, YELLOW = "rgb(100%, 63.529968%, 61.178589%)", "rgb(98.429871%, 87.838745%, 65.489197%)"
BLUE, MAGENTA = "rgb(0%, 0%, 100%)", "rgb(100%, 0%, 100%)"
EX_RED = "rgb(97.24884%, 68.238831%, 68.238831%)"
BLACK = "rgb(0%, 0%, 0%)"
LORA_PANEL = (392, 224, 775, 495)        # pt; its four token columns split at
LORA_COLUMNS = ((477, "#3F9C50"), (604, "#DB3A41"), (686, "#3B6FC7"), (9e9, "#D41BD4"))
CSV_PANEL = (787, 225, 1187, 493)
CSV_PROMPTS = (795, 350, 935, 480)      # the six contrastive prompts
CSV_PLOT = (1020, 376, 1172, 456)
ENCODER = "rgb(100%, 94.898987%, 79.998779%)"
CSV_SEND_AT, CSV_SEND_STEP = 1.3, 0.28  # s: when the first prompt goes, then each next
FLOW = "#7A4BE0"                         # pulses elsewhere

LIVE_CSS = """
.mv{transform-box:fill-box}
.nudge{animation:nudge 2.8s ease-in-out infinite}
.nudge.down{animation-name:nudge-down}
@keyframes nudge{50%{transform:translateX(2.6px)}}
@keyframes nudge-down{50%{transform:translateY(2.6px)}}
.flame{transform-origin:50% 88%;animation:flicker 1.7s ease-in-out infinite}
@keyframes flicker{25%{transform:scale(.95,1.06) rotate(-2deg)}55%{transform:scale(1.04,.96)}
  80%{transform:scale(.98,1.04) rotate(1.5deg)}}
.drift{animation:drift 7s ease-in-out infinite alternate}
@keyframes drift{33%{transform:translate(1.8px,-1.4px)}66%{transform:translate(-1.4px,1.6px)}
  100%{transform:translate(.8px,1.2px)}}
/* the CSV panel tells its story every 7 s: Qwen-VL turns as it writes the
   prompts, they go to the text encoder one by one, it works, the samples
   gather to their two means, which swell, and the arrow between them, the
   edit direction, draws itself again */
.csv{animation-duration:7s;animation-iteration-count:infinite;animation-timing-function:ease-in-out}
.spin{transform-origin:50% 50%;animation-name:spin}
@keyframes spin{0%{transform:rotate(0)}20%,100%{transform:rotate(360deg)}}
.send{animation-name:send}
@keyframes send{0%,8%,100%{transform:none}3.5%{transform:translateX(6px)}}
.enc{transform-origin:50% 50%;animation-name:enc;animation-delay:3s}
@keyframes enc{0%,11%,100%{transform:none}4.5%{transform:scale(1.09)}}
.gather{animation-name:gather;animation-delay:3.6s}
@keyframes gather{0%,36%,100%{transform:none}12%,22%{transform:translate(calc(var(--dx)*.8),calc(var(--dy)*.8))}}
.means{transform-origin:50% 50%;animation-name:means;animation-delay:3.6s}
@keyframes means{0%,34%,100%{transform:none}13%{transform:scale(1.45)}22%{transform:scale(1.25)}}
.draw{transform-origin:3% 64%;animation-name:draw;animation-delay:3.5s}
@keyframes draw{0%,100%{transform:none;opacity:1}5%,17%{transform:scale(.04);opacity:0}32%{transform:none;opacity:1}}
.beads path{fill:none;stroke-linecap:round;stroke-dasharray:.01 22;animation:march 2.4s linear infinite}
.beads .halo{stroke-width:7;opacity:.2}
.beads .bead{stroke-width:3}
@keyframes march{to{stroke-dashoffset:-22.01}}
.glow path{fill:none;stroke:#E0464E;stroke-width:1.8;stroke-linejoin:round;opacity:0;
  animation:glow 3.6s ease-in-out infinite}
@keyframes glow{50%{opacity:.95}}
@media (prefers-reduced-motion:reduce){.mv{animation:none!important}.beads,.glow{display:none}}
/* (the page also swaps in the still figure then: not every browser
   passes that preference into an SVG shown as an image) */
"""


def _numbers(d):
    v = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(v[0::2], v[1::2]))


def _matrix(el):
    m = re.search(r"matrix\(([^)]+)\)", el.get("transform") or "")
    return [float(v) for v in m.group(1).split(",")] if m else [1, 0, 0, 1, 0, 0]


def _apply(m, pts):
    return [(m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]) for x, y in pts]


def _box(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _inside(b, r):
    return r[0] <= b[0] and r[1] <= b[1] and b[2] <= r[2] and b[3] <= r[3]


def _leaves(el):
    """The drawn things under el: paths, and image uses (alone or masked)."""
    tag = el.tag.split("}")[1]
    if tag == "path" or (tag == "g" and el.get("mask")) or tag == "use":
        return [el]
    if tag == "g":
        return [x for c in el for x in _leaves(c)]
    return []


def split_live(svg):
    """Split the figure into a still base and a living layer, by part:
       the fat arrows nudge along their direction, the AnaLoRA/ExLoRA flames
       flicker, and the CSV panel plays its story (see LIVE_CSS), its samples
       drifting meanwhile. On top, beads run slowly along the connectors
       (in the LoRA panel in the colour of the tokens each column carries)
       and ExLoRA's outline glows. Returns (base, live) SVG text."""
    root = ET.fromstring(svg.encode("utf-8"))
    defs = root.find("{%s}defs" % SVG_NS)
    body = [c for c in root if c is not defs]

    # the flame is the one image drawn through a mask four or more times
    masked = [u.get(HREF) for c in body for u in c.iter("{%s}use" % SVG_NS)
              if any(g.get("mask") for g in c.iter("{%s}g" % SVG_NS))]
    flame = max(set(masked), key=masked.count) if masked else None

    def run(top):
        """(baseline, x0, x1) when top is one line of text, else None."""
        uses = list(top.iter("{%s}use" % SVG_NS))
        if not uses or any(not (u.get(HREF) or "").startswith("#glyph") for u in uses) \
                or any(True for _ in top.iter("{%s}path" % SVG_NS)):
            return None
        ys = {round(float(u.get("y"))) for u in uses}
        xs = [float(u.get("x")) for u in uses]
        return (ys.pop(), min(xs), max(xs)) if len(ys) == 1 else None

    def kind(top):
        r = run(top)
        if r:                                         # a contrastive prompt
            return "csv send" if _inside((r[1], r[0], r[2], r[0]), CSV_PROMPTS) else None
        leaves = _leaves(top)
        if len(leaves) != 1:
            return None
        el = leaves[0]
        if el.tag.endswith("g"):
            u = el.find("{%s}use" % SVG_NS)
            if u.get(HREF) == flame:
                return "flame"
            m = _matrix(u)
            return "csv spin" if _inside((m[4], m[5], m[4], m[5]), CSV_PANEL) else None   # Qwen-VL
        if not el.tag.endswith("path"):
            return None
        fill, b = el.get("fill"), _box(_apply(_matrix(el), _numbers(el.get("d"))))
        small = (b[2] - b[0]) * (b[3] - b[1]) < 2500
        if fill in (PINK, YELLOW) and small:
            return "nudge"
        if fill == "url(#linear-pattern-1)":
            return "nudge down"                       # attention -> LoRA panel
        if fill == "url(#linear-pattern-0)":
            return "csv draw"                         # difference of means
        if fill == ENCODER and _inside(b, CSV_PANEL):
            return "csv enc"
        if fill in (BLUE, MAGENTA) and _inside(b, CSV_PLOT):
            return "csv means" if b[2] - b[0] > 11 else "drift"
        return None

    moving = [(top, kind(top)) for top in body]
    moving = [(t, k) for t, k in moving if k]
    # the Text Encoder's label moves with its box
    box = next(_box(_apply(_matrix(_leaves(t)[0]), _numbers(_leaves(t)[0].get("d"))))
               for t, k in moving if k == "csv enc")
    for top in body:
        r = run(top)
        if r and _inside((r[1], r[0], r[2], r[0]), box):
            moving.append((top, "csv enc"))
    order = {id(t): i for i, t in enumerate(body)}
    moving.sort(key=lambda tk: order[id(tk[0])])
    count = {}
    for _, k in moving:
        k = k.replace("csv ", "")
        count[k.split()[0]] = count.get(k.split()[0], 0) + 1
    if count != {"nudge": 6, "flame": 5, "draw": 1, "means": 2, "drift": 6, "spin": 1,
                 "send": 24, "enc": 3}:
        raise RuntimeError("moving parts not as expected (figure changed?): %r" % count)

    # connectors, oriented downstream: towards their arrowhead, else down in
    # the LoRA panel and rightwards elsewhere
    heads, lines, ex = [], [], []
    for top in body:
        for el in _leaves(top):
            if not el.tag.endswith("path"):
                continue
            pts = _apply(_matrix(el), _numbers(el.get("d")))
            b = _box(pts)
            closed = "Z" in el.get("d")
            if closed and el.get("fill") == BLACK and b[2] - b[0] < 8 and b[3] - b[1] < 8:
                heads.append(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
            elif closed and el.get("fill") == EX_RED:
                ex.append(el.get("d"))
            elif (not closed and el.get("fill") == "none" and el.get("stroke") == BLACK
                  and not el.get("stroke-dasharray") and re.fullmatch(r"[ML\d\s.\-]+", el.get("d"))):
                length = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
                if length >= 14:
                    lines.append(pts)
    if len(ex) != 2:
        raise RuntimeError("expected ExLoRA's two halves, found %d" % len(ex))

    # the light panels, boxes and photos; a connector mostly outside them runs
    # over the bare page, where the dark theme draws its beads light
    panels = []
    for top in body:
        for el in _leaves(top):
            if el.tag.endswith("path") and "Z" in el.get("d"):
                c = _rgb(el.get("fill"))
                if c and 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] > 0.55:
                    panels.append(_box(_apply(_matrix(el), _numbers(el.get("d")))))

    def bare(pts):
        samples = []
        for p, q in zip(pts, pts[1:]):
            n = max(1, int(math.dist(p, q) / 3))
            samples += [(p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n) for i in range(n)]
        on = sum(any(_inside((x, y, x, y), b) for b in panels) for x, y in samples)
        return on < len(samples) / 2

    beads = []
    for pts in lines:
        near = lambda p: min((math.dist(p, h) for h in heads), default=99)
        a, z = pts[0], pts[-1]
        if near(a) < near(z) and near(a) < 6:
            pts = pts[::-1]
        elif min(near(a), near(z)) >= 6:
            b = _box(pts)
            if _inside(b, LORA_PANEL):
                pts = pts if z[1] >= a[1] else pts[::-1]
            elif z[0] < a[0] - 1:
                pts = pts[::-1]
        b = _box(pts)
        colour = FLOW
        if _inside(b, LORA_PANEL):
            colour = next(c for x, c in LORA_COLUMNS if pts[0][0] < x)
        d = "M" + " L".join("%.2f %.2f" % p for p in pts)
        extra = " bare" if bare(pts) else ""
        beads.append('<path class="halo%s" stroke="%s" d="%s"/><path class="bead%s" stroke="%s" d="%s"/>'
                     % (extra, colour, d, extra, colour, d))

    # the living layer: the moving parts, wrapped so CSS can transform them,
    # with only the defs they need
    width = float(root.get("viewBox").split()[2])

    def centre(top):
        el = _leaves(top)[0]
        if el.tag.endswith("path"):
            b = _box(_apply(_matrix(el), _numbers(el.get("d"))))
            return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        m = _matrix(el.find("{%s}use" % SVG_NS))
        return m[4], m[5]

    means = {_leaves(t)[0].get("fill"): centre(t) for t, k in moving if k == "csv means"}
    rows = sorted({run(t)[0] for t, k in moving if k == "csv send"})
    live_parts, encoder = [], []
    for i, (top, k) in enumerate(moving):
        xml = ET.tostring(top, encoding="unicode")
        if k == "csv enc":                    # box and label scale as one
            if not encoder:
                live_parts.append(encoder)
            encoder.append(xml)
        elif k == "csv send":                 # the prompts go out one row at a time
            live_parts.append('<g class="mv %s" style="animation-delay:%.2fs">%s</g>'
                              % (k, CSV_SEND_AT + CSV_SEND_STEP * rows.index(run(top)[0]), xml))
        elif k == "drift":                    # a sample: drifts, and gathers to its mean
            (x, y), (mx, my) = centre(top), means[_leaves(top)[0].get("fill")]
            live_parts.append('<g class="mv csv gather" style="--dx:%.2fpx;--dy:%.2fpx">'
                              '<g class="mv drift" style="animation-delay:%.2fs">%s</g></g>'
                              % (mx - x, my - y, -(i * 0.83) % 3.4, xml))
        elif k.startswith("csv"):             # timed by the story in LIVE_CSS
            live_parts.append('<g class="mv %s">%s</g>' % (k, xml))
        else:
            # the arrows nudge in a wave that runs left to right; the flames
            # are simply out of step with each other
            delay = (-(1 - centre(top)[0] / width) * 2.8 if k.startswith("nudge")
                     else -(i * 0.83) % 3.4)
            live_parts.append('<g class="mv %s" style="animation-delay:%.2fs">%s</g>' % (k, delay, xml))
        root.remove(top)
    live_body = "".join(p if isinstance(p, str) else '<g class="mv csv enc">%s</g>' % "".join(p)
                        for p in live_parts)
    need, todo = set(), set(re.findall(r'(?:url\(#|href="#)([^)"]+)', live_body))
    by_id = {el.get("id"): el for el in defs.iter() if el.get("id")}
    while todo:
        i = todo.pop()
        if i in need or i not in by_id:
            continue
        need.add(i)
        todo |= set(re.findall(r'(?:url\(#|href="#)([^)"]+)', ET.tostring(by_id[i], encoding="unicode")))
    # (the glyphs sit one level down in defs, inside a group of their own)
    live_defs = "".join(ET.tostring(by_id[i], encoding="unicode") for i in sorted(need))
    live = ('<svg xmlns="%s" xmlns:xlink="%s" width="%s" height="%s" viewBox="%s">'
            '<style>%s</style><defs>%s</defs><g class="beads">%s</g>%s'
            '<g class="glow">%s</g></svg>'
            % (SVG_NS, XLINK_NS, root.get("width"), root.get("height"), root.get("viewBox"),
               LIVE_CSS.strip(), live_defs, "".join(beads), live_body,
               "".join('<path d="%s"/>' % d for d in ex)))
    base = ET.tostring(root, encoding="unicode")
    dark_live = live.replace("</style>", ".beads .bare{stroke:%s}.beads .halo.bare{opacity:.3}</style>"
                             % DARK_BEAD, 1)
    return base, live, dark_live, len(beads), count


def _rgb(fill):
    m = re.fullmatch(r"rgb\(([\d.]+)%, ([\d.]+)%, ([\d.]+)%\)", fill or "")
    return tuple(float(v) / 100 for v in m.groups()) if m else None


def drop_background(svg, required=True):
    """Take out the page-sized white rectangle under the figure."""
    root = ET.fromstring(svg.encode("utf-8"))
    w, h = (float(v) for v in root.get("viewBox").split()[2:])
    for parent in root.iter():
        for el in list(parent):
            if el.tag.endswith("path") and el.get("fill") == "rgb(100%, 100%, 100%)":
                b = _box(_apply(_matrix(el), _numbers(el.get("d"))))
                if b[2] - b[0] > 0.95 * w and b[3] - b[1] > 0.95 * h:
                    parent.remove(el)
                    return ET.tostring(root, encoding="unicode")
    if required:
        raise RuntimeError("no white background found")
    return svg


def _lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(c1, c2):
    """WCAG contrast ratio of two sRGB colours (0-1 channels)."""
    def rel(c):
        lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    a, b = sorted((rel(c1), rel(c2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


RGB = r"rgb\([\d.]+%, [\d.]+%, [\d.]+%\)"


def _dark_colours(xml):
    return [c for c in map(_rgb, re.findall(RGB, xml)) if _contrast(c, DARK_BG) < DARK_CONTRAST]


def _lift(xml):
    """Ink made readable on the dark page: black becomes DARK_INK; any other
    colour short of DARK_CONTRAST against it (a grey label, a deep green
    "Keep") moves toward white just until it is not. Colours that already
    stand out, like the magenta frames, stay as they are."""
    def swap(m):
        c = _rgb(m.group(0))
        if _contrast(c, DARK_BG) >= DARK_CONTRAST:
            return m.group(0)
        if max(c) < 0.05:
            return DARK_INK
        t = 0.0
        while t < 1 and _contrast([v + (1 - v) * t for v in c], DARK_BG) < DARK_CONTRAST:
            t += 0.05
        return "rgb(%.1f%%, %.1f%%, %.1f%%)" % tuple(100 * (v + (1 - v) * t) for v in c)
    return re.sub(RGB, swap, xml)


def opaque(svg):
    """Translucent fills (draw.io's panels at 40-50 %) flattened to the solid
    colour they show over white, so they keep that look on any page."""
    def flat(m):
        c, a = _rgb(m.group(1)), float(m.group(2))
        return 'fill="rgb(%.2f%%, %.2f%%, %.2f%%)" fill-opacity="1"' % tuple(100 * (a * v + 1 - a) for v in c)
    return re.sub(r'fill="(%s)" fill-opacity="(0(?:\.\d+)?)"' % RGB, flat, svg)


def trim(svg, pdf, pad=6):
    """Fit the viewBox to what the PDF draws, plus pad points of air."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-png", "-r", "36", "-singlefile", pdf, os.path.join(tmp, "p")], check=True)
        a = np.asarray(Image.open(os.path.join(tmp, "p.png")).convert("L"))
    rows, cols = np.where((a < 246).any(axis=1))[0], np.where((a < 246).any(axis=0))[0]
    x0, y0 = cols.min() * 2 - pad, rows.min() * 2 - pad             # 36 dpi: 2 pt a pixel
    w, h = (cols.max() + 1) * 2 + pad - x0, (rows.max() + 1) * 2 + pad - y0
    root = ET.fromstring(svg.encode("utf-8"))
    root.set("viewBox", "%d %d %d %d" % (x0, y0, w, h))
    root.set("width", str(w))
    root.set("height", str(h))
    return ET.tostring(root, encoding="unicode")


def darken(svg):
    """The figure for the dark theme. With no white under it, the black lines
    and labels that sit on the bare page (the Concat column, its "+", the
    connectors into and out of the transformer) would vanish, so a copy of
    every dark element is drawn over the original, made light (see _lift) and
    its lines a little thicker, masked to the bare page: everything but the
    figure's light panels, boxes and photos, where the dark ink stays."""
    root = ET.fromstring(svg.encode("utf-8"))
    defs = root.find("{%s}defs" % SVG_NS)
    vb = root.get("viewBox")
    holes, boxes, copies = [], [], []
    for el in root.iter():
        tag = el.tag.split("}")[1]
        if tag == "path" and "Z" in (el.get("d") or ""):
            c = _rgb(el.get("fill"))
            if c and 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] > 0.55:
                t = ' transform="%s"' % el.get("transform") if el.get("transform") else ""
                holes.append('<path d="%s"%s/>' % (el.get("d"), t))
                boxes.append(_box(_apply(_matrix(el), _numbers(el.get("d")))))
        elif tag == "use" and not (el.get(HREF) or "").startswith("#glyph"):
            img = next((i for i in defs.iter("{%s}image" % SVG_NS) if "#" + i.get("id") == el.get(HREF)), None)
            if img is not None:                       # a photo: no ink over it
                holes.append('<rect width="%s" height="%s" transform="%s"/>'
                             % (img.get("width"), img.get("height"), el.get("transform")))
    def extent(top):
        pts = []
        for el in top.iter():
            if el.tag.endswith("path") and el.get("d"):
                pts += _apply(_matrix(el), _numbers(el.get("d")))
            elif el.tag.endswith("use") and el.get("x"):    # a glyph, at its baseline
                x, y = float(el.get("x")), float(el.get("y"))
                pts += [(x, y - 9), (x + 9, y + 3)]
        return _box(pts) if pts else None

    for top in root:
        if top is defs:
            continue
        xml = ET.tostring(top, encoding="unicode")
        if not _dark_colours(xml):
            continue
        b = extent(top)
        if b and any(_inside(b, h) for h in boxes):  # wholly on one panel: stays black
            continue
        xml = re.sub(r'stroke-width="([\d.]+)"',
                     lambda m: 'stroke-width="%.2f"' % (float(m.group(1)) * DARK_LINE), xml)
        copies.append(_lift(xml))
    x, y, w, h = vb.split()
    if not copies:
        return svg
    mask = ('<mask id="bare-page" maskUnits="userSpaceOnUse" x="%s" y="%s" width="%s" height="%s">'
            '<rect x="%s" y="%s" width="%s" height="%s" fill="#fff"/><g fill="#000">%s</g></mask>'
            % (x, y, w, h, x, y, w, h, "".join(holes)))
    text = ET.tostring(root, encoding="unicode")
    head, tail = text.rsplit("</svg>", 1)
    return head + '<defs>%s</defs><g mask="url(#bare-page)">%s</g></svg>' % (mask, "".join(copies)) + tail


def prune(svg):
    """Drop the images, masks and glyphs in defs that nothing draws any more
    (a base figure keeps them for the parts that moved to its living layer)."""
    root = ET.fromstring(svg.encode("utf-8"))
    defs = root.find("{%s}defs" % SVG_NS)
    by_id = {el.get("id"): el for el in defs.iter() if el.get("id")}
    drawn = "".join(ET.tostring(c, encoding="unicode") for c in root if c is not defs)
    need, todo = set(), set(re.findall(r'(?:url\(#|href="#)([^)"]+)', drawn))
    while todo:
        i = todo.pop()
        if i in need or i not in by_id:
            continue
        need.add(i)
        todo |= set(re.findall(r'(?:url\(#|href="#)([^)"]+)', ET.tostring(by_id[i], encoding="unicode")))
    for parent in list(defs.iter()):
        for el in list(parent):
            tag = el.tag.split("}")[1]
            if el.get("id") and el.get("id") not in need and tag in ("image", "mask", "g", "clipPath"):
                parent.remove(el)
    return ET.tostring(root, encoding="unicode")


def dark_path(path):
    return path[:-4] + "-dark.svg"


def tidy(svg, across=FIGURE_PX, quality=82):
    """Shrink the photos, and round the coordinates to two decimals, plenty
    at any size the page shows (but not the transform matrices)."""
    width = float(ET.fromstring(svg.encode("utf-8")).get("viewBox").split()[2])
    svg, kept, merged = shrink_images(svg, across / width, quality)
    svg = re.sub(r'( (?:d|x|y)="[^"]*")',
                 lambda m: re.sub(r"(\d+\.\d{2})\d+", r"\1", m.group(1)), svg)
    return svg, kept, merged


# ------------------------------------------------- the data figures, living
# Each plays a short story every 8 s over a still base, like the pipeline
# figure: beads run along the connectors that end in an arrowhead, and the
# parts below pop, turn, shake or dim in turn (see data_parts).
DATA_CSS = """
.mv{transform-box:fill-box;transform-origin:50% 50%}
.story{animation-duration:8s;animation-iteration-count:infinite;animation-timing-function:ease-in-out}
.pop{animation-name:pop}
@keyframes pop{0%,12%,100%{transform:none}5%{transform:scale(1.08)}}
.pop.big{animation-name:pop-big}
@keyframes pop-big{0%,12%,100%{transform:none}5%{transform:scale(1.2)}}
.photo{animation-name:photo}
@keyframes photo{0%,14%,100%{transform:none}6%{transform:scale(1.045)}}
.spin{animation-name:spin}
@keyframes spin{0%{transform:rotate(0)}20%,100%{transform:rotate(360deg)}}
.shake{animation-name:shake}
@keyframes shake{0%,11%,100%{transform:none}2%{transform:translateX(-3px) rotate(-5deg)}
  4%{transform:translateX(3px) rotate(5deg)}6%{transform:translateX(-2px) rotate(-3deg)}8%{transform:translateX(2px)}}
.dim{animation-name:dim}
@keyframes dim{0%,24%,100%{opacity:1;transform:none}7%,16%{opacity:.3;transform:scale(.92)}}
.beads path{fill:none;stroke-linecap:round;stroke-dasharray:.01 22;animation:march 2.4s linear infinite}
.beads .halo{stroke-width:8;opacity:.22}
.beads .bead{stroke-width:3.4}
@keyframes march{to{stroke-dashoffset:-22.01}}
@media (prefers-reduced-motion:reduce){.mv{animation:none!important}.beads{display:none}}
"""


def _sizes(defs):
    return {i.get("id"): (float(i.get("width")), float(i.get("height")))
            for i in defs.iter("{%s}image" % SVG_NS)}


def _extent(top, sizes):
    """Bounds of a top-level element: its paths, glyphs and images."""
    pts = []
    for el in top.iter():
        tag = el.tag.split("}")[1]
        if tag == "path" and el.get("d"):
            pts += _apply(_matrix(el), _numbers(el.get("d")))
        elif tag == "use":
            ref = el.get(HREF) or ""
            if ref.startswith("#glyph"):
                x, y = float(el.get("x")), float(el.get("y"))
                pts += [(x, y - 9), (x + 9, y + 3)]
            elif ref[1:] in sizes:
                w, h = sizes[ref[1:]]
                pts += _apply(_matrix(el), [(0, 0), (w, h)])
    return _box(pts) if pts else None


def _hex_lift(hx):
    """A bead colour made readable on the dark page (as _lift does ink)."""
    c = [int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    t = 0.0
    while t < 1 and _contrast([v + (1 - v) * t for v in c], DARK_BG) < DARK_CONTRAST:
        t += 0.05
    return "#%02X%02X%02X" % tuple(round(255 * (v + (1 - v) * t)) for v in c)


def data_parts(stem, body, ext, sizes, unit):
    """(members, classes, delay in s) for each moving part of a data figure,
    found by shape and place. The story's timing is in the delays."""
    def single(top):
        lv = _leaves(top)
        return lv[0] if len(lv) == 1 else None

    def closed(top):
        el = single(top)
        return el is not None and el.tag.endswith("path") and "Z" in el.get("d") and el.get("fill") not in (None, "none")

    def photo(top):
        el = single(top)
        return el is not None and el.tag.endswith("use") and (el.get(HREF) or "")[1:] in sizes

    def masked(top):
        el = single(top)
        return el is not None and el.tag.endswith("g") and el.get("mask")

    def where(test):
        return [t for t in body if test(t, ext[id(t)])]

    def wh(b):
        return b[2] - b[0], b[3] - b[1]

    parts = []
    if stem == "data-generation":
        chips = sorted(where(lambda t, b: closed(t) and b[0] < 60 and 300 < wh(b)[0] < 340 and 38 < wh(b)[1] < 48),
                       key=lambda t: ext[id(t)][1])
        flux = where(lambda t, b: closed(t) and 740 < b[0] < 780 and 55 < wh(b)[1] < 75)
        top_row = sorted(where(lambda t, b: photo(t) and 120 < b[1] < 140), key=lambda t: ext[id(t)][0])
        recipe = sorted(where(lambda t, b: photo(t) and 525 < b[1] < 540), key=lambda t: ext[id(t)][0])
        qwen = where(lambda t, b: masked(t) and 1450 < b[0] < 1550 and wh(b)[0] > 120)
        keep = where(lambda t, b: masked(t) and b[0] > 1780 and b[1] < 500)
        reject = where(lambda t, b: masked(t) and b[0] > 1780 and b[1] > 500)
        found = (len(chips), len(flux), len(top_row), len(recipe), len(qwen), len(keep), len(reject))
        if found != (4, 1, 4, 4, 1, 1, 1):
            raise RuntimeError("data-generation parts not as expected: %r" % (found,))
        # panel 1: the style source joins in, Flux-Klein renders, the result
        parts += [(unit(top_row[2]), "photo", 0.3), (unit(flux[0]), "pop", 1.1), (unit(top_row[3]), "photo", 1.9)]
        # panel 2: one edit at a time, its chip and then the photo that adds it
        for k, at in enumerate((2.6, 3.3, 4.0, 4.4)):
            parts.append((unit(chips[k]), "pop", at))
        for k, at in ((1, 2.8), (2, 3.5), (3, 4.8)):
            parts.append((unit(recipe[k]), "photo", at))
        # the check: Qwen-VL turns, then keep or reject
        parts += [(unit(qwen[0]), "spin", 5.4), (unit(keep[0]), "pop big", 6.9), (unit(reject[0]), "shake", 7.2)]
    else:
        legend = sorted(where(lambda t, b: closed(t) and b[0] < 70 and 390 < wh(b)[0] < 410 and 50 < wh(b)[1] < 58),
                        key=lambda t: ext[id(t)][1])
        recipe = sorted(where(lambda t, b: closed(t) and 270 < b[1] < 280 and 1130 < b[0] < 1460 and 50 < wh(b)[1] < 58),
                        key=lambda t: ext[id(t)][0])
        subset = sorted(where(lambda t, b: closed(t) and 640 < b[1] < 652 and 50 < wh(b)[1] < 60),
                        key=lambda t: -wh(ext[id(t)])[0] * wh(ext[id(t)])[1])
        anchors = []                       # each chip once (some are drawn twice)
        for t in subset:
            b = ext[id(t)]
            if not any(_inside(b, (a[0] - 2, a[1] - 2, a[2] + 2, a[3] + 2)) for a in (ext[id(x)] for x in anchors)):
                anchors.append(t)
        anchors.sort(key=lambda t: ext[id(t)][0])
        photos = where(lambda t, b: photo(t) and wh(b)[0] > 180)
        row = lambda y: sorted((t for t in photos if abs(ext[id(t)][1] - y) < 12), key=lambda t: ext[id(t)][0])
        a_row, b_row = row(144), row(522)
        found = (len(legend), len(recipe), len(anchors), len(a_row), len(b_row))
        if found != (4, 4, 4, 2, 3):
            raise RuntimeError("data-format parts not as expected: %r" % (found,))
        # the recipe, edit by edit, in the legend and in subject a's row; A' follows
        for k in range(4):
            at = 0.4 + 0.45 * k
            parts += [(unit(legend[k]), "pop", at), (unit(recipe[k]), "pop", at)]
        parts.append((unit(a_row[1]), "photo", 2.3))
        # R within E: the retained chips step up, the suppressed ones fall back
        for k, chip in enumerate(anchors):
            c = _rgb(single(chip).get("fill"))
            retained = c[1] >= c[0]
            parts.append((unit(chip), "pop big" if retained else "dim", 3.1 + 0.25 * k))
        # the target, B'_R, then B' with every edit
        parts += [(unit(b_row[1]), "photo", 4.7), (unit(b_row[2]), "photo", 5.4)]
    return parts


def live_data(svg, stem):
    """Split a data figure into its still base and living layer (light and
    dark). Returns base, live, live_dark, number of connectors."""
    root = ET.fromstring(svg.encode("utf-8"))
    defs = root.find("{%s}defs" % SVG_NS)
    body = [c for c in root if c is not defs]
    sizes = _sizes(defs)
    ext = {id(t): _extent(t, sizes) for t in body}
    used = set()

    def unit(anchor, pad=2):
        """anchor and whatever lies wholly on it (a chip's icon and label)"""
        b = ext[id(anchor)]
        b = (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)
        members = [t for t in body if id(t) not in used and ext[id(t)]
                   and (t is anchor or _inside(ext[id(t)], b))]
        used.update(id(t) for t in members)
        return members

    parts = data_parts(stem, body, ext, sizes, unit)

    # connectors that end in an arrowhead: drawn lines, and the dotted ones,
    # which the PDF holds as rows of filled dots
    heads, lines, panels = [], [], []
    for top in body:
        for el in _leaves(top):
            if not el.tag.endswith("path"):
                continue
            d, fill, stroke = el.get("d"), el.get("fill"), el.get("stroke")
            pts = _apply(_matrix(el), _numbers(d))
            b = _box(pts)
            w, h = b[2] - b[0], b[3] - b[1]
            c = _rgb(fill)
            if "Z" in d and c and _lum(c) > 0.55:
                panels.append(b)
            elif "Z" in d and c and _lum(c) < 0.45 and w < 20 and h < 20:
                heads.append(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
            elif "Z" not in d and fill == "none" and stroke and not el.get("stroke-dasharray"):
                if sum(math.dist(p, q) for p, q in zip(pts, pts[1:])) >= 14:
                    col = _rgb(stroke)
                    lines.append((pts, None if max(col) < 0.05 else "#%02X%02X%02X" % tuple(round(255 * v) for v in col)))
            elif "Z" not in d and c and _lum(c) < 0.45 and stroke in (None, "none") and min(w, h) <= 6 and max(w, h) >= 15:
                mid = [(b[0], (b[1] + b[3]) / 2), (b[2], (b[1] + b[3]) / 2)] if w > h else \
                      [((b[0] + b[2]) / 2, b[1]), ((b[0] + b[2]) / 2, b[3])]
                lines.append((mid, None))

    def near(p):
        return min((math.dist(p, q) for q in heads), default=99)

    beads = []
    for pts, colour in lines:
        a, z = pts[0], pts[-1]
        if min(near(a), near(z)) > 9:
            continue                          # a rule or an underline, not a flow
        if near(a) < 9 and near(z) < 9:       # double-headed: left to right
            pts = pts if z[0] >= a[0] else pts[::-1]
        elif near(a) < near(z):
            pts = pts[::-1]
        samples = [(p[0] + (q[0] - p[0]) * i / 8, p[1] + (q[1] - p[1]) * i / 8) for p, q in zip(pts, pts[1:]) for i in range(8)]
        bare = sum(any(_inside((x, y, x, y), b) for b in panels) for x, y in samples) < len(samples) / 2
        beads.append(("M" + " L".join("%.2f %.2f" % p for p in pts), colour or FLOW, bare))
    if not beads:
        raise RuntimeError("no connectors found in " + stem)

    def bead_svg(dark):
        out = []
        for d, colour, bare in beads:
            c = _hex_lift(colour) if dark and bare else colour
            out.append('<path class="halo" stroke="%s" d="%s"/><path class="bead" stroke="%s" d="%s"/>' % (c, d, c, d))
        return "".join(out)

    moving = []
    for members, classes, delay in parts:
        moving.append('<g class="mv story %s" style="animation-delay:%.2fs">%s</g>'
                      % (classes, delay, "".join(ET.tostring(t, encoding="unicode") for t in members)))
        for t in members:
            root.remove(t)
    live_body = "".join(moving)
    by_id = {el.get("id"): el for el in defs.iter() if el.get("id")}
    need, todo = set(), set(re.findall(r'(?:url\(#|href="#)([^)"]+)', live_body))
    while todo:
        i = todo.pop()
        if i in need or i not in by_id:
            continue
        need.add(i)
        todo |= set(re.findall(r'(?:url\(#|href="#)([^)"]+)', ET.tostring(by_id[i], encoding="unicode")))
    live_defs = "".join(ET.tostring(by_id[i], encoding="unicode") for i in sorted(need))

    def layer(dark):
        return ('<svg xmlns="%s" xmlns:xlink="%s" width="%s" height="%s" viewBox="%s"><style>%s</style>'
                '<defs>%s</defs>%s<g class="beads">%s</g></svg>'
                % (SVG_NS, XLINK_NS, root.get("width"), root.get("height"), root.get("viewBox"),
                   DATA_CSS.strip(), live_defs, live_body, bead_svg(dark)))
    return ET.tostring(root, encoding="unicode"), layer(False), layer(True), len(beads), len(parts)


def data_figures():
    for name, stem in DATA_FIGURES:
        pdf = os.path.join(ROOT, "new figures", name)
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "fig.svg")
            subprocess.run(["pdftocairo", "-svg", pdf, raw], check=True)
            with open(raw, encoding="utf-8") as f:
                svg = f.read()
        svg, kept, merged = tidy(svg, DATA_FIGURE_PX)
        svg = trim(drop_background(opaque(svg), required=False), pdf)
        base, live, live_dark, nbeads, nparts = live_data(svg, stem)
        base = prune(base)
        out = os.path.join(ROOT, "static", "figures", stem + ".svg")
        out_base, out_live = out[:-4] + "-base.svg", out[:-4] + "-live.svg"
        for path, text in ((out, svg), (dark_path(out), darken(svg)), (out_base, base),
                           (dark_path(out_base), darken(base)), (out_live, live),
                           (dark_path(out_live), live_dark)):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        print("%s -> %s (%d images, %.0f KB); living layer: %d parts, %d connectors (%.0f KB)"
              % (name, os.path.relpath(out, ROOT), kept, os.path.getsize(out) / 1024,
                 nparts, nbeads, os.path.getsize(out_live) / 1024))


# ------------------------------------------------------ the teaser, living
# The teaser tells its story as a build that plays once, then rests on the
# finished figure: A rises in and the arrow draws itself to A'; A' follows,
# its three edits drop in above it as the legend lists them; B rises, the
# toggles switch, one off and one on, and the second arrow draws; the six chosen subsets arrive one
# by one, each with its chips; last, the full transfer, ringed for a moment.
# Then beads run along both arrows, as on the other figures. Every part ends
# exactly as drawn, so the finished build is the still figure. The layer
# opened as ...svg#done shows that finished figure at once (:target), which
# the page uses to swap the light layer for the full one without a rerun.
TEASER_CSS = """
.b{transform-box:fill-box;transform-origin:50% 50%;animation-fill-mode:both;animation-iteration-count:1}
.rise{animation-name:rise;animation-duration:.8s;animation-timing-function:cubic-bezier(.16,1,.3,1);transform-origin:50% 100%}
@keyframes rise{from{opacity:0;transform:translateY(12px) scale(.96)}to{opacity:1;transform:none}}
.drop{animation-name:drop;animation-duration:.55s;animation-timing-function:cubic-bezier(.34,1.56,.64,1)}
@keyframes drop{from{opacity:0;transform:translateY(-8px) scale(.85)}to{opacity:1;transform:none}}
.slide{animation-name:slide;animation-duration:.7s;animation-timing-function:cubic-bezier(.16,1,.3,1)}
@keyframes slide{from{opacity:0;transform:translateX(16px)}to{opacity:1;transform:none}}
.draw{stroke-dasharray:1 1;animation-name:draw;animation-timing-function:cubic-bezier(.65,0,.35,1)}
@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
.head{animation-name:head;animation-duration:.35s;animation-timing-function:ease-out}
@keyframes head{from{opacity:0;transform:scale(.4)}to{opacity:1;transform:none}}
.tg .knob{transform-box:fill-box;animation:.55s cubic-bezier(.34,1.56,.64,1) both}
.tg.off .knob{animation-name:knob-off}
.tg.on .knob{animation-name:knob-on}
@keyframes knob-off{from{transform:translateX(TRAVELpx)}}
@keyframes knob-on{from{transform:translateX(-TRAVELpx)}}
.tg .track{animation:track .55s ease both}
@keyframes track{from{fill:rgb(58%, 64%, 72%)}}
.ring{fill:none;stroke-width:3;opacity:0;animation-name:ring;animation-duration:1.9s;animation-timing-function:ease-out}
@keyframes ring{0%{opacity:0;transform:scale(.97)}30%{opacity:1}100%{opacity:0;transform:scale(1.035)}}
.beads{opacity:0;animation:show .8s ease both}
@keyframes show{to{opacity:1}}
.beads path{fill:none;stroke-linecap:round;stroke-dasharray:.01 22;animation:march 2.4s linear infinite}
.beads .halo{stroke-width:8;opacity:.22}
.beads .bead{stroke-width:3.4}
@keyframes march{to{stroke-dashoffset:-22.01}}
#done:target .b,#done:target .b *{animation:none!important}
#done:target .beads{animation:none;opacity:1}
@media (prefers-reduced-motion:reduce){.b,.b *{animation:none!important}.beads{display:none}}
"""
GREY = (0.70, 0.70, 0.70)                # the teaser's arrows


def _curve(el, steps=16):
    """Points along a path of M / L / C segments, in figure space."""
    toks = re.findall(r"[MLCZ]|-?\d+(?:\.\d+)?", el.get("d"))
    pts, cur, cmd, i = [], None, None, 0
    while i < len(toks):
        if toks[i] in "MLCZ":
            cmd, i = toks[i], i + 1
            continue
        if cmd in ("M", "L"):
            cur = (float(toks[i]), float(toks[i + 1]))
            pts.append(cur)
            i += 2
        elif cmd == "C":
            (x1, y1), (x2, y2), (x, y) = (
                (float(toks[i + k]), float(toks[i + k + 1])) for k in (0, 2, 4))
            for k in range(1, steps + 1):
                t = k / steps
                a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                pts.append((a * cur[0] + b * x1 + c * x2 + d * x,
                            a * cur[1] + b * y1 + c * y2 + d * y))
            cur = (x, y)
            i += 6
        else:
            i += 1
    return _apply(_matrix(el), pts)


def live_teaser(svg):
    """Split the teaser into its still base and its living layer (light and
    dark). The parts are found by shape and place, and checked by count."""
    root = ET.fromstring(svg.encode("utf-8"))
    defs = root.find("{%s}defs" % SVG_NS)
    body = [c for c in root if c is not defs]
    sizes = _sizes(defs)
    ext = {id(t): _extent(t, sizes) for t in body}
    order = {id(t): k for k, t in enumerate(body)}
    used = set()

    def unit(anchor, pad=2):
        """anchor and whatever lies wholly on it (a chip's icon and label)"""
        b = ext[id(anchor)]
        b = (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)
        members = [t for t in body if id(t) not in used and ext[id(t)]
                   and (t is anchor or _inside(ext[id(t)], b))]
        used.update(id(t) for t in members)
        return members

    def single(top):
        lv = _leaves(top)
        return lv[0] if len(lv) == 1 else None

    def closed(top):
        el = single(top)
        return el is not None and el.tag.endswith("path") and "Z" in el.get("d") and el.get("fill") not in (None, "none")

    def picture(top):
        el = single(top)
        return el is not None and el.tag.endswith("use") and (el.get(HREF) or "")[1:] in sizes

    def grey(top, filled):
        el = single(top)
        if el is None or not el.tag.endswith("path") or el.get("stroke-dasharray"):
            return False
        c = _rgb(el.get("stroke"))
        return c is not None and max(abs(v - g) for v, g in zip(c, GREY)) < 0.02 and (el.get("fill") != "none") == filled

    def wh(b):
        return b[2] - b[0], b[3] - b[1]

    def where(test):
        return [t for t in body if ext[id(t)] and test(t, ext[id(t)])]

    def x0(t):
        return ext[id(t)][0]

    pics = where(lambda t, b: picture(t))
    big = [t for t in pics if wh(ext[id(t)])[0] > 150 and 0.7 < wh(ext[id(t)])[0] / wh(ext[id(t)])[1] < 1]
    small = [t for t in pics if 85 < wh(ext[id(t)])[0] < 110 and 0.7 < wh(ext[id(t)])[0] / wh(ext[id(t)])[1] < 1]
    def filled(t, rgb):
        c = _rgb(single(t).get("fill")) if closed(t) else None
        return c is not None and max(abs(v - w) for v, w in zip(c, rgb)) < 0.02
    toggles = []                                   # (track, knob, "off" | "on")
    for rgb, state in (((0.863, 0.149, 0.149), "off"), ((0.086, 0.639, 0.290), "on")):
        for tr in where(lambda t, b: filled(t, rgb) and 1.5 < wh(b)[0] / wh(b)[1] < 2.5):
            tb = ext[id(tr)]
            kn = where(lambda t, b: filled(t, (1.0, 1.0, 1.0)) and _inside(b, tb))
            if len(kn) == 1:
                toggles.append((tr, kn[0], state))
    top_half = lambda t: ext[id(t)][1] < 250
    a = [t for t in big if top_half(t) and x0(t) < 300]
    ap = [t for t in big if top_half(t) and 300 < x0(t) < 700]
    b_ = [t for t in big if not top_half(t) and x0(t) < 300]
    final = [t for t in big if not top_half(t) and x0(t) > 700]
    small.sort(key=lambda t: (round(ext[id(t)][1] / 50), x0(t)))          # rows, then left to right
    chip = lambda t, b, w0, w1, h0, h1: closed(t) and w0 < wh(b)[0] < w1 and h0 < wh(b)[1] < h1
    ap_chips = sorted(where(lambda t, b: chip(t, b, 40, 47, 19, 24) and b[3] < 30), key=x0)
    final_chips = sorted(where(lambda t, b: chip(t, b, 50, 60, 34, 42)), key=x0)
    legend = sorted(where(lambda t, b: chip(t, b, 150, 170, 19, 24) and b[0] > 700
                          and _rgb(single(t).get("fill")) != (1.0, 1.0, 1.0)), key=lambda t: ext[id(t)][1])
    arrows = sorted(where(lambda t, b: grey(t, False) and "Z" not in single(t).get("d")), key=lambda t: ext[id(t)][1])
    heads = sorted(where(lambda t, b: (grey(t, True) or grey(t, False)) and "Z" in single(t).get("d")
                         and max(wh(b)) < 25), key=lambda t: ext[id(t)][1])
    glyphs = lambda t: all(l.tag.endswith("use") and (l.get(HREF) or "").startswith("#glyph") for l in _leaves(t))
    bb = ext[id(b_[0])] if b_ else (0, 0, 0, 0)
    label = where(lambda t, b: glyphs(t) and bb[2] < b[0] and b[2] < min(map(x0, small), default=0)
                  and bb[1] < b[1] < bb[3])            # "SIA", between B and the subsets
    subset_chips = []
    for p in small:
        pb = ext[id(p)]
        subset_chips.append(sorted(where(lambda t, b: chip(t, b, 30, 46, 19, 24) and pb[1] - 12 < b[3] <= pb[1] + 1
                                         and pb[0] - 12 < (b[0] + b[2]) / 2 < pb[2] + 12), key=x0))
    found = (len(a), len(ap), len(b_), len(final), len(small), len(toggles), len(label), len(ap_chips),
             len(final_chips), len(legend), len(arrows), len(heads), [len(c) for c in subset_chips])
    if found != (1, 1, 1, 1, 6, 2, 1, 3, 3, 3, 2, 2, [3] * 6):
        raise RuntimeError("teaser parts not as expected: %r" % (found,))

    parts = []                          # (members, classes, delay, extra style, on the bare page, inner)
    def add(anchor, classes, at, extra="", bare=False):
        parts.append((unit(anchor), classes, at, extra, bare, None))
    # the demonstration: A, the arrow drawing itself, A' and its three edits
    add(a[0], "rise", 0.15)
    add(arrows[0], "draw", 0.55, ";animation-duration:.9s")
    add(heads[0], "head", 1.35)
    add(ap[0], "rise", 1.25)
    for k in range(3):
        add(ap_chips[k], "drop", 1.8 + 0.2 * k)
        add(legend[k], "slide", 1.85 + 0.2 * k)
    # the query, the switch and the second arrow
    add(b_[0], "rise", 2.7)
    add(label[0], "rise", 2.95, bare=True)
    # the toggles rise together, then each knob slides to its side
    tg_at, inner, members = 3.05, [], []
    for k, (tr, kn, state) in enumerate(toggles):
        used.update((id(tr), id(kn)))
        members += [tr, kn]
        delay = ' style="animation-delay:%.2fs"' % (tg_at + 0.35 + 0.15 * k)
        inner.append('<g class="tg %s"><g class="track"%s>%s</g><g class="knob"%s>%s</g></g>'
                     % (state, delay, ET.tostring(tr, encoding="unicode"), delay, ET.tostring(kn, encoding="unicode")))
    parts.append((members, "rise", tg_at, "", True, "".join(inner)))
    tb, kb = ext[id(toggles[0][0])], ext[id(toggles[0][1])]
    travel = (tb[2] - tb[0]) - (kb[2] - kb[0]) - 2 * (kb[0] - tb[0])
    add(arrows[1], "draw", 3.25, ";animation-duration:.7s")
    add(heads[1], "head", 3.9)
    # the six chosen subsets, one by one, each photo then its chips
    for k, p in enumerate(small):
        at = 3.9 + 0.24 * k
        add(p, "rise", at)
        for j, c in enumerate(subset_chips[k]):
            add(c, "drop", at + 0.14 + 0.07 * j)
    # the full transfer
    for k in range(3):
        add(final_chips[k], "drop", 5.55 + 0.12 * k)
    add(final[0], "rise", 5.8)
    ring_box = ext[id(final[0])]
    beads_at = 6.6

    # arrows draw by their own length (pathLength 1); the beads ride them
    for t in arrows:
        single(t).set("pathLength", "1")
    tracks = ["M" + " L".join("%.2f %.2f" % p for p in _curve(single(t))) for t in arrows]

    parts.sort(key=lambda prt: min(order[id(t)] for t in prt[0]))      # keep the drawing order
    moving = []
    for members, classes, at, extra, bare, inner in parts:
        moving.append(('<g class="b %s" style="animation-delay:%.2fs%s">%s</g>'
                       % (classes, at, extra, inner or "".join(ET.tostring(t, encoding="unicode") for t in members)), bare))
        for t in members:
            root.remove(t)
    live_body = "".join(xml for xml, _ in moving)
    by_id = {el.get("id"): el for el in defs.iter() if el.get("id")}
    need, todo = set(), set(re.findall(r'(?:url\(#|href="#)([^)"]+)', live_body))
    while todo:
        i = todo.pop()
        if i in need or i not in by_id:
            continue
        need.add(i)
        todo |= set(re.findall(r'(?:url\(#|href="#)([^)"]+)', ET.tostring(by_id[i], encoding="unicode")))
    live_defs = "".join(ET.tostring(by_id[i], encoding="unicode") for i in sorted(need))

    def layer(dark):
        bead = _hex_lift(FLOW) if dark else FLOW
        x0_, y0_, x1_, y1_ = ring_box
        ring = ('<rect class="b ring" style="animation-delay:%.2fs" x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="6" stroke="%s"/>'
                % (6.2, x0_ - 4, y0_ - 4, x1_ - x0_ + 8, y1_ - y0_ + 8, ACCENT_DARK if dark else ACCENT))
        beads = "".join('<path class="halo" stroke="%s" d="%s"/><path class="bead" stroke="%s" d="%s"/>'
                        % (bead, d, bead, d) for d in tracks)
        return ('<svg xmlns="%s" xmlns:xlink="%s" width="%s" height="%s" viewBox="%s"><style>%s</style>'
                '<defs>%s</defs><g id="done">%s%s<g class="beads" style="animation-delay:%.2fs">%s</g></g></svg>'
                % (SVG_NS, XLINK_NS, root.get("width"), root.get("height"), root.get("viewBox"),
                   TEASER_CSS.strip().replace("TRAVEL", "%.2f" % travel), live_defs,
                   # ink on the bare page is drawn light in the dark theme, as darken does
                   "".join(_lift(xml) if dark and bare else xml for xml, bare in moving),
                   ring, beads_at, beads))
    return ET.tostring(root, encoding="unicode"), layer(False), layer(True), len(parts)


def drop_faint(svg, below=0.05):
    """Drop the outlines draw.io's math labels stroke at 2-4 % opacity over
    their own filled letters: invisible, and ~90 KB of the teaser."""
    return re.sub(r'<path\b(?=[^>]*\bfill="none")(?=[^>]*\bstroke-opacity="0\.0\d*")[^>]*/>\n?',
                  lambda m: m.group(0) if float(re.search(r'stroke-opacity="([^"]+)"', m.group(0)).group(1)) >= below else "",
                  svg)


def share_shapes(svg, tol=0.02):
    """Draw each shape that recurs (the chips' math letters, ~120 of them)
    once in defs and place its copies with <use>. Copies match to within tol
    of the shape's own units (the source rounds every coordinate), so the
    result is the same drawing to well under a pixel at any zoom."""
    root = ET.fromstring(svg.encode("utf-8"))
    defs = root.find("{%s}defs" % SVG_NS)
    parent = {c: p for p in root.iter() for c in p}
    shapes = {}                      # (commands, style) -> [(rel points, [(el, parent, x0, y0)])]
    for el in list(root.iter("{%s}path" % SVG_NS)):
        if el.get("id") or el.get("pathLength") or el.get("class") or el.get("stroke-dasharray"):
            continue
        anc = parent.get(el)
        if anc is not None and (anc.tag.endswith("clipPath") or anc.tag.endswith("mask")):
            continue
        while anc is not None and anc is not defs:
            anc = parent.get(anc)
        if anc is defs:
            continue
        toks = re.findall(r"[MLCZ]|-?\d+(?:\.\d+)?", el.get("d"))
        if not toks or toks[0] != "M" or len("".join(t for t in toks if t in "MLCZ")) + sum(1 for t in toks if t not in "MLCZ") != len(toks):
            continue
        nums = [float(t) for t in toks if t not in "MLCZ"]
        if len(nums) < 16:
            continue                                   # not worth sharing
        if len(nums) != 2 * sum({"M": 1, "L": 1, "C": 3, "Z": 0}[t] for t in toks if t in "MLCZ"):
            continue                                   # a command repeated implicitly: leave it
        x0, y0 = nums[0], nums[1]
        rel = [v - (x0 if k % 2 == 0 else y0) for k, v in enumerate(nums)]
        key = ("".join(t for t in toks if t in "MLCZ"), tuple(sorted((k, v) for k, v in el.attrib.items() if k not in ("d", "transform"))))
        group = shapes.setdefault(key, [])
        for ref, uses in group:
            if max(abs(a - b) for a, b in zip(ref, rel)) <= tol:
                uses.append((el, parent[el], x0, y0))
                break
        else:
            group.append((rel, [(el, parent[el], x0, y0)]))
    n = k = 0
    for (cmds, style), group in shapes.items():
        for rel, uses in group:
            if len(uses) < 2:
                continue
            n += 1
            sid = "sh%d" % n
            it = iter(rel)
            d, pairs = [], list(zip(it, it))
            i = 0
            for c in cmds:
                take = {"M": 1, "L": 1, "C": 3, "Z": 0}[c]
                d.append(c + "".join(" %.2f %.2f" % pairs[i + j] for j in range(take)))
                i += take
            ET.SubElement(defs, "{%s}path" % SVG_NS, dict(style, id=sid, d=" ".join(d)))
            for el, p, x0, y0 in uses:
                u = ET.Element("{%s}use" % SVG_NS, {HREF: "#" + sid, "x": "%.2f" % x0, "y": "%.2f" % y0})
                if el.get("transform"):
                    u.set("transform", el.get("transform"))     # x, y apply inside it, as the path's own did
                i = list(p).index(el)
                p.remove(el)
                p.insert(i, u)
                k += 1
    return ET.tostring(root, encoding="unicode"), n, k


def social_card(pdf, out, width=TEASER_CARD_PX):
    """The teaser as a JPEG for link previews (og:image), on white."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-png", "-scale-to-x", str(width), "-scale-to-y", "-1",
                        "-singlefile", pdf, os.path.join(tmp, "card")], check=True)
        im = Image.open(os.path.join(tmp, "card.png")).convert("RGB")
    a = np.asarray(im.convert("L"))
    rows, cols = np.where((a < 246).any(axis=1))[0], np.where((a < 246).any(axis=0))[0]
    im = im.crop((max(cols.min() - 12, 0), max(rows.min() - 12, 0),
                  min(cols.max() + 13, im.width), min(rows.max() + 13, im.height)))
    im.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return im.size


def teaser():
    """teaser.svg (+ -dark), the still figure; teaser-base.svg, its parts that
    never move; teaser-live.svg, the build; teaser-live-lite.svg, the same
    build with small, rougher photos, which a slow connection plays first;
    and teaser.jpg for link previews."""
    out = os.path.join(ROOT, "static", "figures", "teaser.svg")
    out_base, out_live = out[:-4] + "-base.svg", out[:-4] + "-live.svg"
    out_lite = out[:-4] + "-live-lite.svg"
    with tempfile.TemporaryDirectory() as tmp:
        pdf, raw = os.path.join(tmp, "fig.pdf"), os.path.join(tmp, "fig.svg")
        export_pdf(TEASER_SRC, pdf)
        subprocess.run(["pdftocairo", "-svg", pdf, raw], check=True)
        with open(raw, encoding="utf-8") as f:
            raw = f.read()

        def prepare(across, quality):
            svg, kept, merged = tidy(raw, across, quality)
            return trim(drop_background(opaque(drop_faint(svg)), required=False), pdf), kept, merged
        svg, kept, merged = prepare(TEASER_PX, 82)
        lite_svg = prepare(*TEASER_LITE)[0]
        card = social_card(pdf, os.path.join(ROOT, "static", "figures", "teaser.jpg"))
    base, live, live_dark, nparts = live_teaser(svg)
    _, lite, lite_dark, _ = live_teaser(lite_svg)
    base = prune(base)
    for path, text in ((out, svg), (dark_path(out), darken(svg)), (out_base, base),
                       (dark_path(out_base), darken(base)), (out_live, live), (dark_path(out_live), live_dark),
                       (out_lite, lite), (dark_path(out_lite), lite_dark)):
        with open(path, "w", encoding="utf-8") as f:
            f.write(share_shapes(text)[0])
    print("Teaser.drawio -> %s (%d images, %d duplicates merged, %.0f KB); living layer: %d parts "
          "(%.0f KB; light copy %.0f KB) over a %.0f KB base; teaser.jpg %dx%d"
          % (os.path.relpath(out, ROOT), kept, merged, os.path.getsize(out) / 1024, nparts,
             os.path.getsize(out_live) / 1024, os.path.getsize(out_lite) / 1024,
             os.path.getsize(out_base) / 1024, card[0], card[1]))


def main():
    if sys.argv[1:] == ["data"]:
        return data_figures()
    if sys.argv[1:] == ["teaser"]:
        return teaser()
    with tempfile.TemporaryDirectory() as tmp:
        drawio, pdf, raw = (os.path.join(tmp, n) for n in ("fig.drawio", "fig.pdf", "fig.svg"))
        n = crop_page(SRC, drawio)
        export_pdf(drawio, pdf)
        subprocess.run(["pdftocairo", "-svg", pdf, raw], check=True)
        with open(raw, encoding="utf-8") as f:
            svg = f.read()
    svg, kept, merged = tidy(svg)
    svg = drop_background(svg)
    base, live, dark_live, nbeads, parts = split_live(svg)
    base = prune(base)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for path, text in ((OUT, svg), (dark_path(OUT), darken(svg)), (OUT_BASE, base),
                       (dark_path(OUT_BASE), darken(base)), (OUT_LIVE, live),
                       (dark_path(OUT_LIVE), dark_live)):
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print("%d cells -> %s (%d images, %d duplicates merged, %.0f KB)"
          % (n, os.path.relpath(OUT, ROOT), kept, merged, os.path.getsize(OUT) / 1024))
    print("living layer: %s, %d connectors -> %s (%.0f KB) over %s"
          % (", ".join("%d %s" % (v, k) for k, v in sorted(parts.items())), nbeads,
             os.path.relpath(OUT_LIVE, ROOT), os.path.getsize(OUT_LIVE) / 1024,
             os.path.relpath(OUT_BASE, ROOT)))
    data_figures()
    teaser()


if __name__ == "__main__":
    main()
