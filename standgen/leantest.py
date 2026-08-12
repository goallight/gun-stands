"""A coupon for dialling in grip tower lean angle before printing a stand.

Prints one blade per candidate angle, sized to fit inside the grip
(magazine well). Slide the grip over each blade and pick the angle
where it sits flush.

Blades are arranged front-to-back (along Z) so the sideways lean of each
blade doesn't interfere with its neighbours.
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

    # The grip width/thickness are the INSIDE dimensions (magazine well).
    # Use extra clearance so blades slide on/off easily — this test is
    # about angle, not fitment.
    test_clearance = max(grip.clearance, 1.5)
    bw = grip.width - test_clearance
    bd = grip.thickness - test_clearance
    h = 35.0                       # short blade — enough to read the angle
    base_y = spec.base.thickness

    # The lean spreads the blade in X. Size the coupon width for the worst case.
    max_lean = max(angles)
    lean_shift = h * np.sin(np.radians(max_lean))
    total_x = bw + lean_shift + 16

    # Blades front-to-back with enough gap for flared magwells
    gap = 20.0
    total_z = gap + len(angles) * (bd + gap)

    # Base plate
    base = prim.box(total_x, base_y, total_z,
                    [total_x / 2, base_y / 2, total_z / 2])

    parts = [base]
    z = gap + bd / 2
    for angle in angles:
        lean = np.radians(angle)
        cx = total_x / 2

        # Build a blade, lean it, clip below deck
        blade = prim.box(bw, h + base_y, bd, [0, (h + base_y) / 2, 0])
        section = blade

        tilt = trimesh.transformations.rotation_matrix(lean, [0, 0, 1])
        section.apply_transform(tilt)

        clip = prim.box(bw + h, h + 20, bd + h, [0, -(h + 20) / 2, 0])
        section = prim.difference(section, [clip])

        section.apply_translation([cx, 0, z])
        parts.append(section)

        # Emboss the angle label on the deck beside the blade
        glyphs = textmod.text_polygons(f"{angle:.0f}", label_size)
        placed = textmod.place(glyphs, total_x - label_size, z)
        label = prim.prism_from_polygons(placed, base_y, 1.2)
        parts.append(label)

        z += bd + gap

    coupon = prim.union(parts)
    return prim.check(coupon, "lean test coupon")
