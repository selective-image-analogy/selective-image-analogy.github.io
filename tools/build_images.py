# -*- coding: utf-8 -*-
"""Crop / convert every result image and emit static/js/data.js for the site.

Source of truth is `new figures/`:
  * all_is_correct/<n>  -> the interactive "Results" switchboard (many subsets)
  * exlora_training      -> the ExLoRA training sample in the Method section
  * some_is_correct/<n> -> one subset each: the Examples section
                           (EXAMPLE_ORDER); HELD_BACK and REJECTED ones are
                           skipped

Any frame taller than 512 px carries a rendered caption strip underneath the
result, so it is cropped back to its top 512 rows.
"""
import json
import os
import re
import shutil

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "new figures")
IMG = os.path.join(ROOT, "static", "images")
MAXH = 512
Q = 88


# ---------------------------------------------------------------- helpers
def prep(path):
    """Open, flatten alpha over white, crop anything taller than 512 px."""
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    im = im.convert("RGB")
    if im.height > MAXH:
        im = im.crop((0, 0, im.width, MAXH))
    return im


def save(im, dest, size=None, q=Q):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if size and im.size != size:
        im = im.resize(size, Image.LANCZOS)
    im.save(dest, "WEBP", quality=q, method=6)


def thumb(im, dest, w=180):
    h = round(im.height * w / im.width)
    save(im.resize((w, h), Image.LANCZOS), dest, q=82)


def lite(im, dest, scale=1 / 3, q=50):
    """A light copy (~3 KB) that the demo and the examples player show while
    the full image downloads, so a slow connection never faces an empty
    frame."""
    save(im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS), dest, q=q)


# ---------------------------------------------------------------- metadata
# Switchboard tabs, in display order; the first is shown on load. `start` is
# the switches' position when a tab opens (1 = edit on): every edit on where
# that result was rendered.
SAMPLES = [
    dict(id="s4", src="all_is_correct/4", label="Dog", subject="creatures",
         title="Red shirt, sitting, painted", start="111",
         edits=[("add a red T-shirt", "object"),
                ("sitting pose", "pose"),
                ("add a minimalist painting style", "style")]),
    # older evaluation run, 3edits data13: every combination right by eye; A, A'
    # and B are that run's data/3edits/data13, every result is SIA's own output
    dict(id="s6", src="all_is_correct/6", label="Sunglasses portrait", subject="people",
         title="Sunglasses, a sad face, wildflowers", start="111",
         edits=[("add sunglasses", "object"),
                ("sad expression", "expression"),
                ("add a sunny wildflower meadow background", "background")]),
    # scored run, 2edits data15: all three results right by eye and by the Qwen
    # judge; A, A' and B are the older evaluation run's data/2edits/data15 (same
    # prompt), every result is SIA's own output
    dict(id="s7", src="all_is_correct/7", label="Lipstick portrait", subject="people",
         title="Open eyes and purple lipstick", start="11",
         edits=[("open the eyes", "expression"),
                ("add purple lipstick", "appearance")]),
    dict(id="s2", src="all_is_correct/2", label="Dragon", subject="creatures",
         title="Lava, open wings, gold scales", start="111",
         edits=[("add lava to the ground", "background"),
                ("open the wings", "pose"),
                ("add gold color", "appearance")]),
    # no full transfer was rendered: opens with the smile and the mountains
    dict(id="s3", src="all_is_correct/3", label="Studio portrait", subject="people",
         title="Earrings, expression, mountains", start="011",
         edits=[("add earrings", "object"),
                ("happy expression", "expression"),
                ("add a mountain and blue sky background", "background")]),
    # opens with the style off: diadem, hair and lake carried over, unpainted
    dict(id="s1", src="all_is_correct/1", label="Alley portrait", subject="people",
         title="Diadem, hair, lake, brushwork", start="1110",
         edits=[("add a celestial diadem", "object"),
                ("add orange hair", "appearance"),
                ("add a lake shore with reflections background", "background"),
                ("add Van Gogh style", "style")]),
]

