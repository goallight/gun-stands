"""Small geometry helpers shared by the generator and the refit tool.

Everything here works in a Y-up coordinate system (matching the donor STLs
this project started from). Conversion to Z-up happens once, in export.py.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union

# manifold3d is what actually performs the booleans; fail loudly and early
try:  # pragma: no cover - import guard
    import manifold3d  # noqa: F401
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "manifold3d is required for boolean operations. pip install manifold3d"
    ) from exc


def box(width: float, height: float, depth: float, center) -> trimesh.Trimesh:
    """Axis-aligned box: width along X, height along Y, depth along Z."""
    b = trimesh.creation.box(extents=[width, height, depth])
    b.apply_translation(np.asarray(center, dtype=float))
    return b


def chamfer_cutter(cx: float, cz: float, width: float, depth: float,
                   mouth_y: float, chamfer: float,
                   overshoot: float = 2.0) -> trimesh.Trimesh:
    """A frustum that cuts a 45 degree lead-in at the mouth of a pocket.

    Opens outward going up, and extends past the mouth so the boolean is clean.
    """
    levels = [
        (width / 2, depth / 2, mouth_y - chamfer),
        (width / 2 + chamfer, depth / 2 + chamfer, mouth_y),
        (width / 2 + chamfer + overshoot, depth / 2 + chamfer + overshoot,
         mouth_y + overshoot),
    ]
    verts: list[list[float]] = []
    for hx, hz, y in levels:
        verts += [[cx - hx, y, cz - hz], [cx + hx, y, cz - hz],
                  [cx + hx, y, cz + hz], [cx - hx, y, cz + hz]]

    faces: list[list[int]] = []
    for level in range(2):
        a, b = level * 4, level * 4 + 4
        for k in range(4):
            j = (k + 1) % 4
            faces += [[a + k, a + j, b + j], [a + k, b + j, b + k]]
    faces += [[0, 2, 1], [0, 3, 2], [8, 9, 10], [8, 10, 11]]

    mesh = trimesh.Trimesh(vertices=np.array(verts, dtype=float),
                           faces=np.array(faces))
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def pocket_cutters(cx: float, cz: float, width: float, depth: float,
                   floor_y: float, mouth_y: float,
                   chamfer: float) -> list[trimesh.Trimesh]:
    """Prism + chamfer that together cut one magazine pocket."""
    height = (mouth_y - floor_y) + 2.0     # overshoot above the mouth
    prism = box(width, height, depth, [cx, floor_y + height / 2, cz])
    out = [prism]
    if chamfer > 0:
        out.append(chamfer_cutter(cx, cz, width, depth, mouth_y, chamfer))
    return out


def prism_from_polygons(polys, base_y: float, height: float) -> trimesh.Trimesh:
    """Extrude shapely polygons (in the XZ plane) upward from base_y.

    Polygons are given in (x, -z) so that the rotation below restores +Z.
    """
    rot = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
    parts = []
    for poly in polys:
        solid = trimesh.creation.extrude_polygon(poly, height)
        solid.apply_transform(rot)
        solid.apply_translation([0, base_y, 0])
        parts.append(solid)
    if not parts:
        raise ValueError("no polygons to extrude")
    return trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]


def nest_rings(rings) -> list[Polygon]:
    """Turn a flat list of rings into polygons with the right holes.

    Uses containment depth: even depth is a shell, odd depth is a hole in the
    shell that encloses it. This is what keeps the counters in 'A' and 'R' open
    and stops letters inside a banner from being treated as holes of the banner.
    """
    polys = [Polygon(np.asarray(r)).buffer(0) for r in rings]
    polys = [p for p in polys if p.area > 1e-9]
    polys.sort(key=lambda g: -g.area)

    # Nesting is decided by whole-polygon containment, not by testing a point
    # inside the fill. For a ribbon (an outer ring plus an inner ring) the fill
    # point of the outer polygon also lands inside the inner one, which would
    # make each look nested in the other and drop both.
    depth = [sum(1 for j, q in enumerate(polys) if j != i and q.contains(g))
             for i, g in enumerate(polys)]

    out: list[Polygon] = []
    for i, g in enumerate(polys):
        if depth[i] % 2:
            continue                       # this ring is a hole, not a shell
        holes = [np.array(q.exterior.coords)
                 for j, q in enumerate(polys)
                 if j != i and depth[j] == depth[i] + 1 and g.contains(q)]
        out.append(Polygon(np.array(g.exterior.coords), holes))
    return out


def section_rings(mesh: trimesh.Trimesh, y: float, bounds=None,
                  negate_z: bool = False):
    """Closed loops where a horizontal plane cuts the mesh, as (x, z) arrays.

    bounds, if given, is [x0, x1, z0, z1] and filters to loops inside it.
    """
    sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
    if sec is None:
        return []
    rings = []
    for entity in sec.entities:
        pts = sec.vertices[entity.points]
        if bounds is not None:
            x0, x1, z0, z1 = bounds
            if not (pts[:, 0].min() >= x0 and pts[:, 0].max() <= x1
                    and pts[:, 2].min() >= z0 and pts[:, 2].max() <= z1):
                continue
        z = -pts[:, 2] if negate_z else pts[:, 2]
        rings.append(np.column_stack([pts[:, 0], z]))
    return rings


def difference(base: trimesh.Trimesh, cutters) -> trimesh.Trimesh:
    return trimesh.boolean.difference([base] + list(cutters))


def union(meshes) -> trimesh.Trimesh:
    meshes = list(meshes)
    return meshes[0] if len(meshes) == 1 else trimesh.boolean.union(meshes)


def check(mesh: trimesh.Trimesh, label: str = "mesh") -> trimesh.Trimesh:
    """Raise if a mesh isn't printable. Cheap insurance against silent breakage."""
    if not mesh.is_watertight:
        raise ValueError(f"{label} is not watertight")
    if mesh.volume <= 0:
        raise ValueError(f"{label} has non-positive volume ({mesh.volume:.3f})")
    return mesh


def bad_edges(mesh: trimesh.Trimesh) -> int:
    """Count edges not shared by exactly two faces (0 for a clean solid)."""
    edges = np.sort(mesh.edges_sorted, axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int((counts != 2).sum())
