"""Geometry regression tests.

These check the things that actually cost a failed print: pockets coming out
the wrong size, meshes that aren't solid, and logo features landing off a
layer boundary.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from standgen import build_design, fittest, load
from standgen.primitives import bad_edges

ROOT = Path(__file__).resolve().parent.parent
DESIGNS = sorted((ROOT / "designs").glob("*.yaml"))


def pocket_sections(mesh, y, lo=15.0, hi=45.0):
    """Widths/depths of pocket-sized loops at a given height."""
    sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
    if sec is None:
        return []
    out = []
    for entity in sec.entities:
        pts = sec.vertices[entity.points]
        w = pts[:, 0].max() - pts[:, 0].min()
        d = pts[:, 2].max() - pts[:, 2].min()
        if lo < w < hi and lo < d < hi:
            out.append((round(w, 3), round(d, 3)))
    return out


@pytest.mark.parametrize("design", DESIGNS, ids=lambda p: p.stem)
def test_design_loads(design):
    spec = load(design)
    assert spec.name
    assert spec.mag.count >= 1
    assert spec.mag.clearance >= 0


@pytest.mark.parametrize("design", DESIGNS, ids=lambda p: p.stem)
def test_parts_are_printable_solids(design):
    for name, mesh, extruder in build_design(load(design)):
        assert mesh.is_watertight, f"{name} is not watertight"
        assert bad_edges(mesh) == 0, f"{name} has non-manifold edges"
        assert mesh.volume > 0, f"{name} has non-positive volume"
        assert extruder in (1, 2, 3, 4)


@pytest.mark.parametrize("design", DESIGNS, ids=lambda p: p.stem)
def test_pockets_match_requested_clearance(design):
    spec = load(design)
    parts = build_design(spec)
    body = parts[0][1]

    want = (round(spec.mag.pocket_width, 3), round(spec.mag.pocket_thickness, 3))
    probe = spec.mag.floor + spec.mag.depth * 0.5
    found = pocket_sections(body, probe)

    matches = [s for s in found if abs(s[0] - want[0]) < 1e-3 and abs(s[1] - want[1]) < 1e-3]
    assert len(matches) == spec.mag.count, (
        f"expected {spec.mag.count} pockets at {want}, found {sorted(set(found))}"
    )


def count_pockets(mesh, spec, y):
    """How many loops at height y match the requested pocket size exactly."""
    want = (round(spec.mag.pocket_width, 3), round(spec.mag.pocket_thickness, 3))
    return sum(1 for w, d in pocket_sections(mesh, y)
               if abs(w - want[0]) < 1e-3 and abs(d - want[1]) < 1e-3)


@pytest.mark.parametrize("design", DESIGNS, ids=lambda p: p.stem)
def test_pocket_walls_are_parallel_top_to_bottom(design):
    """A pocket that narrows with height binds at depth even if the mouth fits.

    Counted per-pocket rather than by comparing whole slices, because other
    features (the grip slot) come and go at different heights.
    """
    spec = load(design)
    body = build_design(spec)[0][1]
    floor, depth = spec.mag.floor, spec.mag.depth

    at_floor = count_pockets(body, spec, floor + 0.5)
    at_mid = count_pockets(body, spec, floor + depth * 0.5)
    at_mouth = count_pockets(body, spec, floor + depth - spec.mag.chamfer - 0.5)

    assert at_floor == spec.mag.count, f"{at_floor} full-size pockets at the floor"
    assert at_mid == spec.mag.count, f"{at_mid} full-size pockets at mid depth"
    assert at_mouth == spec.mag.count, f"{at_mouth} full-size pockets near the mouth"


@pytest.mark.parametrize("design", DESIGNS, ids=lambda p: p.stem)
def test_logo_heights_land_on_layer_boundaries(design):
    spec = load(design)
    if not spec.logo.enabled or not spec.printing.snap_logo_to_layers:
        pytest.skip("no logo, or snapping disabled")

    lh = spec.printing.layer_height
    for value in (spec.logo.letter_height, spec.logo.banner_height):
        layers = value / lh
        assert abs(layers - round(layers)) < 1e-6, (
            f"{value} mm is {layers:.2f} layers at {lh} mm - will round down and "
            "let the base colour show through"
        )
        assert round(layers) >= 5, (
            f"{value} mm is only {round(layers)} layers; use 5+ over a dark base"
        )


@pytest.mark.parametrize("design", DESIGNS, ids=lambda p: p.stem)
def test_fit_test_coupon_is_full_depth(design):
    spec = load(design)
    coupon = fittest.build(spec)
    assert coupon.is_watertight
    assert bad_edges(coupon) == 0

    height = coupon.bounds[1][1] - coupon.bounds[0][1]
    assert abs(height - (spec.mag.floor + spec.mag.depth)) < 1e-6, (
        "coupon must be the same depth as the real stand or it will not "
        "reveal binding partway down"
    )

    probe = spec.mag.floor + spec.mag.depth * 0.5
    found = sorted(pocket_sections(coupon, probe))
    assert len(found) == len(spec.fit_test_clearances)
    for clr in spec.fit_test_clearances:
        want = (round(spec.mag.width + clr, 3), round(spec.mag.thickness + clr, 3))
        assert any(abs(f[0] - want[0]) < 1e-3 and abs(f[1] - want[1]) < 1e-3
                   for f in found), f"missing a pocket for clearance {clr}"


def test_refit_preserves_the_donor_envelope():
    """A refit must only change the pockets - never the outside of the model."""
    design = ROOT / "designs" / "walther_pdp.yaml"
    spec = load(design)
    donor = trimesh.load(spec.refit.donor, force="mesh")
    body = build_design(spec)[0][1]

    donor_size = donor.bounds[1] - donor.bounds[0]
    body_size = body.bounds[1] - body.bounds[0]
    assert np.allclose(donor_size, body_size, atol=1e-3), (
        f"envelope changed: {donor_size} -> {body_size}"
    )


@pytest.mark.parametrize("design", DESIGNS, ids=lambda p: p.stem)
def test_clearance_moves_the_pocket_the_right_way(design):
    """Guards against the clearance sign being flipped somewhere.

    Compares pocket cross-sections, not total volume: on the generator a wider
    pocket also grows the surrounding walls, so overall volume rises either way.
    """
    sizes = {}
    for clearance in (0.20, 0.80):
        spec = load(design)
        spec.mag.clearance = clearance
        body = build_design(spec)[0][1]
        probe = spec.mag.floor + spec.mag.depth * 0.5
        found = pocket_sections(body, probe)
        want = (round(spec.mag.pocket_width, 3), round(spec.mag.pocket_thickness, 3))
        assert any(abs(w - want[0]) < 1e-3 and abs(d - want[1]) < 1e-3
                   for w, d in found), f"no pocket at {want} for clearance {clearance}"
        sizes[clearance] = want

    assert sizes[0.80][0] - sizes[0.20][0] == pytest.approx(0.60, abs=1e-6)
    assert sizes[0.80][1] - sizes[0.20][1] == pytest.approx(0.60, abs=1e-6)
