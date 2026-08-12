#!/usr/bin/env python3
"""Build stands and fit-test coupons from design files.

    python build.py designs/walther_pdp.yaml
    python build.py designs/walther_pdp.yaml --fit-test
    python build.py --all -o out/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import trimesh

from standgen import build_design, load
from standgen import fittest
from standgen import leantest
from standgen.export import write_bambu_3mf, write_stl
from standgen.primitives import bad_edges
from standgen.spec import DonorMissing, donor_available


def report(label: str, mesh: trimesh.Trimesh) -> None:
    size = mesh.bounds[1] - mesh.bounds[0]
    flag = "ok" if mesh.is_watertight and bad_edges(mesh) == 0 else "CHECK"
    print(f"    {label:<24} {size[0]:7.2f} x {size[1]:6.2f} x {size[2]:6.2f} mm  "
          f"{mesh.volume/1000:7.1f} cm3  {len(mesh.faces):6d} tris  [{flag}]")


def render_preview(parts, outpath: Path) -> None:
    """Top-down PNG preview with logo highlighted."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPatch
    from matplotlib.collections import PatchCollection

    colours = {1: "#707070", 2: "#e8c840"}
    has_logo = any(ext == 2 for _, _, ext in parts)
    ncols = 2 if has_logo else 1
    fig, axes = plt.subplots(1, ncols, figsize=(8 * ncols, 7))
    if ncols == 1:
        axes = [axes]

    def top_patches(mesh, color, ax):
        up = mesh.faces[mesh.face_normals[:, 1] > 0.5]
        patches = [MPatch(mesh.vertices[f][:, [0, 2]], closed=True) for f in up]
        ax.add_collection(PatchCollection(patches, facecolor=color,
                                          edgecolor="#555", linewidth=0.2))

    # full top-down
    for _, mesh, ext in parts:
        top_patches(mesh, colours.get(ext, "#888"), axes[0])
    all_v = parts[0][1].vertices
    axes[0].set_xlim(all_v[:, 0].min() - 2, all_v[:, 0].max() + 2)
    axes[0].set_ylim(all_v[:, 2].min() - 2, all_v[:, 2].max() + 2)
    axes[0].set_aspect("equal")
    axes[0].invert_yaxis()
    axes[0].set_title("Top-down view")
    axes[0].set_xlabel("mm")
    axes[0].set_ylabel("mm")

    # logo close-up
    if has_logo:
        for _, mesh, ext in parts:
            top_patches(mesh, colours.get(ext, "#888"), axes[1])
        logo_mesh = [m for _, m, e in parts if e == 2][0]
        lc = logo_mesh.vertices.mean(0)
        span = max(12, (logo_mesh.bounds[1] - logo_mesh.bounds[0]).max() * 0.8)
        axes[1].set_xlim(lc[0] - span, lc[0] + span)
        axes[1].set_ylim(lc[2] - span, lc[2] + span)
        axes[1].set_aspect("equal")
        axes[1].invert_yaxis()
        axes[1].set_title("Logo close-up")
        axes[1].set_xlabel("mm")

    fig.patch.set_facecolor("white")
    fig.tight_layout()
    fig.savefig(str(outpath), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"    preview -> {outpath}")


def build_one(design: Path, outdir: Path, fit_test: bool, bed,
              preview: bool = False, lean_test: bool = False) -> int:
    spec = load(design)
    print(f"\n{spec.name}  ({spec.mode})")

    # Coupons are generated from measurements alone, so they still
    # build without a donor. Only the stand itself needs one.
    if not (fit_test or lean_test) and not donor_available(spec):
        print(f"    skipped - donor STL not present ({spec.refit.donor})")
        return 0

    target = outdir / spec.name
    target.mkdir(parents=True, exist_ok=True)
    print(f"    magazine {spec.mag.width} x {spec.mag.thickness} mm, "
          f"clearance {spec.mag.clearance} -> pocket "
          f"{spec.mag.pocket_width:.2f} x {spec.mag.pocket_thickness:.2f} mm")

    problems = 0
    if lean_test:
        coupon = leantest.build(spec)
        report("lean-test coupon", coupon)
        write_stl(coupon, target / f"{spec.name}_lean_test.stl")
        problems += bad_edges(coupon)
    elif fit_test:
        coupon = fittest.build(spec)
        report("fit-test coupon", coupon)
        write_stl(coupon, target / f"{spec.name}_fit_test.stl")
        problems += bad_edges(coupon)
    else:
        parts = build_design(spec)
        for name, mesh, _ in parts:
            report(name, mesh)
            problems += bad_edges(mesh)

        for name, mesh, _ in parts:
            slug = name.split("(")[0].strip().lower().replace(" ", "_")
            write_stl(mesh, target / f"{spec.name}_{slug}.stl")

        if len(parts) > 1:
            solid = trimesh.boolean.union([m for _, m, _ in parts])
            report("single-colour solid", solid)
            write_stl(solid, target / f"{spec.name}_single.stl")

        write_bambu_3mf(parts, target / f"{spec.name}.3mf", spec.name, bed=bed)

        if preview:
            render_preview(parts, target / f"{spec.name}_preview.png")

    print(f"    -> {target}")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design", nargs="*", help="design YAML file(s)")
    ap.add_argument("--all", action="store_true", help="build everything in designs/")
    ap.add_argument("-o", "--outdir", default="out", help="output directory")
    ap.add_argument("--fit-test", action="store_true",
                    help="build the clearance coupon instead of the stand")
    ap.add_argument("--lean-test", action="store_true",
                    help="build the grip angle coupon instead of the stand")
    ap.add_argument("--preview", action="store_true",
                    help="render a top-down PNG preview of the stand")
    ap.add_argument("--bed", default="256x256", help="bed size for 3MF centring")
    args = ap.parse_args(argv)

    designs = [Path(d) for d in args.design]
    if args.all:
        designs = sorted(Path("designs").glob("*.yaml"))
    if not designs:
        ap.error("give a design file or --all")

    bed = tuple(float(v) for v in args.bed.lower().split("x"))
    outdir = Path(args.outdir)

    problems = 0
    for design in designs:
        try:
            problems += build_one(design, outdir, args.fit_test, bed,
                                  preview=args.preview,
                                  lean_test=args.lean_test)
        except DonorMissing as exc:
            print(f"\n{design}: skipped - {exc}")
        except Exception as exc:                       # noqa: BLE001
            print(f"\n{design}: FAILED - {exc}", file=sys.stderr)
            problems += 1

    if problems:
        print(f"\n{problems} problem(s) found", file=sys.stderr)
        return 1
    print("\nall good")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
