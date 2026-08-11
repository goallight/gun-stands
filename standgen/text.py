"""Text and banner outlines for the deck logo."""
from __future__ import annotations

import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
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
