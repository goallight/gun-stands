"""A coupon for dialling in grip tower lean angle before printing a stand.

Prints one slot per candidate angle, at the same slot dimensions and wall
thicknesses as the real part, with the angle embossed on the back face.
Drop the grip into each slot and pick the one where it sits flush.
"""
from __future__ import annotations

import numpy as np
import trimesh

from . import primitives as prim
from . import text as textmod
from .spec import StandSpec


def build(spec: StandSpec, angles=None, label_size: float = 7.0):
    grip = spec.grip
    angles = list(angles or spec.lean_test_angles)
    if not angles:
        raise ValueError("need at least one lean angle to test")

    sw, st = grip.slot_width, grip.slot_thickness
    wall = grip.wall
    w = sw + 2 * wall          # tower section width
    d = st + 2 * wall          # tower section depth
    h = grip.slot_depth + 10   # tall enough to test the grip
    base_y = spec.base.thickness

    # Each test slot is a mini tower at a different lean angle
    gap = 6.0
    total_x = gap + len(angles) * (w + gap)
    # Depth needs to accommodate the most leaned tower's footprint
    max_lean = max(angles)
    lean_shift = h * np.sin(np.radians(max_lean))
    total_z = d + 2 * wall + lean_shift + 10
    total_h = base_y + h

    # Base plate
    base = prim.box(total_x, base_y, total_z,
                    [total_x / 2, base_y / 2, total_z / 2])

    towers = [base]
    x = gap + w / 2
    for angle in angles:
        lean = np.radians(angle)
        cz = total_z / 2

        # Build a small tower section at the origin
        body = prim.box(w, h, d, [0, h / 2, 0])
        slot = prim.box(sw, grip.slot_depth + 4, st,
                        [0, h + 2 - (grip.slot_depth + 4) / 2, 0])
        section = prim.difference(body, [slot])

        # Lean the whole section
        tilt = trimesh.transformations.rotation_matrix(lean, [1, 0, 0])
        section.apply_transform(tilt)

        # Clip below y=0
        clip = prim.box(w + 20, h + 20, d + h, [0, -(h + 20) / 2, 0])
        section = prim.difference(section, [clip])

        # Move to position
        section.apply_translation([x, base_y, cz])
        towers.append(section)

        # Emboss the angle label on the back face
        from shapely.affinity import translate
        glyphs = textmod.text_polygons(f"{angle:.0f}", label_size)
        bounds = np.array([g.bounds for g in glyphs])
        gx = (bounds[:, 0].min() + bounds[:, 2].max()) / 2
        gy = (bounds[:, 1].min() + bounds[:, 3].max()) / 2
        for g in glyphs:
            moved = translate(g, x - gx, base_y + h * 0.3 - gy)
            emboss = trimesh.creation.extrude_polygon(moved, 1.2)
            emboss.apply_translation([0, 0, total_z - 0.4])
            towers.append(emboss)

        x += w + gap

    coupon = prim.union(towers)
    return prim.check(coupon, "lean test coupon")
