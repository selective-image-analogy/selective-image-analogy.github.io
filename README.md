# SIA: Selective Image Analogy — project page

Project page for **SIA: Selective Image Analogy**, SIGGRAPH Asia 2026.

**Live site:** <https://selective-image-analogy.github.io/>

Amir Alimohammadi\*, Kian Izadpanah\*, Bardiya Kariminia, Yiorgos Chrysanthou,
Ali Mahdavi-Amiri — *\*equal contribution*

---

## Layout

```
index.html                  the whole page
static/
  css/style.css             all styles (light + dark, token-driven)
  js/data.js                GENERATED — sample/example metadata and image paths
  js/app.js                 switchboard, examples player, lightbox, theme, nav
  figures/                  GENERATED — the teaser, pipeline and training-data
                            figures as SVG (teaser*, architecture*,
                            data-generation*, data-format*); teaser.jpg, the
                            link-preview image; and wall*.webp, the masthead's
                            result wall (full and light copies)
  images/                   GENERATED — every result crop, as webp
  pdfs/SIA_paper.pdf        GENERATED — web-sized copy of the paper
  favicon.svg               the tab icon: the SIA wordmark from the teaser; the
                            PNGs beside it (32, 96, apple-touch 180) are renders of it
new figures/                SOURCE — the authors' renders, figure PDFs and the
                            teaser's and pipeline figure's draw.io files
tools/                      the four build scripts
```

Everything under `static/images`, `static/figures`, `static/pdfs` and
`static/js/data.js` is generated. Edit the sources, then re-run the scripts.

## Rebuilding the assets

Requires Python with `Pillow` and `numpy`, plus `pdftoppm` (poppler or MiKTeX)
and Ghostscript for the two PDF steps.

```bash
python tools/build_images.py                  # results  -> static/images + static/js/data.js
python tools/build_arch.py                    # the vector figures -> static/figures/*.svg
python tools/build_arch.py data               #   (or only the two training-data figures)
python tools/build_arch.py teaser             #   (or only the teaser)
python tools/build_wall.py                    # results  -> static/figures/wall*.webp
python tools/build_paper.py ../SIA_finalized2.pdf   # 70 MB paper -> 1.6 MB web copy
```

