"""Parametric pistol stands: generate from measurements, or refit a donor STL."""

from .spec import (
    BaseSpec,
    GripSpec,
    LogoSpec,
    MagSpec,
    PrintSpec,
    RefitSpec,
    StandSpec,
    load,
)

__all__ = [
    "BaseSpec", "GripSpec", "LogoSpec", "MagSpec", "PrintSpec",
    "RefitSpec", "StandSpec", "load", "build_design",
]

__version__ = "1.0.0"


def build_design(spec: StandSpec):
    """Dispatch a spec to the generator or the refit pipeline.

    Returns [(part_name, mesh, extruder), ...].
    """
    if spec.mode == "refit":
        from . import pipeline
        return pipeline.refit_design(spec)
    from . import generate
    return generate.build(spec)
