"""Reshape magazine pockets on an existing (donor) STL.

This is the path that keeps a model you already like pixel-identical everywhere
except the pockets. It also knows how to peel raised logo features off the deck
so they can be printed in a second colour.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from shapely.geometry import MultiLineString, Polygon
from shapely.ops import polygonize, unary_union

from . import primitives as prim


@dataclass
class Pocket:
    """An axis-aligned, upward-opening rectangular cavity."""
    x0: float
    x1: float
    z0: float
    z1: float
    floor: float
    mouth: float

    @property
    def center(self):
        return ((self.x0 + self.x1) / 2, (self.z0 + self.z1) / 2)

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def depth(self):
        return self.z1 - self.z0

    def __repr__(self):
        return (f"Pocket({self.width:.3f} x {self.depth:.3f} mm, "
                f"y {self.floor:.2f}..{self.mouth:.2f})")


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------

def detect_pockets(mesh: trimesh.Trimesh, min_area: float = 150.0,
                   samples: int = 25, rect_tol: float = 0.03) -> list[Pocket]:
    """Find rectangular, vertical-walled pockets that open upward.

    Works by slicing horizontally, keeping loops that are (a) rectangles and
    (b) enclosed by another loop in the same slice, then tracking the height
    range over which each one survives.
    """
    lo, hi = mesh.bounds[0][1], mesh.bounds[1][1]
    heights = np.linspace(lo + (hi - lo) * 0.02, hi - (hi - lo) * 0.02, samples)

    # a real pocket has material on all four sides, so it never reaches the
    # model's own XZ footprint - this is what rules out the mag bar itself
    bx0, bz0 = mesh.bounds[0][0], mesh.bounds[0][2]
    bx1, bz1 = mesh.bounds[1][0], mesh.bounds[1][2]
    margin = 0.5

    seen: dict[tuple, list[float]] = {}
    for y in heights:
        sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec is None:
            continue
        loops = []
        for entity in sec.entities:
            pts = sec.vertices[entity.points][:, [0, 2]]
            if len(pts) < 4:
                continue
            poly = Polygon(pts).buffer(0)
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
            loops.append(poly)

        for poly in loops:
            x0, z0, x1, z1 = poly.bounds
            w, d = x1 - x0, z1 - z0
            if w * d < min_area:
                continue
            if abs(poly.area - w * d) > rect_tol * w * d:      # not a rectangle
                continue
            if (x0 - bx0 < margin or z0 - bz0 < margin
                    or bx1 - x1 < margin or bz1 - z1 < margin):
                continue                                        # touches the footprint
            pt = poly.representative_point()
            if not any(o is not poly and o.contains(pt) for o in loops):
                continue                                        # not enclosed -> outer wall
            key = (round(x0, 3), round(z0, 3), round(x1, 3), round(z1, 3))
            seen.setdefault(key, []).append(float(y))

    pockets = []
    for (x0, z0, x1, z1), ys in seen.items():
        if len(ys) < 2:
            continue
        pockets.append(Pocket(x0, x1, z0, z1,
                              floor=_pocket_floor(mesh, x0, x1, z0, z1, min(ys)),
                              mouth=_pocket_mouth(mesh, x0, x1, z0, z1, max(ys))))
    pockets.sort(key=lambda p: p.x0)
    return pockets


def _pocket_floor(mesh, x0, x1, z0, z1, y_hint) -> float:
    """Highest upward-facing face inside the footprint below y_hint."""
    tv = mesh.vertices[mesh.faces]
    up = mesh.face_normals[:, 1] > 0.999
    cx, cz = tv[:, :, 0].mean(axis=1), tv[:, :, 2].mean(axis=1)
    inside = (cx > x0) & (cx < x1) & (cz > z0) & (cz < z1)
    ys = tv[:, :, 1].mean(axis=1)
    sel = up & inside & (ys <= y_hint + 1e-6)
    return float(ys[sel].max()) if sel.any() else float(mesh.bounds[0][1])


def _pocket_mouth(mesh, x0, x1, z0, z1, y_hint) -> float:
    """Lowest upward-facing face just outside the footprint above y_hint."""
    tv = mesh.vertices[mesh.faces]
    up = mesh.face_normals[:, 1] > 0.999
    cx, cz = tv[:, :, 0].mean(axis=1), tv[:, :, 2].mean(axis=1)
    near = ((cx > x0 - 6) & (cx < x1 + 6) & (cz > z0 - 6) & (cz < z1 + 6)
            & ~((cx > x0) & (cx < x1) & (cz > z0) & (cz < z1)))
    ys = tv[:, :, 1].mean(axis=1)
    sel = up & near & (ys >= y_hint - 1e-6)
    return float(ys[sel].min()) if sel.any() else float(mesh.bounds[1][1])


# ---------------------------------------------------------------------------
# resizing
# ---------------------------------------------------------------------------

def resize_pockets(mesh: trimesh.Trimesh, pockets: list[Pocket],
                   width: float, depth: float, chamfer: float = 1.0,
                   grow: float = 3.0) -> trimesh.Trimesh:
    """Fill the old pockets solid, then cut new ones at the given size.

    `grow` oversizes the fill blocks so the union seam falls inside existing
    material. Without it the seam sits exactly where the new chamfer crosses
    the old wall and the boolean leaves slivers.
    """
    fills = []
    for p in pockets:
        cx, cz = p.center
        fills.append(prim.box(p.width + grow, p.mouth - p.floor, p.depth + grow,
                              [cx, (p.floor + p.mouth) / 2, cz]))
    solid = prim.union([mesh] + fills)

    cutters = []
    for p in pockets:
        cx, cz = p.center
        cutters += prim.pocket_cutters(cx, cz, width, depth, p.floor, p.mouth, chamfer)

    return prim.check(prim.difference(solid, cutters), "refit body")


# ---------------------------------------------------------------------------
# raised deck features (logo) -> separate colour bodies
# ---------------------------------------------------------------------------

def find_deck_height(mesh: trimesh.Trimesh, region) -> float:
    """Largest upward-facing plane inside the region: that's the deck."""
    x0, x1, z0, z1 = region
    tv = mesh.vertices[mesh.faces]
    up = mesh.face_normals[:, 1] > 0.999
    cx, cz = tv[:, :, 0].mean(axis=1), tv[:, :, 2].mean(axis=1)
    inside = up & (cx > x0) & (cx < x1) & (cz > z0) & (cz < z1)
    if not inside.any():
        raise ValueError("no upward-facing geometry in the logo region")
    ys = np.round(tv[inside][:, :, 1].mean(axis=1), 3)
    areas = mesh.area_faces[inside]
    planes, idx = np.unique(ys, return_inverse=True)
    totals = np.bincount(idx, weights=areas)
    return float(planes[int(totals.argmax())])


