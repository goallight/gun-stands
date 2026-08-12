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
    """A leaning blade the grip slides over.

    The blade is sized to the inside grip dimensions (magazine well) minus
    clearance. The entire tower leans sideways at `grip.lean` degrees so
    the pistol sits at its natural grip angle. The base is clipped flat.
    """
    grip = spec.grip
    # Blade fits INSIDE the grip — subtract clearance from inside dimensions
    bw = grip.width - grip.clearance
    bd = grip.thickness - grip.clearance
    h = grip.height
    lean = np.radians(grip.lean)
    base_y = spec.base.thickness

    # Build the blade with a wider foot at the origin, then lean the whole
    # thing together so the foot transitions flush into the leaned blade.
    foot_extra = 6.0
    foot = prim.box(bw + foot_extra, base_y + 4, bd + foot_extra,
                    [0, (base_y + 4) / 2, 0])
    blade = prim.box(bw, h, bd, [0, base_y + h / 2, 0])
    tower = prim.union([foot, blade])

    # Lean the tower sideways (rotate about Z axis at the base) so the
    # blade matches the pistol's natural grip angle. Positive lean
    # tilts the top to the left (-X) when viewed from the front.
    tilt = trimesh.transformations.rotation_matrix(lean, [0, 0, 1])
    tower.apply_transform(tilt)

    # Clip off anything below y=0 so the base sits flat on the deck
    clip = prim.box(bw + h, h + 20, bd + h, [0, -(h + 20) / 2, 0])
    tower = prim.difference(tower, [clip])

    # Move to final position on the deck
    tower.apply_translation([cx, 0, cz])

    return tower


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

    if logo.image:
        glyphs = textmod.image_polygons(logo.image, logo.size)
    elif logo.text:
        glyphs = textmod.text_polygons(logo.text, logo.size)
    else:
        glyphs = []
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

    # Determine tower dimensions — from donor STL or from grip measurements
    if grip.tower:
        donor_tower = trimesh.load(grip.tower)
        tower_w = donor_tower.extents[0]
        tower_d = donor_tower.extents[2]
    else:
        donor_tower = None
        # Blade fits inside the grip; foot adds extra around the base
        tower_w = grip.width - grip.clearance + 6
        tower_d = grip.thickness - grip.clearance + 6

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

    # grip tower X position depends on alignment
    if grip.align == "right":
        tower_cx = deck_w - tower_w / 2 - base.margin
    elif grip.align == "left":
        tower_cx = tower_w / 2 + base.margin
    else:
        tower_cx = deck_w / 2

    tower_cz = bar_d + base.gap + tower_d / 2

    if donor_tower is not None:
        # Donor tower is centred at X=0, Y starts at 0, Z centred at 0.
        donor_tower.apply_translation([tower_cx, 0.0, tower_cz])
        tower = donor_tower
    else:
        tower = _grip_tower(spec, tower_cx, tower_cz)

    body = prim.union([deck, bar, tower])

    # logo placement: beside the tower when aligned, or centred in the gap
    logo_cz = bar_d + (base.gap + tower_d) / 2
    if grip.align == "right":
        logo_cx = (tower_cx - tower_w / 2) / 2  # centred in the space left of the tower
    elif grip.align == "left":
        logo_cx = (tower_cx + deck_w) / 2  # right half
    else:
        logo_cx = deck_w / 2
    features = _logo(spec, logo_cx, logo_cz)
    if features:
        body = prim.difference(body, [m for _, m in features])   # keep them separable

    parts = [("Stand", prim.check(body, "stand body"), 1)]
    for name, mesh in features:
        parts.append((f"{name} (colour 2)", prim.check(mesh, name), 2))
    return parts