EXAMPLES = [
    dict(id="x1", src="some_is_correct/1", result="supp_e2_e3.png", subject="people",
         title="Armor, without the hat or the jungle",
         edits=[("add armor", "object", 1),
                ("add a beach hat", "object", 0),
                ("jungle background", "background", 0)]),
    dict(id="x2", src="some_is_correct/2", result="supp_e3.png", subject="objects",
         title="The carving, in full color",
         edits=[("add carved Halloween texture", "appearance", 1),
                ("spooky candlelit table, dark background", "background", 1),
                ("black and white pencil style", "style", 0)]),
    dict(id="x8", src="some_is_correct/8", result="supp_e1_e4.png", subject="people",
         title="Wig and alley, in color",
         edits=[("add a blue scarf", "object", 0),
                ("add a short white hair wig", "appearance", 1),
                ("add an old cobblestone alley background", "background", 1),
                ("add black and white pencil style", "style", 0)]),
    dict(id="x4", src="some_is_correct/4", result="SIA.png", subject="creatures",
         title="Recolored, still standing",
         edits=[("change the dog color to blue", "appearance", 1),
                ("sitting pose", "pose", 0)]),
    dict(id="x5", src="some_is_correct/5", result="supp_e2.png", subject="people",
         title="Beard and street, same neutral face",
         edits=[("add a beard", "object", 1),
                ("happy expression", "expression", 0),
                ("street background", "background", 1)]),
    dict(id="x6", src="some_is_correct/6", result="supp_e2.png", subject="creatures",
         title="The jump, without the pencil",
         edits=[("jumping", "pose", 1),
                ("add colored pencil style", "style", 0)]),
    dict(id="x7", src="some_is_correct/7", result="supp_e2.png", subject="people",
         title="The beard, not the sunglasses",
         edits=[("add a professor beard", "object", 1),
                ("add sunglasses", "object", 0)]),
    dict(id="x3", src="some_is_correct/3", result="supp_e3.png", subject="objects",
         title="Logo and paint, doors closed",
         edits=[("add a golden star logo to the hood", "object", 1),
                ("change the car color to red", "appearance", 1),
                ("open the car doors", "pose", 0)]),
    # (x9 onwards follow; carousel order is set by EXAMPLE_ORDER below)
    dict(id="x9", src="some_is_correct/9", result="supp_e2.png", subject="people",
         title="Sunglasses, not the sad face",
         edits=[("add sunglasses", "object", 1),
                ("add a sad expression", "expression", 0),
                ("empty Japanese festival street background", "background", 1)]),
    dict(id="x10", src="some_is_correct/10", result="supp_e3.png", subject="people",
         title="Crown and necklace, calm face",
         edits=[("add an open-top crown", "object", 1),
                ("add a seamless gold necklace", "object", 1),
                ("add an angry expression", "expression", 0)]),
    dict(id="x11", src="some_is_correct/11", result="supp_e3.png", subject="people",
         title="Armor and hat, still at the beach",
         edits=[("add armor", "object", 1),
                ("add a beach hat", "object", 1),
                ("old cobblestone alley background", "background", 0)]),
    dict(id="x12", src="some_is_correct/12", result="no_supp.png", subject="people",
         title="All three edits, carried over",
         edits=[("add drop earrings", "object", 1),
                ("add a happy expression", "expression", 1),
                ("rolling green hills background", "background", 1)]),
    dict(id="x13", src="some_is_correct/13", result="supp_e3.png", subject="people",
         title="Beard and surprise, same path",
         edits=[("add a short beard", "object", 1),
                ("add a surprised expression", "expression", 1),
                ("lake shore with reflections background", "background", 0)]),
    dict(id="x14", src="some_is_correct/14", result="supp_e2.png", subject="people",
         title="Golden armor, no hat",
         edits=[("add golden armor", "object", 1),
                ("add a cowboy hat", "object", 0),
                ("add a rolling green hills background", "background", 1)]),
    dict(id="x15", src="some_is_correct/15", result="supp_e3.png", subject="creatures",
         title="Red shirt and sit, no painting",
         edits=[("add a red T-shirt", "object", 1),
                ("sitting pose", "pose", 1),
                ("add a minimalist painting style", "style", 0)]),
    dict(id="x16", src="some_is_correct/16", result="supp_e2_e4.png", subject="people",
         title="The scarf and the room, in color",
         edits=[("add a scarf", "object", 1),
                ("add a long blond hair wig", "appearance", 0),
                ("add a store interior background", "background", 1),
                ("add black and white pencil style", "style", 0)]),
    dict(id="x17", src="some_is_correct/17", result="supp_e4.png", subject="people",
         title="Crown, green hair and Paris, as a photo",
         edits=[("add an open-top crown without jewellery", "object", 1),
                ("add green hair", "appearance", 1),
                ("add a Paris background", "background", 1),
                ("add Van Gogh style", "style", 0)]),
    dict(id="x18", src="some_is_correct/18", result="supp_e2.png", subject="people",
         title="Armor and the stage, no hat",
         edits=[("add armor", "object", 1),
                ("add a beach hat", "object", 0),
                ("add an indoor music festival stage background", "background", 1)]),
    dict(id="x19", src="some_is_correct/19", result="no_supp.png", subject="people",
         title="Armor, hat and alley, all three",
         edits=[("add armor", "object", 1),
                ("add a beach hat", "object", 1),
                ("add an old cobblestone alley background", "background", 1)]),
    dict(id="x20", src="some_is_correct/20", result="supp_e3.png", subject="people",
         title="Earrings and a smile, still indoors",
         edits=[("add cluster earrings", "object", 1),
                ("add a happy expression", "expression", 1),
                ("add a peaceful countryside road background", "background", 0)]),
    dict(id="x21", src="some_is_correct/21", result="supp_e1.png", subject="people",
         title="The smile and the beach, no earrings",
         edits=[("add huggie earrings", "object", 0),
                ("add a happy expression", "expression", 1),
                ("add a sandy beach with ocean waves background", "background", 1)]),
    dict(id="x22", src="some_is_correct/22", result="no_supp.png", subject="people",
         title="Beard, surprise and the lake",
         edits=[("add a short beard", "object", 1),
                ("add a surprised expression", "expression", 1),
                ("add a lake shore with reflections background", "background", 1)]),
    dict(id="x23", src="some_is_correct/23", result="supp_e3.png", subject="people",
         title="Sweater and santa hat, same market",
         edits=[("add a sweater", "object", 1),
                ("add a santa hat", "object", 1),
                ("add a street background", "background", 0)]),
    dict(id="x24", src="some_is_correct/24", result="supp_e1.png", subject="objects",
         title="Red lamp in oils, no bench",
         edits=[("add a park metal bench", "object", 0),
                ("turn the lamp light red", "appearance", 1),
                ("add oil painting style", "style", 1)]),
    dict(id="x25", src="some_is_correct/25", result="no_supp.png", subject="creatures",
         title="Red shirt, sit and paint",
         edits=[("add a red T-shirt", "object", 1),
                ("sitting pose", "pose", 1),
                ("add a minimalist painting style", "style", 1)]),
    dict(id="x26", src="some_is_correct/26", result="supp_e1.png", subject="people",
         title="Wig, store and pencil, no scarf",
         edits=[("add a scarf", "object", 0),
                ("add a long blond hair wig", "appearance", 1),
                ("add a store interior background", "background", 1),
                ("add black and white pencil style", "style", 1)]),
    dict(id="x27", src="some_is_correct/27", result="supp_e1.png", subject="people",
         title="White wig in pencil, no scarf",
         edits=[("add a blue scarf", "object", 0),
                ("add a short white hair wig", "appearance", 1),
                ("add an old cobblestone alley background", "background", 1),
                ("add black and white pencil style", "style", 1)]),
    dict(id="x28", src="some_is_correct/28", result="supp_e1_e3.png", subject="people",
         title="Green hair in Van Gogh, same field",
         edits=[("add an open-top crown without jewellery", "object", 0),
                ("add green hair", "appearance", 1),
                ("add a Paris background", "background", 0),
                ("add Van Gogh style", "style", 1)]),
    # x29 onwards: the second batch, picked by eye from the evaluation runs
    dict(id="x29", src="some_is_correct/29", result="supp_e1.png", subject="people",
         title="Star glasses, no snow",
         edits=[("winter background", "background", 0),
                ("add star sunglasses", "object", 1)]),
    dict(id="x30", src="some_is_correct/30", result="supp_e1.png", subject="people",
         title="Star glasses, without the laugh",
         edits=[("laugh expression", "expression", 0),
                ("add star sunglasses", "object", 1)]),
    dict(id="x31", src="some_is_correct/31", result="supp_e1.png", subject="people",
         title="The hat, not the sad face",
         edits=[("sad expression", "expression", 0),
                ("add a hat", "object", 1)]),
    dict(id="x32", src="some_is_correct/32", result="supp_e1.png", subject="people",
         title="Surprised, but no pencil sketch",
         edits=[("black and white pencil-sketch style", "style", 0),
                ("surprised expression", "expression", 1)]),
    dict(id="x33", src="some_is_correct/33", result="supp_e2.png", subject="people",
         title="The laugh, without the sunglasses",
         edits=[("laugh expression", "expression", 1),
                ("add sunglasses", "object", 0)]),
    dict(id="x34", src="some_is_correct/34", result="supp_e2.png", subject="people",
         title="Angry, but no beard",
         edits=[("angry expression", "expression", 1),
                ("add a beard", "object", 0)]),
    dict(id="x35", src="some_is_correct/35", result="supp_e2.png", subject="people",
         title="Red lipstick, no necklace",
         edits=[("add lipstick", "appearance", 1),
                ("add a necklace", "object", 0)]),
    dict(id="x36", src="some_is_correct/36", result="supp_e1.png", subject="people",
         title="The crown, not the laugh",
         edits=[("laugh expression", "expression", 0),
                ("add a crown", "object", 1)]),
    dict(id="x37", src="some_is_correct/37", result="supp_e2.png", subject="people",
         title="The yawn, not the nose ring",
         edits=[("yawning expression", "expression", 1),
                ("add a nose ring", "object", 0)]),
    dict(id="x38", src="some_is_correct/38", result="supp_e1.png", subject="people",
         title="Sunglasses, no armor",
         edits=[("add armor", "object", 0),
                ("add sunglasses", "object", 1)]),
    dict(id="x39", src="some_is_correct/39", result="supp_e2.png", subject="people",
         title="The beard, not the crown",
         edits=[("add a beard", "object", 1),
                ("add a king's crown", "object", 0)]),
    dict(id="x40", src="some_is_correct/40", result="supp_e1.png", subject="people",
         title="Arms up, no clown face",
         edits=[("look like a clown", "appearance", 0),
                ("raise arms behind the head", "pose", 1)]),
    dict(id="x41", src="some_is_correct/41", result="supp_e2.png", subject="people",
         title="The laugh, no cross",
         edits=[("laugh expression", "expression", 1),
                ("add a cross necklace", "object", 0)]),
    dict(id="x42", src="some_is_correct/42", result="supp_e2.png", subject="people",
         title="Eyes open, no purple lipstick",
         edits=[("open the eyes", "expression", 1),
                ("add purple lipstick", "appearance", 0)]),
    dict(id="x43", src="some_is_correct/43", result="supp_e1.png", subject="people",
         title="A beard, same open mouth",
         edits=[("poker face expression", "expression", 0),
                ("add a beard", "object", 1)]),
    dict(id="x44", src="some_is_correct/44", result="supp_e1.png", subject="people",
         title="Arms behind the head, still squatting",
         edits=[("stand up", "pose", 0),
                ("raise arms behind the head", "pose", 1)]),
    dict(id="x45", src="some_is_correct/45", result="supp_e1.png", subject="people",
         title="Sad in the meadow, no sunglasses",
         edits=[("add sunglasses", "object", 0),
                ("sad expression", "expression", 1),
                ("sunny wildflower meadow background", "background", 1)]),
    dict(id="x46", src="some_is_correct/46", result="supp_e1.png", subject="people",
         title="Necklace and a scowl, no crown",
         edits=[("add an open-top crown", "object", 0),
                ("add a necklace", "object", 1),
                ("angry expression", "expression", 1)]),
    dict(id="x47", src="some_is_correct/47", result="supp_e1.png", subject="people",
         title="Hat and jungle, no armor",
         edits=[("add armor", "object", 0),
                ("add a beach hat", "object", 1),
                ("jungle background", "background", 1)]),
    dict(id="x48", src="some_is_correct/48", result="supp_e3.png", subject="people",
         title="Earrings and a smile, no mountains",
         edits=[("add earrings", "object", 1),
                ("happy expression", "expression", 1),
                ("mountain with blue sky background", "background", 0)]),
    dict(id="x49", src="some_is_correct/49", result="supp_e1.png", subject="people",
         title="Smile and street, no beard",
         edits=[("add a beard", "object", 0),
                ("happy expression", "expression", 1),
                ("street background", "background", 1)]),
    dict(id="x50", src="some_is_correct/50", result="supp_e3_e4.png", subject="people",
         title="Crown and blond hair, still a photo",
         edits=[("add an open-top crown", "object", 1),
                ("add long blond hair", "appearance", 1),
                ("Italian street background", "background", 0),
                ("add Van Gogh style", "style", 0)]),
    dict(id="x51", src="some_is_correct/51", result="supp_e2.png", subject="objects",
         title="Star logo, original silver paint",
         edits=[("add a golden star logo to the hood", "object", 1),
                ("change the car color to red", "appearance", 0)]),
    dict(id="x52", src="some_is_correct/52", result="supp_e3.png", subject="objects",
         title="Logo and mountains, not a comic",
         edits=[("add a dinosaur logo", "object", 1),
                ("mountain road with blue sky background", "background", 1),
                ("comic style", "style", 0)]),
    dict(id="x53", src="some_is_correct/53", result="supp_e3.png", subject="objects",
         title="Carved pineapple by candlelight",
         edits=[("add carved Halloween texture", "appearance", 1),
                ("spooky candlelit table, dark background", "background", 1),
                ("black and white pencil style", "style", 0)]),
    dict(id="x54", src="some_is_correct/54", result="supp_e2_e3.png", subject="objects",
         title="Carved, still in the garden",
         edits=[("add carved Halloween texture", "appearance", 1),
                ("spooky candlelit table, dark background", "background", 0),
                ("black and white pencil style", "style", 0)]),
    dict(id="x55", src="some_is_correct/55", result="supp_e2.png", subject="scenes",
         title="Oil painting, no moss",
         edits=[("add a bed lamp", "object", 1),
                ("add moss all over the scene", "appearance", 0),
                ("old oil painting style", "style", 1)]),
    dict(id="x56", src="some_is_correct/56", result="supp_e3.png", subject="people",
         title="Sunglasses and a frown, no meadow",
         edits=[("add sunglasses", "object", 1),
                ("sad expression", "expression", 1),
                ("sunny wildflower meadow background", "background", 0)]),
    dict(id="x57", src="some_is_correct/57", result="supp_e2.png", subject="creatures",
         title="Sitting, but not blue",
         edits=[("sitting pose", "pose", 1),
                ("change the dog color to blue", "appearance", 0)]),
    dict(id="x58", src="some_is_correct/58", result="supp_e2_e3_e4.png", subject="people",
         title="Only the punk wig",
         edits=[("add a punk wig", "appearance", 1),
                ("add a scarf", "object", 0),
                ("rural countryside background", "background", 0),
                ("black and white pencil style", "style", 0)]),
    dict(id="x59", src="some_is_correct/59", result="supp_e3.png", subject="creatures",
         title="Lava and open wings, not the gold",
         edits=[("add lava to the ground", "background", 1),
                ("open the wings", "pose", 1),
                ("add gold color", "appearance", 0)]),
    dict(id="x60", src="some_is_correct/60", result="supp_e2.png", subject="people",
         title="Sunglasses and the meadow, no frown",
         edits=[("add sunglasses", "object", 1),
                ("sad expression", "expression", 0),
                ("sunny wildflower meadow background", "background", 1)]),
    dict(id="x61", src="some_is_correct/61", result="supp_e2_e3.png", subject="people",
         title="Just the sunglasses",
         edits=[("add sunglasses", "object", 1),
                ("sad expression", "expression", 0),
                ("sunny wildflower meadow background", "background", 0)]),
    dict(id="x62", src="some_is_correct/62", result="supp_e3.png", subject="people",
         title="Crown and necklace, no scowl",
         edits=[("add an open-top crown", "object", 1),
                ("add a necklace", "object", 1),
                ("angry expression", "expression", 0)]),
    dict(id="x63", src="some_is_correct/63", result="supp_e1_e3_e4.png", subject="people",
         title="Only the long blond hair",
         edits=[("add an open-top crown", "object", 0),
                ("add long blond hair", "appearance", 1),
                ("Italian street background", "background", 0),
                ("add Van Gogh style", "style", 0)]),
    dict(id="x64", src="some_is_correct/64", result="supp_e2.png", subject="creatures",
         title="Sitting, still brown",
         edits=[("sitting pose", "pose", 1),
                ("change the dog color to blue", "appearance", 0)]),
    dict(id="x65", src="some_is_correct/65", result="supp_e1.png", subject="creatures",
         title="Blue, still standing",
         edits=[("sitting pose", "pose", 0),
                ("change the dog color to blue", "appearance", 1)]),
    dict(id="x66", src="some_is_correct/66", result="no_supp.png", subject="creatures",
         title="Blue and sitting",
         edits=[("sitting pose", "pose", 1),
                ("change the dog color to blue", "appearance", 1)]),
    # x67 onwards: more objects and animals from the older evaluation run
    # (KianIzadpanah/SIA_Evaluation_Data_Results, *_non_creature cases).
    dict(id="x67", src="some_is_correct/67", result="supp_e2_e3.png", subject="objects",
         title="Carved apple, still in color",
         edits=[("add carved Halloween texture", "appearance", 1),
                ("spooky candlelit table, dark background", "background", 0),
                ("black and white pencil style", "style", 0)]),
    dict(id="x68", src="some_is_correct/68", result="supp_e2.png", subject="objects",
         title="Carved apple in pencil, no candles",
         edits=[("add carved Halloween texture", "appearance", 1),
                ("spooky candlelit table, dark background", "background", 0),
                ("black and white pencil style", "style", 1)]),
    dict(id="x69", src="some_is_correct/69", result="supp_e1_e2.png", subject="objects",
         title="Watermelon in pencil, not carved",
         edits=[("add carved Halloween texture", "appearance", 0),
                ("spooky candlelit table, dark background", "background", 0),
                ("black and white pencil style", "style", 1)]),
    dict(id="x70", src="some_is_correct/70", result="supp_e1.png", subject="objects",
         title="Candlelit pencil sketch, no carving",
         edits=[("add carved Halloween texture", "appearance", 0),
                ("spooky candlelit table, dark background", "background", 1),
                ("black and white pencil style", "style", 1)]),
    dict(id="x71", src="some_is_correct/71", result="supp_e2_e3.png", subject="objects",
         title="Just the dinosaur logo",
         edits=[("add a dinosaur logo", "object", 1),
                ("mountain road with blue sky background", "background", 0),
                ("comic style", "style", 0)]),
    dict(id="x72", src="some_is_correct/72", result="supp_e1.png", subject="objects",
         title="Comic mountain road, no logo",
         edits=[("add a dinosaur logo", "object", 0),
                ("mountain road with blue sky background", "background", 1),
                ("comic style", "style", 1)]),
    dict(id="x73", src="some_is_correct/73", result="supp_e1_e3.png", subject="objects",
         title="Only the mountain road",
         edits=[("add a dinosaur logo", "object", 0),
                ("mountain road with blue sky background", "background", 1),
                ("comic style", "style", 0)]),
    dict(id="x74", src="some_is_correct/74", result="supp_e1.png", subject="objects",
         title="Red paint, no star",
         edits=[("add a golden star logo to the hood", "object", 0),
                ("change the car color to red", "appearance", 1)]),
    dict(id="x75", src="some_is_correct/75", result="supp_e2.png", subject="creatures",
         title="Sitting, still golden",
         edits=[("sitting pose", "pose", 1),
                ("change the dog color to blue", "appearance", 0)]),
    # x76 onwards: other subsets of the x59 (dragon) and x25 (dog) pairs, from
    # the scored run (KianIzadpanah/SIA_Rebuttal_Baselines, 3edits_non_creature
    # data29 and data67); A, A' and B are the same files as x59 / x25.
    dict(id="x76", src="some_is_correct/76", result="supp_e1_e3.png", subject="creatures",
         title="Wings open, no lava or gold",
         edits=[("add lava to the ground", "background", 0),
                ("open the wings", "pose", 1),
                ("add gold color", "appearance", 0)]),
    dict(id="x77", src="some_is_correct/77", result="supp_e1.png", subject="creatures",
         title="Gold and open wings, no lava",
         edits=[("add lava to the ground", "background", 0),
                ("open the wings", "pose", 1),
                ("add gold color", "appearance", 1)]),
    dict(id="x78", src="some_is_correct/78", result="supp_e2_e3.png", subject="creatures",
         title="Just the red shirt",
         edits=[("add a red T-shirt", "object", 1),
                ("sitting pose", "pose", 0),
                ("add a minimalist painting style", "style", 0)]),
    dict(id="x79", src="some_is_correct/79", result="supp_e1_e3.png", subject="creatures",
         title="Only the sit",
         edits=[("add a red T-shirt", "object", 0),
                ("sitting pose", "pose", 1),
                ("add a minimalist painting style", "style", 0)]),
    dict(id="x80", src="some_is_correct/80", result="supp_e1_e2.png", subject="creatures",
         title="Only the painting style",
         edits=[("add a red T-shirt", "object", 0),
                ("sitting pose", "pose", 0),
                ("add a minimalist painting style", "style", 1)]),
    dict(id="x81", src="some_is_correct/81", result="supp_e1.png", subject="creatures",
         title="Sitting in paint, no shirt",
         edits=[("add a red T-shirt", "object", 0),
                ("sitting pose", "pose", 1),
                ("add a minimalist painting style", "style", 1)]),
    dict(id="x82", src="some_is_correct/82", result="supp_e2.png", subject="creatures",
         title="Shirt and paint, still standing",
         edits=[("add a red T-shirt", "object", 1),
                ("sitting pose", "pose", 0),
                ("add a minimalist painting style", "style", 1)]),
]


