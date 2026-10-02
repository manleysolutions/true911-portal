"""Build the True911 Beacon production SVG family from one geometry.

Geometry is CONSTRUCTED (not traced) from proportions measured on
brand_source/Gradient Beacon Location Pin Logo.png:
  * a pin-shaped band: an outer circle joined by tangent lines to the location
    point, offset inward by the band thickness;
  * the band is opened at 12 o'clock (notch), split at the point (slot) and cut
    twice low on the ring, separating the converging legs;
  * a protected central node: a disc with a small core opening.
Text is converted to outlines from Inter (SIL Open Font License 1.1).

Usage (writes the production SVGs into web/public/brand):
    python tools/brand/build_beacon_assets.py --fonts <dir with inter-700.ttf, inter-600.ttf>
Fetch the fonts from Google Fonts (OFL): the static Inter 700 and 600 TTFs.
The two PNGs (apple-touch-icon.png 180x180, favicon-32.png) are rasterised from
favicon.svg and the _apple-touch-icon.svg written to --raster-dir with any SVG
renderer (headless Edge was used for the first release).
Never use the brand_source concept boards as production assets.
"""
import argparse
import math
import os

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
_ap = argparse.ArgumentParser()
_ap.add_argument("--fonts", required=True, help="directory containing inter-700.ttf and inter-600.ttf")
_ap.add_argument("--out", default=os.path.join(REPO, "web", "public", "brand"))
_ap.add_argument("--raster-dir", default=os.path.join(REPO, ".brand-raster"))
ARGS = _ap.parse_args()
OUT = ARGS.out
os.makedirs(OUT, exist_ok=True)
os.makedirs(ARGS.raster_dir, exist_ok=True)

NAVY, BLUE, LIGHT, WHITE = "#0B1F3B", "#2D8CFF", "#60A9FF", "#FFFFFF"
MID = "#1C6FE6"           # gradient step between Blue and Navy (sampled #0F6BE8 upper left)
DEEP = "#12408F"          # gradient step toward Navy (sampled #023A80 lower left)
SLATE = "#4A5B75"         # descriptor on light (6.9:1 on white)
SOFT = "#C9D6EA"          # descriptor on navy (11:1 on #0B1F3B)


def f(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Geo:
    # measured on the 1264x1244 master, scaled so the mark is 60 units tall
    def __init__(self, **kw):
        self.cx, self.cy = 32.0, 28.2
        self.r_out, self.r_in = 26.2, 18.6
        self.tip_y = 62.0
        self.node, self.core = 11.3, 2.9
        self.notch, self.slot, self.cut = 3.1, 3.3, 1.7
        self.cut_left, self.cut_right = -140.5, 129.0     # deg, clockwise from 12 o'clock
        self.__dict__.update(kw)

    def pin(self, r, d):
        """Pin contour: circle radius r joined by tangents to the point at distance d below centre."""
        alpha = math.acos(r / d)                       # tangent angle from the downward axis
        ang = math.pi - alpha                           # clockwise from 12 o'clock
        tx = r * math.sin(ang)
        ty = -r * math.cos(ang)
        tip = (self.cx, self.cy + d)
        pr = (self.cx + tx, self.cy + ty)
        pl = (self.cx - tx, self.cy + ty)
        return (f"M{f(tip[0])} {f(tip[1])}L{f(pr[0])} {f(pr[1])}"
                f"A{f(r)} {f(r)} 0 1 0 {f(pl[0])} {f(pl[1])}Z")

    def body(self, band_fill, node_fill, uid, defs=""):
        d_out = self.tip_y - self.cy
        alpha = math.acos(self.r_out / d_out)
        d_in = self.r_in / math.cos(alpha)             # parallel offset keeps the same tangent angle
        band = self.pin(self.r_out, d_out) + self.pin(self.r_in, d_in)
        t = self.r_out - self.r_in
        y0 = self.cy - self.r_out - 1
        cuts = "".join(
            f'<rect x="{f(self.cx - w / 2)}" y="{f(y0)}" width="{f(w)}" height="{f(t + 2)}" '
            f'transform="rotate({f(a)} {f(self.cx)} {f(self.cy)})"/>'
            for a, w in ((0, self.notch), (self.cut_left, self.cut), (self.cut_right, self.cut)))
        slot = (f'<rect x="{f(self.cx - self.slot / 2)}" y="{f(self.cy + d_in - 0.6)}" width="{f(self.slot)}" '
                f'height="{f(self.tip_y - (self.cy + d_in) + 2)}"/>')
        node = (f'M{f(self.cx - self.node)} {f(self.cy)}a{f(self.node)} {f(self.node)} 0 1 0 {f(2 * self.node)} 0'
                f'a{f(self.node)} {f(self.node)} 0 1 0 {f(-2 * self.node)} 0Z')
        if self.core:
            node += (f'M{f(self.cx - self.core)} {f(self.cy)}a{f(self.core)} {f(self.core)} 0 1 0 {f(2 * self.core)} 0'
                     f'a{f(self.core)} {f(self.core)} 0 1 0 {f(-2 * self.core)} 0Z')
        return (f'<defs>{defs}<mask id="{uid}-m" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">'
                f'<rect width="64" height="64" fill="#fff"/><g fill="#000">{cuts}{slot}</g></mask></defs>'
                f'<path fill="{band_fill}" fill-rule="evenodd" mask="url(#{uid}-m)" d="{band}"/>'
                f'<path fill="{node_fill}" fill-rule="evenodd" d="{node}"/>')


def grad(uid, stops, x1=52, y1=4, x2=12, y2=60):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return (f'<linearGradient id="{uid}" gradientUnits="userSpaceOnUse" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
            f'{s}</linearGradient>')


MASTER = Geo()
# favicon: same identity; wider openings and a solid node so it survives 16px
FAV = Geo(notch=5.0, slot=5.2, cut=3.0, core=0, node=10.5)


def master_body(uid, variant):
    if variant == "color":          # on light surfaces: the brand gradient, Blue -> Navy
        g = grad(f"{uid}-g", ((0, BLUE), (0.42, MID), (0.78, DEEP), (1, NAVY)))
        return MASTER.body(f"url(#{uid}-g)", f"url(#{uid}-g)", uid, g)
    if variant == "reversed":       # on navy: light gradient band, white node
        g = grad(f"{uid}-g", ((0, LIGHT), (1, BLUE)))
        return MASTER.body(f"url(#{uid}-g)", WHITE, uid, g)
    return MASTER.body("currentColor", "currentColor", uid)


def text_path(font_file, text, size, x, y, tracking=0.0):
    font = TTFont(font_file)
    gs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    scale = size / font["head"].unitsPerEm
    paths, cx = [], x
    for ch in text:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, cx, y)))
        if pen.getCommands():
            paths.append(pen.getCommands())
        cx += hmtx[g][0] * scale + tracking * size
    return " ".join(paths), cx - tracking * size


