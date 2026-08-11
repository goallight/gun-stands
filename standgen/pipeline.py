"""End-to-end refit: donor STL in, coloured parts out."""
from __future__ import annotations

import trimesh

from . import primitives as prim
from . import refit as refitmod
from .spec import StandSpec


def refit_design(spec: StandSpec):
    """Resize the donor's pockets, then peel the deck logo into its own colour."""
    cfg = spec.refit
    assert cfg is not None

    donor = trimesh.load(cfg.donor, force="mesh")
    prim.check(donor, f"donor {cfg.donor}")

    # --- pockets ---------------------------------------------------------
    if cfg.pockets:
        pockets = [refitmod.Pocket(**p) for p in cfg.pockets]
    else:
        pockets = refitmod.detect_pockets(donor)
    if not pockets:
        raise ValueError(f"no magazine pockets detected in {cfg.donor}; "
                         "list them explicitly under refit.pockets")

    body = refitmod.resize_pockets(donor, pockets,
                                   spec.mag.pocket_width,
                                   spec.mag.pocket_thickness,
                                   spec.mag.chamfer)

    # --- deck logo -------------------------------------------------------
    if not cfg.logo_region:
        return [("Stand", body, 1)]

    deck = cfg.deck_height or refitmod.find_deck_height(body, cfg.logo_region)

    # Map every existing feature height onto the requested one. The taller of
    # the two goes to banner_height, the shorter to letter_height, which keeps
    # the original design's relationship between ribbon and lettering.
    _, probe = refitmod.split_raised(body, cfg.logo_region, deck)
    tops = sorted({round(top, 3) for _, top in probe})
    remap = {}
    if len(tops) >= 2:
        remap[tops[-1]] = spec.logo.banner_height
        for t in tops[:-1]:
            remap[t] = spec.logo.letter_height
    elif tops:
        remap[tops[0]] = spec.logo.letter_height

    body, features = refitmod.split_raised(body, cfg.logo_region, deck, heights=remap)

    parts = [("Stand", prim.check(body, "refit stand"), 1)]
    if features:
        logo = trimesh.util.concatenate([m for m, _ in features])
        logo.merge_vertices()
        parts.append(("Logo (colour 2)", prim.check(logo, "logo"), 2))
    return parts
