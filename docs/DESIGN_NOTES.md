# Design notes

Everything learned building the Walther PDP stand, kept because most of it will
bite again on the next gun.

## Measured numbers

| | Value |
|---|---|
| Magazine cross-section | 31.75 × 20.45 mm |
| Donor pockets (as downloaded) | 33.00 × 22.40 mm — 1.25 / 1.95 mm of slop |
| Final pockets | 32.00 × 20.70 mm (0.25 total, 0.125 per side) |
| Pocket depth | 36 mm, floor at 4 mm, mouth at 40 mm |
| Lead-in chamfer | 1 mm at 45° |
| Deck plane | y = 6 |
| Letters | 1.6 mm proud (8 layers @ 0.2) |
| Banner ribbon | 2.0 mm proud (10 layers @ 0.2) |
| Envelope | 130 × 62.77 × 80 mm |
| Walls at 0.25 clearance | 4.50 mm ends, 12.50 mm between, 4.65 mm front/back |

## Clearance

Total, split evenly. Tested at full depth on a coupon printed with the same
filament and profile as the stand. 0.25 won; 0.40 was noticeably loose and 0.60
wobbled.

The coupon has to be **full depth**. A 12 mm test tells you nothing about
binding at 36 mm, and nothing about whether the mag bottoms out.

## Second-colour opacity

Feature height determines how many layers of the accent colour sit over the
base. Four is not enough over black — it telegraphs through. The original
design's 0.9 mm letters worked out to 4.5 layers at 0.2 mm, which rounds down
to 4.

Rule adopted: **5 layers minimum, 8 comfortable**, and heights snapped to whole
layers. `spec.py` does the snapping, `tests/test_build.py` enforces it.

Purge volume is the other half. Light-onto-dark is the worst-case flush
direction; below roughly 250 mm³ the first layers stay tinted regardless of
height.

## Boolean gotchas

**Seams from fill-then-cut.** Filling old pockets and cutting new ones leaves
the union seam exactly where the old wall was. When the new chamfer reaches
past that plane, the difference produces slivers — 2 non-manifold edges, and
0.008 mm apart, so they collapse on float32 STL export. Fix: oversize the fill
blocks (3 mm) so the seam lands inside existing material and disappears.

**float32 collapse.** Boolean output can carry vertices closer together than
float32 can resolve at these coordinates (~5 × 10⁻⁵ mm at x ≈ 400). Translating
to the origin does *not* fix it — the near-duplicates are real geometry, not
rounding. The fix is avoiding the sliver, not chasing precision.

**Prefer surgery to booleans** when the operation is topological rather than
geometric. Splitting the logo off the deck via boolean left 685 bad edges.
Deleting the raised faces and re-capping the holes with the exact existing
boundary vertices gave zero, and reused vertices merge cleanly.

## Ring nesting

Rings must be nested by **whole-polygon containment**, not by testing a fill
point. A ribbon is an outer ring plus an inner ring; the fill point of the
outer polygon also lands inside the inner one, so a point test makes each look
nested in the other and silently drops both. Cost an hour.

Depth parity does the rest: even depth is a shell, odd depth is a hole. That
keeps the counters in `A` and `R` open while stopping letters inside a banner
from being read as holes of the banner.

## Pocket detection

Slice horizontally, keep loops that are rectangles and are enclosed by another
loop in the same slice. One more filter is essential: a real pocket has
material on all four sides, so it never touches the model's own XZ footprint.
Without that, the magazine bar itself gets detected as a giant pocket.

## Bambu 3MF

A generic 3MF is not enough. Bambu reads it as plain geometry and flattens
every part into one object, so the parts and their filament assignments vanish.

What works — `standgen/export.py`:

- `3D/3dmodel.model` with one `<object>` per part, plus an assembly `<object>`
  whose `<components>` reference them
- `Metadata/model_settings.config` with a `<part>` per component, each carrying
  `name` and `extruder`
- `p:UUID` attributes and `requiredextensions="p"` on the root element
- Rotate Y-up model space to Z-up bed space and centre on the plate

Opens as one object with named parts and colours already assigned.

## Generator layout trap

The deck must butt against the back of the mag bar, not run underneath it. If
it runs underneath, the union fills the pockets up to deck height and the
pockets are quietly shallower than requested. Caught by
`test_pocket_walls_are_parallel_top_to_bottom`, not by eye.

## Checks worth keeping

Every part is verified watertight with zero non-manifold edges before it is
written. `bad_edges()` counts edges not shared by exactly two faces; a clean
solid gives 0. The refit path additionally asserts the donor's outside envelope
is unchanged — a refit should only ever touch the pockets.
