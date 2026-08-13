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

python build.py specs/walther_pdp.yaml            # STLs + .3mf into builds/
python build.py specs/walther_pdp.yaml --fit-test  # clearance coupon
python build.py specs/glock19.yaml --lean-test     # grip angle coupon
python build.py specs/sig_p365x.yaml --preview     # build + top-down PNG
python build.py --all                                # everything in specs/
```

## The clearance workflow

This is the part worth being disciplined about. Pocket fit is the whole design.

1. Measure the magazine cross-section with calipers. Put it in `mag.width`
   (long dimension) and `mag.thickness` (short one).
2. `python build.py specs/yours.yaml --fit-test` and print the coupon.
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

## The grip angle workflow

The grip tower lean angle matters as much as pocket clearance. Every pistol
has a different grip angle, and guessing from spec sheets doesn't work — the
stand slot lean depends on how the gun actually rests, not just the number on
paper.

1. `python build.py specs/yours.yaml --lean-test` and print the coupon.
   It carries one slot per candidate angle (default 10, 13, 16, 19, 22
   degrees), each labeled on the back face.
2. Drop the grip into each slot and pick the angle where it sits flush with
   the most contact.
3. Put that number in `grip.lean` and build the stand.

`lean_test_angles` in the YAML controls which angles the coupon includes.

## Image logos

Logos can be either text strings or image files. Text logos use
`logo.text` and `logo.size` (cap height). Image logos use `logo.image`
(path to an image — PNG, JPEG, etc.) and `logo.size` (target width in mm).

Dark pixels become solid geometry; light pixels become background. The image
is traced into vector contours and extruded onto the deck as a separate colour
body, same as text logos.

Tips for image logos:
- Crop the image tight to the logo. Whitespace or small distant features
  (like a registered trademark symbol) stretch the bounding box and shrink
  the actual logo.
- For transparent PNGs, convert to a white background first, or the tracer
  may pick up gray from the alpha channel.

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

## Grip tower options

Generated stands build a grip tower from the `grip` measurements. Two extra
options control the layout:

- **`grip.align`** — `center` (default), `left`, or `right`. Shifts the tower
  to one side of the deck, leaving room for the logo beside it.
- **`grip.tower`** — path to an STL to use instead of generating a tower. The
  STL should be centred at X=0, Y=0 at the base, Z=0 centred. Use this to
  reuse a known-good tower shape across designs (e.g. the Walther tower works
  for the P365X).

## Slicer notes

`builds/<name>/<name>.3mf` opens in Bambu Studio or OrcaSlicer as **one object
with named parts**, filaments already assigned, oriented flat on the bed.

Generic 3MF exporters do not do this — Bambu reads them as plain geometry and
flattens every part into a single object. `standgen/export.py` writes Bambu's
own structure instead: one mesh object per part, an assembly object built from
components, and a `Metadata/model_settings.config` naming each part and its
extruder.

If you'd rather assemble by hand: load `<name>_stand.stl`, right-click the
object, **Add part → Load**, and pick the logo STL. They share an origin, so it
drops into place.

## Preview

`--preview` generates a top-down PNG alongside the STLs, showing the stand
layout with the logo highlighted. Useful for checking placement before
printing.

## Designs

| File | Mode | Notes |
|---|---|---|
| `specs/walther_pdp.yaml` | refit | Verified against a printed part. 0.25 mm clearance. Needs a donor (below). |
| `specs/sig_p365x.yaml` | generate | Verified. 0.25 mm clearance. Uses Walther donor grip tower. SIG brand mark logo. |
| `specs/glock19.yaml` | generate | Verified. 0.25 mm mag clearance, 16° lean. Glock logo. |
| `specs/sw_bodyguard_2.yaml` | generate | S&W Bodyguard 2.0 (.380 ACP). S&W logo. Verify clearance with coupon. |
| `specs/glock19_example.yaml` | generate | **Placeholder numbers.** Measure before printing. |

Adding a gun is a new YAML in `specs/`. Nothing else needs to change.

### Donor STLs are not in the repo

`donors/` is gitignored — donor models are third-party and usually can't be
redistributed. So a fresh clone can't build refit designs until you supply the
mesh yourself:

```
donors/PDP_Stand_V1.stl      <- drop your own copy here
```

Without it, `build.py` prints `skipped - donor STL not present` and moves on,
and the donor-dependent tests skip rather than fail. That keeps CI green on a
clone while still exercising the generator, the coupon builder, and every
design that doesn't need a donor. Generated designs are unaffected, and
`--fit-test` and `--lean-test` work for every design regardless, since coupons
are built from measurements alone.

## Repo layout

```
build.py               CLI
standgen/
  spec.py              YAML -> dataclasses, layer snapping
  primitives.py        boxes, chamfer cutters, ring nesting, solidity checks
  refit.py             pocket detection, pocket resizing, logo splitting
  pipeline.py          mode dispatcher (generate vs refit)
  generate.py          from-scratch stand (with lean + alignment support)
  fittest.py           clearance coupon
  leantest.py          grip angle coupon
  text.py              glyph outlines, banner rings, and image logo tracing
  export.py            STL + Bambu 3MF writer
specs/                 one YAML per gun
donors/                donor STLs for refit designs (gitignored)
logos/                 logo images for image-based logos
parts/                 derived geometry (e.g. extracted grip towers)
docs/                  design notes and session logs
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

- Pocket detection assumes axis-aligned rectangular pockets with vertical
  walls. If it misses, list them explicitly under `refit.pockets`.
- Image logo tracing works best with clean, high-contrast images. Noisy or
  low-resolution images may produce ragged contours.