# The Examples section, in the order it plays: objects and animals first and
# most, portraits spread so no two follow each other, and subsets of the same
# pair kept apart.
EXAMPLE_ORDER = [
    "x59", "x67", "x56", "x78", "x71", "x58", "x3", "x24",
    "x13", "x2", "x80", "x63", "x76", "x23", "x4", "x17",
    "x70", "x44", "x79", "x30", "x74", "x27", "x55", "x32",
    "x77", "x14", "x69", "x26", "x15", "x72", "x9", "x53",
    "x1", "x81", "x42", "x68", "x57", "x50", "x82", "x8",
    "x51", "x47", "x64",
]

# Portraits kept in EXAMPLES and in `new figures/` but not built or shown, so
# the page isn't dominated by people. Move an id into EXAMPLE_ORDER to bring
# one back.
HELD_BACK = [
    "x45", "x35", "x41", "x62", "x20", "x31", "x28", "x39", "x60", "x16",
    "x36", "x5", "x43", "x33", "x10", "x61", "x48", "x11", "x29", "x21",
    "x46", "x18", "x38", "x12", "x49", "x22", "x19", "x7",
]

# Never shown: the result fails, or there is nothing selective about it.
REJECTED = {
    "x34": "the beard it was meant to drop appears anyway",
    "x37": "the yawn reads as a scream",
    "x40": "an awkward, half-raised pose",
    "x6": "the jump barely shows",
    "x25": "full transfer: every edit kept",
    "x66": "full transfer: every edit kept",
    "x65": "the dog sits although sitting was dropped",
    "x75": "the dog barely changes",
    "x52": "comic style leaks into the mountains",
    "x73": "comic style leaks into the mountains",
    "x54": "the carved watermelon turns yellow and reads as another fruit",
}


