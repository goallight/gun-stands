# gun-stands

Parametric 3D-printable pistol stands. Designs live in YAML, geometry lives in
Python, and the build spits out STLs plus a Bambu Studio project file with the
two-colour parts already assigned.

Two ways to make a stand:

- **refit** — take a stand model you already like and recut the magazine
  pockets to fit your mags. Everything outside the pockets stays untouched.
- **generate** — build a stand from measurements alone, no donor model.

```bash
pip install -r requirements.txt

python build.py designs/walther_pdp.yaml            # STLs + .3mf into out/
python build.py designs/walther_pdp.yaml --fit-test # clearance coupon
python build.py --all                               # everything in designs/
```

## The clearance workflow

This is the part worth being disciplined about. Pocket fit is the whole design.

1. Measure the magazine cross-section with calipers. Put it in `mag.width`
   (long dimension) and `mag.thickness` (short one).
2. `python build.py designs/yours.yaml --fit-test` and print the coupon.
   It carries one pocket per candidate clearance, at **full depth** and with
   the same wall thicknesses as the real stand.
3. Drop a mag in each pocket, pick the one you like, put that number in
   `mag.clearance`, and build the stand.

`clearance` is the **total** added to the pocket, split evenly between the two
sides. `0.25` means 0.125 mm per side. Reference points from the Walther PDP:

| Clearance | Feel |
|---|---|
| 0.25 | snug, very little play — what the PDP shipped with |
| 0.40 | drops in with light guidance |
| 0.60 | easy one-handed drop-in, slight wobble |

Print the coupon with the exact filament and profile you'll use for the stand.
A different spool or a flow tweak can eat 0.125 mm of clearance on its own.

## Two-colour logos

`logo.letter_height` and `logo.banner_height` are how far the lettering stands
off the deck. They matter more than they look: over a dark base colour, four
layers of a light filament still lets black telegraph through. Five is a
minimum and eight is comfortable.

`printing.snap_logo_to_layers` rounds both heights to whole layers at your
`layer_height`, so 1.6 mm stays 8 layers instead of silently becoming 4.5 and
rounding down. A test enforces this.

Purge volume matters as much as height. Light-onto-dark is the worst-case
flush direction; under ~250 mm³ the first layers stay tinted no matter how
tall the feature is.

## Slicer notes

`out/<name>/<name>.3mf` opens in Bambu Studio or OrcaSlicer as **one object
with named parts**, filaments already assigned, oriented flat on the bed.

Generic 3MF exporters do not do this — Bambu reads them as plain geometry and
flattens every part into a single object. `standgen/export.py` writes Bambu's
own structure instead: one mesh object per part, an assembly object built from
components, and a `Metadata/model_settings.config` naming each part and its
extruder.

If you'd rather assemble by hand: load `<name>_stand.stl`, right-click the
object, **Add part → Load**, and pick the logo STL. They share an origin, so it
drops into place.

## Designs

| File | Mode | Notes |
|---|---|---|
| `designs/walther_pdp.yaml` | refit | Verified against a printed part. 0.25 mm clearance. Needs a donor (below). |
| `designs/glock19_example.yaml` | generate | **Placeholder numbers.** Measure before printing. |

Adding a gun is a new YAML in `designs/`. Nothing else needs to change.

### Donor STLs are not in the repo

`donors/*.stl` is gitignored — donor models are third-party and usually can't
be redistributed. So a fresh clone can't build refit designs until you supply
the mesh yourself:

```
donors/PDP_Stand_V1.stl      <- drop your own copy here
```

Without it, `build.py` prints `skipped - donor STL not present` and moves on,
and the donor-dependent tests skip rather than fail. That keeps CI green on a
clone while still exercising the generator, the coupon builder, and every
design that doesn't need a donor. Generated designs are unaffected, and
`--fit-test` works for every design regardless, since a coupon is built from
measurements alone.

## Repo layout

```
build.py               CLI
standgen/
  spec.py              YAML -> dataclasses, layer snapping
  primitives.py        boxes, chamfer cutters, ring nesting, solidity checks
  refit.py             pocket detection, pocket resizing, logo splitting
  generate.py          from-scratch stand
  fittest.py           clearance coupon
  text.py              glyph outlines and banner rings
  export.py            STL + Bambu 3MF writer
designs/               one YAML per gun
donors/                donor STLs for refit designs
tests/                 geometry regressions
```

## Tests

```bash
python -m pytest tests/ -q
```

They check the things that cost a failed print: pockets at the requested size,
walls parallel from floor to mouth, every part a watertight manifold with zero
bad edges, logo heights on layer boundaries, coupons at full depth, and a
refit never changing the donor's outside envelope.

CI runs the same suite on every push and uploads the built STLs and 3MFs as
artifacts, so a green run means printable files are one click away.

## Known rough edges

- The generated grip tower is a tapered blade with a straight slot. It holds a
  pistol, but it has none of the contouring a hand-modelled stand has. The
  refit path is the one to use when a good donor model exists.
- Pocket detection assumes axis-aligned rectangular pockets with vertical
  walls. If it misses, list them explicitly under `refit.pockets`.
- `donors/` contains third-party models. Check their licence before pushing
  this repo public.
