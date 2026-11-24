#!/usr/bin/env python3
"""
One-off font builder (NOT run by the GitHub Action; needs `pip install fonttools`).

Takes a variable TTF (default: Plus Jakarta Sans, the portfolio's font), cuts static
instances, subsets them to the characters the cards use, and writes:

  fonts/display.woff     weight 800  (name, big numbers)
  fonts/body.woff        weight 500  (body text)
  fonts/body-bold.woff   weight 700  (labels, tagline)
  fonts/metrics.json     advance widths, so render_cards.py (stdlib only) can measure text

  python scripts/build_fonts.py path/to/PlusJakartaSans[wght].ttf
"""
import json
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTS = Path(__file__).resolve().parent.parent / "fonts"
CHARS = [chr(c) for c in range(0x20, 0x7F)] + ["·", "—", "’", "…"]
FACES = {"display": 800, "body": 500, "body-bold": 700}


def kerning(font, cmap):
    """{"AV": -40, ...} from the GPOS 'kern' pair-positioning lookups (formats 1 and 2)."""
    if "GPOS" not in font:
        return {}
    gpos = font["GPOS"].table
    idx = sorted({i for fr in gpos.FeatureList.FeatureRecord if fr.FeatureTag == "kern"
                  for i in fr.Feature.LookupListIndex})
    subtables = []
    for i in idx:
        for st in gpos.LookupList.Lookup[i].SubTable:
            st = getattr(st, "ExtSubTable", st)
            if getattr(st, "LookupType", 2) == 2:
                subtables.append(st)

    def pair_value(g1, g2):
        for st in subtables:
            cov = st.Coverage.glyphs
            if g1 not in cov:
                continue
            if st.Format == 1:
                for rec in st.PairSet[cov.index(g1)].PairValueRecord:
                    if rec.SecondGlyph == g2:
                        return getattr(rec.Value1, "XAdvance", 0) or 0
            elif st.Format == 2:
                c1 = st.ClassDef1.classDefs.get(g1, 0)
                c2 = st.ClassDef2.classDefs.get(g2, 0)
                v = st.Class1Record[c1].Class2Record[c2].Value1
                return getattr(v, "XAdvance", 0) or 0
        return 0

    glyph = {c: cmap[ord(c)] for c in CHARS if ord(c) in cmap}
    out = {}
    for a, ga in glyph.items():
        for b, gb in glyph.items():
            v = pair_value(ga, gb)
            if v:
                out[a + b] = v
    return out


def main(src):
    FONTS.mkdir(exist_ok=True)
    metrics = {}
    for name, weight in FACES.items():
        font = TTFont(src)
        if "fvar" in font:
            font = instancer.instantiateVariableFont(font, {"wght": weight})
        opts = subset.Options()
        opts.flavor = "woff"
        opts.layout_features = ["kern", "liga"]
        opts.hinting = False
        opts.desubroutinize = True
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=[ord(c) for c in CHARS])
        sub.subset(font)
        out = FONTS / f"{name}.woff"
        font.flavor = "woff"
        font.save(out)

        cmap, hmtx = font.getBestCmap(), font["hmtx"]
        metrics[name] = {
            "upm": font["head"].unitsPerEm,
            "adv": {c: hmtx[cmap[ord(c)]][0] for c in CHARS if ord(c) in cmap},
            "kern": kerning(font, cmap),
        }
        print(f"{out.name}: {out.stat().st_size / 1024:.1f} KB")
    (FONTS / "metrics.json").write_text(json.dumps(metrics, separators=(",", ":")), encoding="utf-8")
    print("metrics.json written")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "PlusJakartaSans[wght].ttf")
