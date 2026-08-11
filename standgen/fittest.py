"""A full-depth coupon for dialling in pocket clearance before printing a stand.

Prints one pocket per candidate clearance, at the same depth and wall
thicknesses as the real part, with the clearance embossed on the back face.
A shallow coupon will lie to you: a magazine that slides in fine for 12 mm can
still bind at 36 mm if the walls bow inward at all.
"""
from __future__ import annotations

import numpy as np

from . import primitives as prim
from . import text as textmod
from .spec import StandSpec


def build(spec: StandSpec, clearances=None, label_size: float = 8.0):
    mag = spec.mag
    clearances = list(clearances or spec.fit_test_clearances)
    if not clearances:
        raise ValueError("need at least one clearance to test")

    floor, depth, chamfer = mag.floor, mag.depth, mag.chamfer
    height = floor + depth

    widths = [mag.width + c for c in clearances]
    depths = [mag.thickness + c for c in clearances]

    end_wall = max(4.0, max(widths) * 0.14)
    mid_wall = max(6.0, max(widths) * 0.38)
    side_wall = max(4.0, max(depths) * 0.22)

    total_x = 2 * end_wall + sum(widths) + mid_wall * (len(clearances) - 1)
    total_z = max(depths) + 2 * side_wall

    body = prim.box(total_x, height, total_z, [total_x / 2, height / 2, total_z / 2])

    cutters, labels = [], []
    x = end_wall
    for clr, w, d in zip(clearances, widths, depths):
        cx, cz = x + w / 2, total_z / 2
        cutters += prim.pocket_cutters(cx, cz, w, d, floor, height, chamfer)

        glyphs = textmod.text_polygons(f"{clr:.2f}", label_size)
        bounds = np.array([g.bounds for g in glyphs])
        gx = (bounds[:, 0].min() + bounds[:, 2].max()) / 2
        gy = (bounds[:, 1].min() + bounds[:, 3].max()) / 2
        for g in glyphs:
            import trimesh
            from shapely.affinity import translate
            moved = translate(g, cx - gx, height / 2 - gy)
            emboss = trimesh.creation.extrude_polygon(moved, 1.2)
            emboss.apply_translation([0, 0, total_z - 0.4])
            labels.append(emboss)
        x += w + mid_wall

    coupon = prim.union([prim.difference(body, cutters)] + labels)
    return prim.check(coupon, "fit test coupon")
