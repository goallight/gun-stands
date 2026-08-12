"""Design specifications loaded from YAML."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MagSpec:
    """Magazine dimensions and how tightly the pocket should hold it.

    width/thickness are the *measured* magazine cross-section. The pocket is
    cut at (width + clearance) x (thickness + clearance), i.e. `clearance` is
    the TOTAL added, split evenly between the two sides.
    """

    width: float                 # long dimension of the mag cross-section, mm
    thickness: float             # short dimension, mm
    count: int = 3               # number of pockets
    clearance: float = 0.25      # total, mm (0.125 per side)
    depth: float = 36.0          # pocket depth below the mouth, mm
    floor: float = 4.0           # material under the pocket, mm
    chamfer: float = 1.0         # 45 deg lead-in at the mouth, mm

    @property
    def pocket_width(self) -> float:
        return self.width + self.clearance

    @property
    def pocket_thickness(self) -> float:
        return self.thickness + self.clearance

    @property
    def bar_height(self) -> float:
        return self.floor + self.depth


@dataclass
class GripSpec:
    """The slot the pistol grip wedges into."""

    width: float = 32.0          # grip front-to-back at the slot, mm
    thickness: float = 20.5      # grip side-to-side, mm
    clearance: float = 0.6       # total, mm - grips are tapered so run looser
    height: float = 56.0         # how tall the tower stands, mm
    lean: float = 2.0            # degrees the slot leans back from vertical
    wall: float = 4.0            # material around the slot, mm
    slot_depth: float = 50.0     # how deep the slot runs, mm
    align: str = "center"        # "center", "left", or "right"
    tower: str = ""              # path to an STL to use instead of generating

    @property
    def slot_width(self) -> float:
        return self.width + self.clearance

    @property
    def slot_thickness(self) -> float:
        return self.thickness + self.clearance


@dataclass
class BaseSpec:
    thickness: float = 6.0       # deck thickness, mm
    depth: float = 80.0          # front-to-back footprint, mm
    margin: float = 2.0          # deck overhang past the mag bar, mm
    gap: float = 14.5            # clear deck between mag bar and grip tower, mm


@dataclass
class LogoSpec:
    """Raised lettering on the deck, printed in a second colour."""

    text: str = ""
    image: str = ""              # path to a PNG logo image (traced to geometry)
    size: float = 9.0            # cap height (text) or target width (image), mm
    letter_height: float = 1.6   # how far letters stand off the deck, mm
    banner: bool = False         # draw a ribbon outline around the text
    banner_height: float = 2.0   # ribbon height off the deck, mm
    banner_margin: float = 3.0   # ribbon offset around the text, mm
    banner_width: float = 2.6    # ribbon line thickness, mm

    @property
    def enabled(self) -> bool:
        return bool(self.text) or bool(self.image) or self.banner


@dataclass
class PrintSpec:
    layer_height: float = 0.2
    snap_logo_to_layers: bool = True   # round logo heights to whole layers


class DonorMissing(FileNotFoundError):
    """A refit design's donor STL isn't present.

    Donor models are usually third-party and often can't be redistributed, so
    they're gitignored. Builds and tests treat this as "skip", not "fail" -
    otherwise CI goes red for everyone who doesn't own a copy.
    """


@dataclass
class RefitSpec:
    """Reshape pockets on an existing donor STL instead of generating one."""

    donor: str                        # path to the donor STL
    pockets: list[dict] = field(default_factory=list)  # optional manual override
    logo_region: list[float] | None = None             # [x0,x1,z0,z1] on the deck
    deck_height: float | None = None                   # deck plane, model units
    up_axis: str = "y"                                 # which axis is up in the donor


@dataclass
class StandSpec:
    name: str
    mode: str = "generate"           # "generate" or "refit"
    mag: MagSpec = field(default_factory=lambda: MagSpec(31.75, 20.45))
    grip: GripSpec = field(default_factory=GripSpec)
    base: BaseSpec = field(default_factory=BaseSpec)
    logo: LogoSpec = field(default_factory=LogoSpec)
    printing: PrintSpec = field(default_factory=PrintSpec)
    refit: RefitSpec | None = None
    fit_test_clearances: list[float] = field(default_factory=lambda: [0.25, 0.40, 0.60])
    lean_test_angles: list[float] = field(default_factory=lambda: [10, 13, 16, 19, 22])

    # ---- layer snapping -------------------------------------------------
    def snapped(self) -> "StandSpec":
        """Round logo feature heights to whole layers so light-on-dark stays opaque."""
        if not self.printing.snap_logo_to_layers or not self.logo.enabled:
            return self
        lh = self.printing.layer_height
        snap = lambda v: max(lh, round(v / lh) * lh)
        self.logo.letter_height = round(snap(self.logo.letter_height), 4)
        self.logo.banner_height = round(snap(self.logo.banner_height), 4)
        return self


def _build(cls, data: dict[str, Any] | None):
    if not data:
        return cls()
    known = {f for f in cls.__dataclass_fields__}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"{cls.__name__}: unknown key(s) {sorted(unknown)}")
    return cls(**data)


def load(path: str | Path) -> StandSpec:
    """Read a design YAML into a StandSpec."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text()) or {}

    if "name" not in raw:
        raise ValueError(f"{path}: missing required key 'name'")
    if "mag" not in raw:
        raise ValueError(f"{path}: missing required key 'mag'")

    spec = StandSpec(
        name=raw["name"],
        mode=raw.get("mode", "generate"),
        mag=_build(MagSpec, raw.get("mag")),
        grip=_build(GripSpec, raw.get("grip")),
        base=_build(BaseSpec, raw.get("base")),
        logo=_build(LogoSpec, raw.get("logo")),
        printing=_build(PrintSpec, raw.get("printing")),
        refit=_build(RefitSpec, raw["refit"]) if raw.get("refit") else None,
        fit_test_clearances=raw.get("fit_test_clearances", [0.25, 0.40, 0.60]),
    )

    if spec.mode not in ("generate", "refit"):
        raise ValueError(f"{path}: mode must be 'generate' or 'refit', got {spec.mode!r}")
    if spec.mode == "refit" and spec.refit is None:
        raise ValueError(f"{path}: mode 'refit' requires a 'refit:' block")

    # resolve the grip tower path relative to the design file
    if spec.grip.tower:
        p = Path(spec.grip.tower)
        if not p.is_absolute():
            spec.grip.tower = str((path.parent / p).resolve())

    # resolve the image path relative to the design file
    if spec.logo.image:
        p = Path(spec.logo.image)
        if not p.is_absolute():
            spec.logo.image = str((path.parent / p).resolve())

    # resolve the donor path relative to the design file
    if spec.refit:
        d = Path(spec.refit.donor)
        if not d.is_absolute():
            spec.refit.donor = str((path.parent / d).resolve())

    return spec.snapped()


def donor_available(spec: StandSpec) -> bool:
    """True if this design can actually be built here."""
    if spec.mode != "refit" or spec.refit is None:
        return True
    return Path(spec.refit.donor).is_file()