def svg(inner, vb, w, h, label=None, style=""):
    st = f' style="{style}"' if style else ""
    a11y = f'role="img" aria-label="{label}"><title>{label}</title>' if label else 'aria-hidden="true">'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w}" height="{h}"{st} {a11y}{inner}</svg>\n'


BOLD = os.path.join(ARGS.fonts, "inter-700.ttf")
SEMI = os.path.join(ARGS.fonts, "inter-600.ttf")


def lockup(true_c, nine_c, desc_c, mark, label, style=""):
    tp, x1 = text_path(BOLD, "True", 34, 74, 34, tracking=-0.02)
    np_, x2 = text_path(BOLD, "911", 34, x1 + 0.5, 34, tracking=-0.02)
    dp, x3 = text_path(SEMI, "LIFE-SAFETY COMMUNICATIONS", 8.4, 75.5, 50.5, tracking=0.16)
    width = math.ceil(max(x2, x3) + 2)
    inner = mark + f'<path fill="{true_c}" d="{tp}"/><path fill="{nine_c}" d="{np_}"/><path fill="{desc_c}" d="{dp}"/>'
    return svg(inner, f"0 0 {width} 64", width * 2, 128, label, style)


def write(name, content, folder=None):
    with open(os.path.join(folder or OUT, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    print(f"{name:32s} {len(content.encode()):6d} bytes")


if __name__ == "__main__":
    lab = "True911 — Life-Safety Communications"
    write("true911-beacon.svg", svg(master_body("b", "color"), "0 0 64 64", 64, 64, "True911"))
    write("true911-beacon-reversed.svg", svg(master_body("br", "reversed"), "0 0 64 64", 64, 64, "True911"))
    write("true911-logo-horizontal.svg", lockup(NAVY, BLUE, SLATE, master_body("h", "color"), lab))
    write("true911-logo-reversed.svg", lockup(WHITE, LIGHT, SOFT, master_body("r", "reversed"), lab))
    write("true911-logo-monochrome.svg", lockup("currentColor", "currentColor", "currentColor",
                                               master_body("m", "mono"), lab, style="color:#0B1F3B"))
    def tile(rx, scale):
        off = 32 * (1 - scale)
        return (f'<rect width="64" height="64" rx="{rx}" fill="{NAVY}"/><g transform="translate({f(off)} {f(off - 1)}) scale({scale})">'
                + FAV.body("url(#f-g)", WHITE, "f", grad("f-g", ((0, LIGHT), (1, BLUE)))) + "</g>")
    write("favicon.svg", svg(tile(14, 0.9), "0 0 64 64", 64, 64, "True911"))
    # full-bleed square for the Apple touch icon (iOS applies its own corner mask)
    write("_apple-touch-icon.svg", svg(tile(0, 0.78), "0 0 64 64", 180, 180), ARGS.raster_dir)