`build_arch.py` builds the pipeline figure from `new figures/Architecture.drawio`
(a copy of the authors' `main_fig.drawio`). It keeps the cells inside
`FIG_RECT` (that page also holds scratch drawings), exports them to PDF with
**draw.io desktop**, converts that with `pdftocairo -svg` so the labels become
outlines, and re-encodes the embedded photos as WebP at the size the page can
show them (~560 KB in all). It needs draw.io desktop (set `DRAWIO` if it is not
on `PATH`) and the figure's fonts installed: Comic Sans MS, Architects
Daughter, Open Sans, Arial and Times New Roman. draw.io substitutes missing
fonts silently, so check the labels after a rebuild. Being vector, the figure
stays sharp when the page enlarges a part of it.

The figure has **no background**: the build removes draw.io's white page, so the
panels sit straight on the site. Each still figure also gets a `-dark.svg` twin
for the dark theme, in which the black lines and labels that lie on the bare
page (the Concat column, its "+", the connectors into and out of the
transformer) are drawn light and a little thicker; inside the pastel panels
they stay black. The living layer has a dark twin too, whose beads run light
where a connector crosses the bare page.
`app.js` picks the file for the current theme and swaps it when the theme
changes. *Enlarge* opens these living figures (pipeline and training data)
as the page shows them: the same base and moving layers, in the current
theme, on the page's surface (`#lbStack` in the lightbox).

It also writes the figure's **living version** as two layers that the page
stacks: `architecture-base.svg` (the figure minus the parts that move) and
`architecture-live.svg` (~105 KB, ~30 KB sent gzipped: just those parts, animated by CSS inside it).
The fat arrows nudge along their direction in a slow left-to-right wave, the
AnaLoRA/ExLoRA flames flicker, the CSV panel plays a 7 s story (Qwen-VL turns,
the six prompts go out one by one, the text encoder pulses, the samples gather
into their two means, which swell, and the difference-of-means arrow redraws),
small beads run slowly along every
connector (in the LoRA panel in the colour of the tokens each column carries),
and ExLoRA's outline glows. The parts are found by their colours and shapes;
if the figure changes and they no longer match, the build stops and says so.
Under `prefers-reduced-motion` the page shows the still `architecture.svg`
(or its dark twin) instead.

The **teaser** (Fig. 1) is built the same way from `new figures/Teaser.drawio`,
a copy of `figures/teaser_SIA_final_draft1.drawio`, the file behind
`teaser_SIA_V6.pdf` (V6 differs from the V5 raster the page used before only in
the bottom-left: *SIA* above the arrow, with an on/off switch). In the copy, the
authors' on/off switch picture is replaced by two native draw.io toggles in the
site's switch colours (off red `#DC2626`, on green `#16A34A`; cells
`sia-toggle-*` / `sia-knob-*`), so re-copying the authors' file means redoing
that. It gets the same treatment as the other figures (SVG, photos re-encoded,
no background, a dark twin), plus `teaser.jpg` (1570 px) for link previews
(`og:image`). Two passes keep it light: `drop_faint` removes the outlines that
draw.io's math labels stroke at 2–4 % opacity over their own letters (invisible,
~90 KB), and `share_shapes` draws each recurring shape (the chips' *e₁ e₂ e₃*,
~60 of them) once and places the copies with `<use>`.
Its living layer (`teaser-live.svg`, ~170 KB sent gzipped, mostly the photos) is a
**build** that plays once, ~7 s, over `teaser-base.svg` (~20–27 KB sent: the legend
box, the separator and the keys): *A* rises in and the arrow draws itself to
*A′*; *A′* follows and its three edits drop in above it as the legend lists
them; *B* and *SIA* arrive, the two toggles rise and their knobs slide to off
and on, and the second arrow draws; the six chosen
subsets come in one by one, each with its chips; last, the full transfer,
ringed for a moment. Then beads run along both arrows, as on the other
figures. Every part ends exactly as drawn, so the finished build is the still
figure. The parts are found by shape and place (`live_teaser`), and the build
stops if their counts change.

The layer also comes **light**: `teaser-live-lite.svg` (~80 KB sent) is the
same build with photos at 900 px across and quality 55 (`TEASER_LITE`). Opened
as `…svg#done`, either layer shows the finished figure at once (a `:target`
rule switches the build off).

