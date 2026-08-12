"""A coupon for dialling in grip tower lean angle before printing a stand.

Prints one slot per candidate angle with thin walls (2 mm) so the grip
slides on easily. The test is about angle, not fitment — the walls just
need to be stiff enough to check which lean feels flush.

Towers are arranged front-to-back (along Z) so the sideways lean of each
tower doesn't interfere with its neighbours.
"""
from __future__ import annotations

import numpy as np
import trimesh

from . import primitives as prim
from . import text as textmod
from .spec import StandSpec


def build(spec: StandSpec, angles=None, label_size: float = 6.0):
    grip = spec.grip
    angles = list(angles or spec.lean_test_angles)
    if not angles:
        raise ValueError("need at least one lean angle to test")

    sw, st = grip.slot_width, grip.slot_thickness
    test_wall = 2.0                # thin walls — just enough to check angle
    w = sw + 2 * test_wall         # tower section width
    d = st + 2 * test_wall         # tower section depth
    h = 35.0                       # short tower — enough to read the angle
    base_y = spec.base.thickness

    # The lean spreads the tower in X. Size the coupon width for the worst case.
    max_lean = max(angles)
    lean_shift = h * np.sin(np.radians(max_lean))
    total_x = w + lean_shift + 12

    # Towers front-to-back with a small gap between them
    gap = 4.0
    foot_extra = 4.0               # foot overhang per side
    total_z = gap + len(angles) * (d + foot_extra + gap)

    # Base plate
    base = prim.box(total_x, base_y, total_z,
                    [total_x / 2, base_y / 2, total_z / 2])

    towers = [base]
    z = gap + (d + foot_extra) / 2
    for angle in angles:
        lean = np.radians(angle)
        cx = total_x / 2

        # Build a thin-walled tower section with foot, lean it, clip it
        foot = prim.box(w + foot_extra, base_y + 2, d + foot_extra,
                        [0, (base_y + 2) / 2, 0])
        body = prim.box(w, h, d, [0, base_y + h / 2, 0])
        slot = prim.box(sw, h + 4, st,
                        [0, base_y + h / 2, 0])
        section = prim.difference(prim.union([foot, body]), [slot])

        tilt = trimesh.transformations.rotation_matrix(lean, [0, 0, 1])
        section.apply_transform(tilt)

        clip = prim.box(w + h, h + 20, d + h, [0, -(h + 20) / 2, 0])
        section = prim.difference(section, [clip])

        section.apply_translation([cx, 0, z])
        towers.append(section)

        # Emboss the angle label on the deck beside the tower
        glyphs = textmod.text_polygons(f"{angle:.0f}", label_size)
        placed = textmod.place(glyphs, total_x - label_size, z)
        label = prim.prism_from_polygons(placed, base_y, 1.2)
        towers.append(label)

        z += d + foot_extra + gap

    coupon = prim.union(towers)
    return prim.check(coupon, "lean test coupon")
