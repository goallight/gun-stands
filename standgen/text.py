"""Text and banner outlines for the deck logo."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from PIL import Image
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .primitives import nest_rings


def text_polygons(text: str, size: float, font: str = "DejaVu Sans",
                  weight: str = "bold"):
    """Glyph outlines as shapely polygons, holes intact, baseline at y=0."""
    path = TextPath((0, 0), text, size=size, prop=FontProperties(family=font, weight=weight))
    rings = [p for p in path.to_polygons() if len(p) >= 3]
    if not rings:
        raise ValueError(f"font produced no outlines for {text!r}")
    geom = unary_union(nest_rings(rings))
    return [geom] if geom.geom_type == "Polygon" else list(geom.geoms)


def image_polygons(path: str, target_width: float, threshold: int = 128):
    """Trace a PNG image into shapely polygons, scaled to *target_width* mm.

    Dark pixels become solid geometry; light pixels become background. The
    contours are extracted with contourpy and assembled into polygons with
    holes using the same nest_rings helper that text_polygons uses.
    """
    from contourpy import contour_generator

    img = Image.open(path).convert("L")
    arr = np.array(img, dtype=float)
    # invert so dark = high value (solid), then normalise to 0-1
    arr = 1.0 - arr / 255.0

    gen = contour_generator(
        z=arr,
        line_type="SeparateCode",
    )
    result = gen.lines(0.5)
    lines, codes = result

    rings = [np.asarray(line) for line in lines if len(line) >= 4]
    if not rings:
        raise ValueError(f"no contours found in {path}")

    # scale from pixel coords to mm, fitting within target_width
    all_pts = np.vstack(rings)
    px_w = all_pts[:, 0].max() - all_pts[:, 0].min()
    px_h = all_pts[:, 1].max() - all_pts[:, 1].min()
    scale = target_width / max(px_w, px_h)

    scaled = []
    x_min, x_max = all_pts[:, 0].min(), all_pts[:, 0].max()
    y_min, y_max = all_pts[:, 1].min(), all_pts[:, 1].max()
    for r in rings:
        pts = r.copy()
        pts[:, 0] = (pts[:, 0] - x_min) * scale
        pts[:, 1] = (y_max - pts[:, 1]) * scale
        scaled.append(pts)

    geom = unary_union(nest_rings(scaled))
    return [geom] if geom.geom_type == "Polygon" else list(geom.geoms)


def banner_ring(polys, margin: float, width: float):
    """A rounded outline standing off a set of polygons, as a closed ribbon."""
    hull = unary_union([p.buffer(margin, join_style=1) for p in polys])
    outer = hull.buffer(width, join_style=1)
    ring = outer.difference(hull)
    return [ring] if ring.geom_type == "Polygon" else list(ring.geoms)


def place(polys, center_x: float, center_z: float, negate_z: bool = True):
    """Centre polygons on (center_x, center_z) in the deck plane.

    Glyphs are authored in a (x, y) plane; the deck uses (x, z). With
    negate_z the result is in (x, -z), which is what prism_from_polygons wants.
    """
    bounds = unary_union(polys).bounds        # minx, miny, maxx, maxy
    dx = center_x - (bounds[0] + bounds[2]) / 2
    dy = (-center_z if negate_z else center_z) - (bounds[1] + bounds[3]) / 2

    out = []
    for p in polys:
        shell = np.array(p.exterior.coords) + [dx, dy]
        holes = [np.array(h.coords) + [dx, dy] for h in p.interiors]
        out.append(Polygon(shell, holes))
    return out
