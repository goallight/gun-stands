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
from standgen.export import write_bambu_3mf, write_stl
from standgen.primitives import bad_edges


def report(label: str, mesh: trimesh.Trimesh) -> None:
    size = mesh.bounds[1] - mesh.bounds[0]
    flag = "ok" if mesh.is_watertight and bad_edges(mesh) == 0 else "CHECK"
    print(f"    {label:<24} {size[0]:7.2f} x {size[1]:6.2f} x {size[2]:6.2f} mm  "
          f"{mesh.volume/1000:7.1f} cm3  {len(mesh.faces):6d} tris  [{flag}]")


def build_one(design: Path, outdir: Path, fit_test: bool, bed) -> int:
    spec = load(design)
    target = outdir / spec.name
    target.mkdir(parents=True, exist_ok=True)
    print(f"\n{spec.name}  ({spec.mode})")
    print(f"    magazine {spec.mag.width} x {spec.mag.thickness} mm, "
          f"clearance {spec.mag.clearance} -> pocket "
          f"{spec.mag.pocket_width:.2f} x {spec.mag.pocket_thickness:.2f} mm")

    problems = 0
    if fit_test:
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
            problems += build_one(design, outdir, args.fit_test, bed)
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