# ---------------------------------------------------------------- build
def mask_from_filename(fn, n):
    """`supp_e1_e3.png` with n=4 -> "0101" (1 = edit kept)."""
    supp = {int(t) for t in re.findall(r"e(\d+)", fn)}
    out_of_range = [i for i in supp if i < 1 or i > n]
    assert not out_of_range, f"{fn}: edit index out of range {out_of_range}"
    return "".join("0" if (i + 1) in supp else "1" for i in range(n))


def main():
    if os.path.isdir(IMG):
        shutil.rmtree(IMG)

    out_samples = []

    for s in SAMPLES:
        d = os.path.join(SRC, s["src"])
        n = len(s["edits"])
        dim = prep(os.path.join(d, "a.png")).size
        dest = os.path.join(IMG, "samples", s["id"])
        for name, fn in (("a", "a.png"), ("ap", "a_prime.png"), ("b", "b.png")):
            im = prep(os.path.join(d, fn)).resize(dim, Image.LANCZOS)
            save(im, os.path.join(dest, name + ".webp"))
            lite(im, os.path.join(dest, "lite", name + ".webp"))
        thumb(prep(os.path.join(d, "b.png")), os.path.join(dest, "thumb.webp"))

        available = []
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".png"):
                continue
            if fn == "no_supp.png":
                mask = "1" * n
            elif fn.startswith("supp_"):
                mask = mask_from_filename(fn, n)
            else:
                continue
            im = prep(os.path.join(d, fn)).resize(dim, Image.LANCZOS)
            save(im, os.path.join(dest, "subsets", mask + ".webp"))
            lite(im, os.path.join(dest, "lite", "subsets", mask + ".webp"))
            available.append(mask)
        available.sort(key=lambda m: (-m.count("1"), m))

        assert s["start"] in available or "1" not in s["start"], (
            "%s: start %s was not rendered" % (s["id"], s["start"]))
        out_samples.append(dict(
            id=s["id"], label=s["label"], title=s["title"], subject=s["subject"],
            start=s["start"], w=dim[0], h=dim[1], dir="static/images/samples/" + s["id"],
            edits=[dict(id="e%d" % (i + 1), label=lb, type=tp)
                   for i, (lb, tp) in enumerate(s["edits"])],
            available=available))
        print("%s: %s  %d/%d combinations  %s"
              % (s["id"], dim, len(available), 2 ** n, available))

    by_id = {x["id"]: x for x in EXAMPLES}
    listed = EXAMPLE_ORDER + HELD_BACK + list(REJECTED)
    assert len(listed) == len(set(listed)), (
        "an example is listed twice across EXAMPLE_ORDER, HELD_BACK and REJECTED")
    assert set(by_id) == set(listed), (
        "EXAMPLE_ORDER + HELD_BACK + REJECTED disagree with EXAMPLES: %s"
        % (set(by_id) ^ set(listed)))

    def build_example(x):
        d = os.path.join(SRC, x["src"])
        dim = prep(os.path.join(d, "a.png")).size
        dest = os.path.join(IMG, "examples", x["id"])
        for name, fn in (("a", "a.png"), ("ap", "a_prime.png"),
                         ("b", "b.png"), ("out", x["result"])):
            im = prep(os.path.join(d, fn))
            if im.size != dim:
                im = im.resize(dim, Image.LANCZOS)
            save(im, os.path.join(dest, name + ".webp"))
            lite(im, os.path.join(dest, "lite", name + ".webp"))
        thumb(prep(os.path.join(d, x["result"])), os.path.join(dest, "thumb.webp"))

        keep = "".join(str(k) for _, _, k in x["edits"])
        if x["result"].startswith("supp_"):
            expect = mask_from_filename(x["result"], len(x["edits"]))
        elif x["result"] == "no_supp.png":
            expect = "1" * len(x["edits"])          # full transfer, nothing suppressed
        else:
            expect = keep                            # hand-named render, e.g. SIA.png
        assert expect == keep, ("%s: %s implies %s but metadata says %s"
                                % (x["id"], x["result"], expect, keep))

        print("%s: %s  keep=%s  <- %s" % (x["id"], dim, keep, x["result"]))
        return dict(
            id=x["id"], title=x["title"], subject=x["subject"],
            w=dim[0], h=dim[1], dir="static/images/examples/" + x["id"],
            edits=[dict(id="e%d" % (i + 1), label=lb, type=tp, kept=bool(k))
                   for i, (lb, tp, k) in enumerate(x["edits"])])

    out_examples = [build_example(by_id[i]) for i in EXAMPLE_ORDER]

    # The ExLoRA training sample shown in the Method section: the same input
    # and full prompt as usual, with "gold color" masked and a target that
    # leaves the gold out (from SIA_slides_animated.pptx, slide 27).
    d = os.path.join(SRC, "exlora_training")
    dim = prep(os.path.join(d, "a.png")).size
    for name, fn in (("a", "a.png"), ("ap", "a_prime.png"), ("b", "b.png"), ("target", "target.png")):
        save(prep(os.path.join(d, fn)), os.path.join(IMG, "training", name + ".webp"), dim)
    print("training sample: %s" % (dim,))

    js = os.path.join(ROOT, "static", "js", "data.js")
    os.makedirs(os.path.dirname(js), exist_ok=True)
    with open(js, "w", encoding="utf-8") as f:
        f.write("/* Generated by tools/build_images.py - do not edit by hand. */\n")
        f.write("window.SIA_SAMPLES = "
                + json.dumps(out_samples, indent=2, ensure_ascii=False) + ";\n\n")
        f.write("window.SIA_EXAMPLES = "
                + json.dumps(out_examples, indent=2, ensure_ascii=False) + ";\n")

    total = sum(os.path.getsize(os.path.join(r, fn))
                for r, _, fns in os.walk(IMG) for fn in fns)
    count = sum(len(fns) for _, _, fns in os.walk(IMG))
    print("\n%d webp files, %.2f MB total" % (count, total / 1024 / 1024))


if __name__ == "__main__":
    main()