def split_raised(mesh: trimesh.Trimesh, region, deck: float,
                 heights: dict[float, float] | None = None):
    """Separate raised features on the deck from the body underneath.

    Returns (body, features) where `features` is a list of (mesh, top_height).
    `heights` optionally remaps an existing feature height to a new one, which
    is how the logo gets taller without changing its footprint.
    """
    x0, x1, z0, z1 = region
    V, F = mesh.vertices, mesh.faces
    tv = V[F]

    in_region = ((tv[:, :, 0] > x0).all(1) & (tv[:, :, 0] < x1).all(1)
                 & (tv[:, :, 2] > z0).all(1) & (tv[:, :, 2] < z1).all(1))
    raised = in_region & (tv[:, :, 1] >= deck - 1e-3).all(1) & (tv[:, :, 1].max(1) > deck + 1e-3)
    if not raised.any():
        return mesh, []

    # distinct top planes of the raised features
    up = mesh.face_normals[:, 1] > 0.999
    tops = np.unique(np.round(tv[raised & up][:, :, 1].mean(axis=1), 3))
    tops = tops[tops > deck + 1e-3]

    # footprint of everything raised, used to tell solid from open deck below
    footprint = unary_union([Polygon(t[:, [0, 2]]).buffer(1e-6)
                             for t in tv[raised & up] if abs(t[:, 1].mean() - deck) > 1e-3])

    # boundary of the removed patch, on the deck plane -> holes needing a cap
    edge_count: dict[tuple[int, int], int] = {}
    for f in F[raised]:
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            key = (min(a, b), max(a, b))
            edge_count[key] = edge_count.get(key, 0) + 1
    border = [k for k, c in edge_count.items() if c == 1
              and abs(V[k[0], 1] - deck) < 1e-4 and abs(V[k[1], 1] - deck) < 1e-4]

    segments = [((V[a, 0], V[a, 2]), (V[b, 0], V[b, 2])) for a, b in border]
    faces_2d = [p for p in polygonize(MultiLineString(segments))
                if footprint.contains(p.representative_point())]

    cap_v: list[list[float]] = []
    cap_f: list[list[int]] = []
    for poly in faces_2d:
        vv, ff = trimesh.creation.triangulate_polygon(poly, engine="earcut")
        base = len(cap_v)
        cap_v += [[q[0], deck, q[1]] for q in vv]
        cap_f += [[base + a, base + c, base + b] for a, b, c in ff]

    body = trimesh.Trimesh(vertices=V, faces=F[~raised], process=False)
    if cap_f:
        cap = trimesh.Trimesh(vertices=np.array(cap_v), faces=np.array(cap_f), process=False)
        if cap.face_normals[:, 1].mean() < 0:
            cap.invert()
        body = trimesh.util.concatenate([body, cap])
    body.merge_vertices()
    body.remove_unreferenced_vertices()
    prim.check(body, "refit body after logo split")

    # Rebuild each feature as a clean prism so its height is trivially editable.
    # A feature topping out at `top` is present just below that plane and gone
    # just above it, so set-differencing the two slices isolates it exactly.
    eps = min(0.05, (min(np.diff(tops)) / 4) if len(tops) > 1 else 0.05)
    key = lambda r: (round(r[:, 0].min(), 2), round(r[:, 0].max(), 2),
                     round(r[:, 1].min(), 2), round(r[:, 1].max(), 2))

    features = []
    for top in tops:
        below = prim.section_rings(mesh, top - eps, bounds=region, negate_z=True)
        above = prim.section_rings(mesh, top + eps, bounds=region, negate_z=True)
        gone = {key(r) for r in above}
        mine = [r for r in below if key(r) not in gone]
        if not mine:
            continue

        height = (heights or {}).get(round(float(top), 3), float(top) - deck)
        feat = prim.prism_from_polygons(prim.nest_rings(mine), deck, height)
        feat.merge_vertices()
        features.append((prim.check(feat, f"raised feature @{top}"), deck + height))

    return body, features