An SVG in an `<img>` starts its animation when it loads, so `app.js` controls
when the build plays: the page shows the base, fetches the layers (light, then
full) once the page has loaded and the figure is within ~1500 px, and plays a
fresh blob URL of one when a third of the figure is on screen. If the full
layer is already here (or arrives within 300 ms of the light one) it plays;
otherwise the light one plays at once, and when its build has ended and the
full one has arrived, the full one takes over as `#done`: the photos sharpen,
nothing reruns. A soft sheen runs over the figure while the first layer is on
its way. *Replay* (top centre, the figure's one empty spot) plays it again.
After a theme switch the finished figure is shown in the new theme (`#done`,
light first if need be). Under `prefers-reduced-motion`, without script, or if
neither layer loads, the page shows the still `teaser.svg` (or its dark twin).

`build_wall.py` reads the *built* results under `static/images` (and their
subjects from `static/js/data.js`), so run it after `build_images.py`. It
writes two images, keeping results that share a query subject from touching or
crowding the wall, and leading with the objects, animals and scenes: portraits
are capped (14 of the still wall's 45 tiles, 3 per column of the moving one),
while an animal or object may show up to 6 of its distinct results. Results
are spaced by *family*: their query image, or a `FAMILIES` group of queries
that look alike (the silver cars, the dog in a field, the dragons, ...). On the
still wall a family never touches itself, diagonals included. On the moving
wall, neighbouring columns slide past each other and so share no family;
`app.js` gives every column one pace, so columns two apart move in step and a
family recurs there only three or more rows away. After a rebuild, bump the
`?v=` on the wall URLs (`index.html`, `style.css`, `app.js`) so browsers
fetch the new images:

* `wall.webp` (~550 KB, 9 × 5 tiles) — the still wall.
* `wall-motion.webp` (~790 KB, 9 × 8 tiles) — a taller grid whose columns loop
  seamlessly, for the drifting wall: columns slide alternately up and down at
  one pace, and pause while the masthead is scrolled away.
* `wall-lite.webp` (~45 KB, ¼ size) and `wall-motion-lite.webp` (~100 KB,
  ⅓ size) — light copies of the two (`STATIC_LITE`, `MOTION_LITE`), so that a
  weak connection gets a wall, and a moving one, without waiting.

The page loads them in steps. `index.html` paints the light still wall; `app.js`
then fetches the light moving one at high priority and fades into the drift
(on a 1 Mbit/s link, about 7 s in, against never before), and once the page has
loaded it downloads the full-quality moving wall in the background and lays it
over the light one without interrupting the drift. That full download runs only
while the masthead is on screen: if the visitor scrolls on before it has
arrived, it stops so it doesn't slow down what they are looking at, and starts
again when they come back. Under `prefers-reduced-motion` the wall stays still
and the full still wall fades in over the light one; under Data Saver it stays
the light still wall. Append `?wall=move` or `?wall=still` to the URL to force
either for preview, or `?wall=lite` to stay on the light copies (what a slow
connection shows first).

`build_images.py` reads `new figures/`:

* `all_is_correct/<n>/` — one demonstration with **many** rendered subsets. It
  drives the interactive *Results* switchboard. `no_supp.png` is the full
  transfer; `supp_e1_e3.png` means edits 1 and 3 were suppressed. Filenames are
  translated into keep-masks (`"0101"` = keep e2 and e4) and the metadata
  asserts that each mask matches its declared edit list. The tabs, in
  `SAMPLES` order: Dog (4: red T-shirt, sitting, painting style; inputs =
  example x25, results from the scored run's data67; the demo opens on it),
  Sunglasses portrait (6: sunglasses, sad expression, wildflower meadow; the
  older evaluation run's 3edits data13, its inputs from that run's
  `data/3edits/data13`, every result SIA's own output, all seven right),
  Lipstick portrait (7: open the eyes, purple lipstick; the scored run's 2edits
  data15, its inputs from the older evaluation run's `data/2edits/data15`, all
  three results SIA's own and right), Dragon (2), Studio portrait (3) and
  Alley portrait (1). `all_is_correct/5` (a pug: jumping, colored pencil) is kept
  but not shown: its "pencil only" was never rendered cleanly (the scored run's
  makes the pug jump).
  Each has a `start`, the switches' position when its tab opens: every edit on,
  except Studio portrait (no full transfer was rendered, so smile and mountains
  on, earrings off) and Alley portrait (style off, to open on a selective
  result). The build asserts that each start was rendered. A combination with
  no render (Studio portrait's full transfer) can still be switched to: the
  result then shows the closest rendered combination, with a note under the
  switches saying which edit differs. Every
  image has a light copy under `lite/` (⅓ size, ~3 KB), which its frame shows
  until the full one has downloaded and faded in. The page fetches the
  light copies first (A, A′, B and the result, then every other combination on
  the open tab and what each other tab opens on, ~70 KB), and each full image
  only once its light copy is in; the open tab's other combinations follow in
  full once A, A′ and B have arrived (none under Data Saver), and stop if the
  visitor changes tab.
  A result enlarged before it has arrived opens as its light copy and sharpens.
* `some_is_correct/<n>/` (1–82) — one demonstration with a **single** rendered
  subset each. `EXAMPLE_ORDER` lists the ones shown in the *Examples*
  section, in the order they play (mostly objects and animals, never two
  portraits in a row). `HELD_BACK` keeps 28 portraits out so people don't dominate
  the page, and `REJECTED` lists results that fail (a dropped edit shows up
  anyway, or the kept one barely shows) or keep every edit, with the reason
  for each. Sources and metadata stay for all of them. Every example must be
  in exactly one of the three, and the build asserts it. x67–x75 come from the
  older evaluation run (`KianIzadpanah/SIA_Evaluation_Data_Results`) and
  x76–x82 are further subsets of the x59 and x25 pairs from the scored run
  (`KianIzadpanah/SIA_Rebuttal_Baselines`). The result file is usually
  `supp_*.png`; `no_supp.png` (a full transfer) and hand-named renders such as
  `SIA.png` are also accepted, and the build asserts the filename agrees with
  the kept/suppressed flags in the metadata.

Any frame taller than 512 px carries a rendered caption strip underneath the
result image, so the script crops every frame back to its top 512 rows. Edit
labels, titles, subject classes and edit types live in the `SAMPLES` /
`EXAMPLES` tables at the top of `build_images.py` — that is the one place to
change wording or add a new sample. `data.js` carries them as `SIA_SAMPLES`
(switchboard) and `SIA_EXAMPLES` (the Examples section).

The **Examples** section plays one example at a time: *A → A′*, a *B / B′*
compare slider, every demonstrated edit under *A → A′*, and the same edits
under *B → B′* marked carried over (green ✓) or left out (red ✕). Each one
opens on *B*, the slider sweeps across to reveal *B′*, holds, then cross-fades
to the next, about 3 s each; a thin line under it fills while it waits (timings are `WAIT`,
`SWEEP` and `HOLD` in the `explorer` block of `app.js`). Every example also has
a `lite/` folder: its four images at ⅓ size (~3 KB each, from `lite()` in
`build_images.py`). Each frame carries the light copy as its background, so on
a slow connection the example appears at once in low quality and every image
fades in sharp as it arrives. The player fetches the next example (light, then
full) and the previous one (light) ahead of time, after the page has loaded,
and stops unfinished downloads for examples the visitor has moved past. It plays only while
the section is on screen, pauses under the mouse, stops when the visitor drags
the slider, and waits for the play button under `prefers-reduced-motion`.
Under it, one toolbar: play/pause, a rail of small previews (`thumb.webp`)
about seven wide that keeps the current example in the middle and can be
clicked, swiped or scrolled, and *Surprise me*. Prev / next and the arrow
keys move by hand too. Hovering over the example or the rail pauses it. The page shows no
example counts and no edit categories; the `type` and `subject` fields in
`EXAMPLES` are kept as metadata only.

The **Method** section has five parts:

* **The pipeline figure, part by part** (`#tour`). The paper's Fig. 2 with
  seven steps (overview, then inputs, prompt, transformer, AnaLoRA + ExLoRA,
  CSV, output); each step dims all but its region and shows a caption.
  A region is `data-r="x0 y0 x1 y1"` on its step button, in percent of the
  figure, measured from `architectureV2.pdf`'s own geometry (text, image and
  panel boxes; the draw.io export has the same bounds). If the figure's layout
  changes, re-measure them. The regions are clickable on the figure too, and
  with a mouse, hovering one enlarges that part (up to 1.8×, kept inside the
  figure) until the pointer leaves it; clicking the enlarged part selects its
  step. On a touch screen, where the figure is too small to read part by part,
  a step zooms into its part instead: the stage takes the part's shape and the
  figure is scaled to fill its width (2.2–4.5×, `.lens`), and tapping the part
  again zooms back out.
* **Under the hood** (`#hood`). The dragon sample (`s2`) with its three
  edits as switches. Switching one off marks its prompt tokens 1 in the mask,
  forks those tokens through the ExLoRA hourglass (a soft low-rank glyph) in the attention-layer diagram
  (drawn after SliderEdit's selective-token figure: every column goes through
  *W* + AnaLoRA, and only a dropped edit's column adds ExLoRA's output back), and
  shows SIA's real result for that subset. On a narrow screen the diagram's
  five columns sit in two rows (three over two) instead of scrolling sideways.
* **How ExLoRA is trained** (`.trainp`). One real training sample from the
  slide deck, `new figures/exlora_training/` (A, A′, B and the target with
  "gold color" masked), built into `static/images/training/`.
* **Concept Suppression Vector** (`#csvp`). Two inline SVG plots: the
  contrastive prompts' clusters and the direction *d* (looping while on
  screen: a copy of each sample runs into its cluster's mean, the means swell
  and get labelled, then *d* draws between them; still under reduced motion),
  then the dropped token,
  the part along *d* that CSV removes, and what is left. A λ slider drives
  the second plot, and it eases from 0 to 1 once when it comes on screen.
* **Training data**: `data-generation` and `data-format`, vector SVGs built by
  `build_arch.py` from `new figures/DataGeneration.pdf` and `DataFormat.pdf`
  (copies of `fig_data_generation.pdf` / `fig_data_format.pdf`, which
  diagrams.net exported from `figures/Stage1-3.drawio` and `phase4.drawio`;
  the draw.io command line does not set their LaTeX labels reliably, so the
  build starts from those exports). Like the pipeline figure they have no
  background and a `-dark.svg` twin: their translucent panels are made solid
  (the colour they show over white), and on the dark page any ink short of
  4.5:1 contrast is lifted toward white just enough. Each `img` carries both
  files (`data-dark`, `data-light`) and the theme switch picks one. They are
  living figures too (`-base` + `-live` layers, as for the pipeline figure;
  `data_parts` in `build_arch.py` finds the moving parts and sets the 8 s
  story). Data generation: beads run along every arrowed connector (dotted
  ones included), Flux-Klein-9B pulses and its result pops, the recipe chips
  e1 to e4 light up in turn with the photo that adds each edit, Qwen-VL turns,
  the check pops and the cross shakes. Data format: the recipe chips pulse in
  turn in the legend and in subject a's row and A′ pops; in R ⊆ ℰ the
  retained chips step up while the suppressed ones fade back; then B′_R and
  B′ pop. Under reduced motion the base `img` switches to its
  `data-still-*` file (the whole still figure) and the layer is hidden. Then
  the stats band.

The slide deck these come from (`SIA_slides_animated.pptx`, slides 16–32)
is not in the repo.

## Design system

The page opens on a full-screen **result wall**: a tilted grid of real SIA
outputs (`static/figures/wall.webp`) under a veil in the page colour that is
densest behind the title. The interactive switchboard follows directly below,
so a visitor sees the work, then uses it, before reading anything.

Everything else is neutral and restrained: a deep slate ground (`#121826`,
deliberately not black), one periwinkle accent (`#8EA8FF`) for interface
furniture — links, focus rings, the result frame, the active nav item — and the
paper's green/red only for retained vs suppressed edits. Each edit is an on/off
switch whose knob position reads without relying on colour. Each switchboard
tab opens at its `start` (see above), and the tabs follow the order of
`SAMPLES` in `tools/build_images.py`.

Dark is the default. Every colour is a token in `:root`, overridden under
`:root[data-theme="light"]` with a white ground, cool slate greys (ink
`#0F172A`) and an indigo-blue accent (`#3B5BDB`); a stored light choice is
applied by a small inline script in `<head>` before first paint. The wall's veil is the
`--veil` / `--veil-a…c` tokens, so the masthead follows the theme too.

**On a phone** (checked at 390 × 844, 390 × 700, 360 × 740 and 607 × 812,
with touch): nothing scrolls the page sideways, and each interactive section
fits on one screen under the bar, so a switch and what it changes are seen
together. Up to 760 px wide: the **demo** shows its tabs as one sliding row,
*A → A′* as thumbnails beside their label, and *B → B′* side by side, as big as
the height left over (`app.js` measures the rest of the demo, tabs to footer,
into `--fixed`, and `--qh` in `style.css` takes the screen's `svh` less that);
its legend and plain how-to give way, warnings show in short, and the counter
reads "3 / 8". An **example** works the same way: thumbnails for *A → A′*, the
compare slider sized from what is left (`--rest`, measured from the card and
its toolbar), the kept and excluded edits as pills, the toolbar on one row
(*Surprise me* as its icon) and the slider's pins just *B* and *B′*. **Under
the hood**, *A* and *A′* shrink to a small pair over *B* and *B′*, so the
switches, the result and the token mask share one screen. The section links in the bar scroll sideways, their ends fade,
and the current section's link is kept in view. Running text is left-aligned
(justified text spaces its words unevenly on a short line). The demo's number-key
badges and keyboard hints are hidden on touch, and its footer wraps. The
example card drops its plain list of edits, since *B → B′* repeats them with
their marks. The results table pins its method column and says it scrolls.
Small controls (the demo's and the figure's arrows, the figure's steps, the
λ slider) grow to touch size. Text meant for a mouse or a finger is in
`.when-hover` / `.when-touch` spans, and `touch` in `app.js` makes the same call.

Type is Inter for headings and text, Source Serif 4 italic only for the
*A*, *A′*, *B*, *B′* notation, and JetBrains Mono for small labels and code.
Surfaces share three radii (8 / 12 / 16 px), a 1 px rule and two soft shadows.

Figures and tables are framed, with the caption *inside* the frame under a
hairline — so caption text is always exactly as wide as the thing it
describes.

## Sizing

Every image block is driven by a custom property in `:root`, shaped as
`clamp(floor, min(Nvh, Mvw), ceiling)`:

* `min(Nvh, Mvw)` takes whichever viewport dimension is scarcer, so a portrait
  tablet and a wide monitor both get a size that fits without a breakpoint.
* the ceiling is the **native pixel height of the source render** (512 px for
  the result crops, 1570 / 1088 for the two figure PDFs) — past it the browser
  is only upscaling.
* `--pair-h` and `--demo-h` are `calc()`ed from `--res-h` / `--wipe-h`, so the
  columns beside them stay level at every screen size.

Widths come from `calc(height * aspect-ratio)` with `max-width` clamping —
never `width: min(100%, ...)`, which is a circular percentage inside an
auto-sized grid track and silently collapses. `--wide` follows the viewport
too (`min(94vw, 1480px)`), so figures keep growing on large displays.

Below 760 px the layout is one column and these are pinned to the column width
instead, since there the column and not the viewport height is the constraint.

## Local preview

```bash
python -m http.server 8000
# open http://127.0.0.1:8000
```

## Deployment

The site is served from the organization repo
[`selective-image-analogy/selective-image-analogy.github.io`](https://github.com/selective-image-analogy/selective-image-analogy.github.io),
which GitHub publishes at the domain root — so the relative `static/...` paths
work unchanged.

`.github/workflows/pages.yml` runs on every push to `main` (and can be run by
hand from the Actions tab). **Settings -> Pages -> Source** is **GitHub
Actions**. The workflow deletes `new figures/` and `tools/` from the artifact
before uploading, so the published site is ~26 MB rather than ~190 MB. Jekyll is
off (`.nojekyll`), so paths starting with `_` and the `static/` tree are served
verbatim.

If Pages is ever re-enabled from a branch instead, it will publish the *whole*
repository, sources included; flipping Source back to GitHub Actions and
re-running the workflow fixes it.

### Remotes

```
site    selective-image-analogy/selective-image-analogy.github.io   <- the live site
origin  KianIzadpanah/selective-image-analogy                       <- the original repo
```

Push to `site` to publish. `origin` still serves an older copy of the page at
`kianizadpanah.github.io/selective-image-analogy`; every canonical/OG URL in
`index.html` points at the new domain, so search engines will settle on it, but
the old page can be turned off in that repo's Pages settings whenever you like.

## Loose ends

1. **BibTeX track.** `index.html` cites the paper as
   `@inproceedings{... booktitle = {SIGGRAPH Asia 2026 Conference Papers} ...}`.
   If it was accepted to the journal (TOG) track instead, switch it to
   `@article` with `journal = {ACM Transactions on Graphics}` plus volume,
   number and DOI.
2. **arXiv and Code buttons** in the masthead are inert `<span class="btn
   pending">` placeholders. Turn each back into an `<a href="...">` once the
   preprint and the repo are public.
3. **The paper PDF** is still at `static/pdfs/SIA_paper.pdf` but nothing links
   to it. Add a button back to the masthead when it should be public.
4. **Studio portrait** reads *combination n / 7* rather than 8 because
   `all_is_correct/3` has no `no_supp.png`. Render it and the build picks it
   up. The pug (`all_is_correct/5`) could come back as a tab once it has a
   clean `supp_e1.png` ("pencil only").
5. **Video.** The *Video* section plays the YouTube method video
   (`HU010YnVEwI`). To swap it, change `data-yt` on the `.yt` element in
   `index.html` to the new ID and update its label; the poster and the
   "Watch on YouTube" link follow the ID. The player loads only
   on click, from `youtube-nocookie.com`. For readers where YouTube is blocked,
   attach a compressed MP4 to a GitHub release and uncomment the download link
   under the player.

## Credit

Layout and typography take their cue from the
[Nerfies](https://nerfies.github.io) and
[HairPort](https://deepmancer.github.io/HairPort/) project pages. Released
under [CC BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/).
