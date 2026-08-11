"""Build a stand from measurements alone, no donor model required.

Layout (Y is up, matching the donor STLs):

      Z=0 ......................... front
      +-----------------------------+
      |  mag bar  [ ][ ][ ]         |   pockets open upward
      +-----------------------------+
      |  deck  (logo lives here)    |
      |        [grip tower]         |   slot leans back
      +-----------------------------+
                                      back
"""
from __future__ import annotations

import numpy as np
import trimesh

from . import primitives as prim
from . import text as textmod
from .spec import StandSpec


def _mag_bar(spec: StandSpec):
    """The block of magazine pockets, plus the pocket centres for reuse."""
    mag, base = spec.mag, spec.base
    pw, pd = mag.pocket_width, mag.pocket_thickness

    end_wall = max(4.0, pw * 0.14)
    mid_wall = max(6.0, pw * 0.38)
    side_wall = max(4.0, pd * 0.22)

    width = 2 * end_wall + mag.count * pw + (mag.count - 1) * mid_wall
    depth = pd + 2 * side_wall
    height = mag.bar_height

    bar = prim.box(width, height, depth, [width / 2, height / 2, depth / 2])

    centres, x = [], end_wall
    for _ in range(mag.count):
        centres.append((x + pw / 2, depth / 2))
        x += pw + mid_wall

    cutters = []
    for cx, cz in centres:
        cutters += prim.pocket_cutters(cx, cz, pw, pd, mag.floor, height, mag.chamfer)

    return prim.difference(bar, cutters), width, depth, centres


def _grip_tower(spec: StandSpec, cx: float, cz: float):
    """A leaning blade with a slot the grip wedges into."""
    grip = spec.grip
    sw, st = grip.slot_width, grip.slot_thickness
    w = sw + 2 * grip.wall
    d = st + 2 * grip.wall
    h = grip.height
    lean = np.radians(grip.lean)

    # tapered tower: full section at the base, slightly narrower at the top
    top_scale = 0.86
    lower = prim.box(w + 6, spec.base.thickness + 4, d + 6,
                     [cx, (spec.base.thickness + 4) / 2, cz])   # fillet-ish foot
    body = _tapered_box(cx, cz, w, d, w * top_scale, d * top_scale,
                        spec.base.thickness, spec.base.thickness + h)
    tower = prim.union([lower, body])

    # slot: a tall box, tilted about X so its top leans toward the back (+Z)
    slot_h = grip.slot_depth + 4
    slot_top = spec.base.thickness + h + 2
    slot = prim.box(sw, slot_h, st, [0, 0, 0])
    tilt = trimesh.transformations.rotation_matrix(lean, [1, 0, 0])
    slot.apply_transform(tilt)
    slot.apply_translation([cx, slot_top - slot_h / 2, cz])

    return prim.difference(tower, [slot])


def _tapered_box(cx, cz, w0, d0, w1, d1, y0, y1) -> trimesh.Trimesh:
    """A four-sided frustum between two rectangles."""
    verts = []
    for hw, hd, y in ((w0 / 2, d0 / 2, y0), (w1 / 2, d1 / 2, y1)):
        verts += [[cx - hw, y, cz - hd], [cx + hw, y, cz - hd],
                  [cx + hw, y, cz + hd], [cx - hw, y, cz + hd]]
    faces = []
    for k in range(4):
        j = (k + 1) % 4
        faces += [[k, j, 4 + j], [k, 4 + j, 4 + k]]
    faces += [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7]]
    mesh = trimesh.Trimesh(vertices=np.array(verts, dtype=float), faces=np.array(faces))
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _logo(spec: StandSpec, cx: float, cz: float):
    """Raised deck lettering (and optional banner) as separate colour bodies."""
    logo = spec.logo
    if not logo.enabled:
        return []

    glyphs = textmod.text_polygons(logo.text, logo.size) if logo.text else []
    out = []
    if glyphs:
        placed = textmod.place(glyphs, cx, cz)
        out.append(("letters",
                    prim.prism_from_polygons(placed, spec.base.thickness,
                                             logo.letter_height)))
    if logo.banner and glyphs:
        ring = textmod.banner_ring(textmod.place(glyphs, cx, cz),
                                   logo.banner_margin, logo.banner_width)
        out.append(("banner",
                    prim.prism_from_polygons(ring, spec.base.thickness,
                                             logo.banner_height)))
    return out


def build(spec: StandSpec):
    """Return [(part_name, mesh, extruder), ...] ready for export."""
    base, grip = spec.base, spec.grip

    bar, bar_w, bar_d, _ = _mag_bar(spec)

    tower_w = grip.slot_width + 2 * grip.wall
    tower_d = grip.slot_thickness + 2 * grip.wall

    deck_w = max(bar_w, tower_w + 2 * base.margin)
    deck_d = max(base.depth, bar_d + base.gap + tower_d + 2 * base.margin)

    # The deck butts up against the back of the mag bar rather than running
    # underneath it. If it ran underneath, the union would fill the pockets up
    # to deck height and quietly make them shallower than requested.
    plate_d = deck_d - bar_d
    deck = prim.box(deck_w, base.thickness, plate_d,
                    [deck_w / 2, base.thickness / 2, bar_d + plate_d / 2])

    # mag bar sits at the front edge; tower sits behind the logo gap
    bar.apply_translation([(deck_w - bar_w) / 2, 0.0, 0.0])
    tower_cx = deck_w / 2
    tower_cz = bar_d + base.gap + tower_d / 2
    tower = _grip_tower(spec, tower_cx, tower_cz)

    body = prim.union([deck, bar, tower])

    logo_cz = bar_d + base.gap / 2
    features = _logo(spec, deck_w / 2, logo_cz)
    if features:
        body = prim.difference(body, [m for _, m in features])   # keep them separable

    parts = [("Stand", prim.check(body, "stand body"), 1)]
    for name, mesh in features:
        parts.append((f"{name} (colour 2)", prim.check(mesh, name), 2))
    return parts
