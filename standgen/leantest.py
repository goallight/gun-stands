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
    # Use generous clearance so blades slide on/off easily — this test is
    # about angle, not fitment.
    test_clearance = max(grip.clearance, 2.5)
    bw = grip.width - test_clearance
    bd = grip.thickness - test_clearance
    h = 35.0                       # short blade — enough to read the angle
    chamfer = 3.0                  # top-edge chamfer to guide into magwell
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

        # Build a blade with a tapered tip so it guides into the magwell
        body_h = h + base_y - chamfer
        blade = prim.box(bw, body_h, bd, [0, body_h / 2, 0])
        # Tapered cap: full size at bottom, narrower at top
        tip_w, tip_d = bw - 2 * chamfer, bd - 2 * chamfer
        verts = []
        for hw, hd, y in ((bw/2, bd/2, body_h), (tip_w/2, tip_d/2, body_h + chamfer)):
            verts += [[-hw, y, -hd], [hw, y, -hd],
                      [hw, y, hd], [-hw, y, hd]]
        faces = []
        for k in range(4):
            j = (k + 1) % 4
            faces += [[k, j, 4+j], [k, 4+j, 4+k]]
        faces += [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7]]
        tip = trimesh.Trimesh(vertices=np.array(verts, dtype=float),
                              faces=np.array(faces))
        if tip.volume < 0:
            tip.invert()
        section = prim.union([blade, tip])

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
