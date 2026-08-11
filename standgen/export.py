"""Writing STL and Bambu Studio / OrcaSlicer project files.

Bambu will not read part information out of a generic 3MF - it flattens the
whole thing into one object. The writer here emits Bambu's own structure:
one mesh object per part, an assembly object made of components, and a
Metadata/model_settings.config that names each part and assigns its filament.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import trimesh

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    "</Types>"
)

RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel-1" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
)

IDENTITY_3 = "1 0 0 0 1 0 0 0 1 0 0 0"
IDENTITY_4 = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"
MESH_STAT = ('<mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0" '
             'facets_reversed="0" backwards_edges="0"/>')


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def to_print_orientation(meshes, bed=(256, 256)):
    """Rotate Y-up model space to Z-up bed space and centre on the plate."""
    meshes = [m.copy() for m in meshes]
    rot = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
    for m in meshes:
        m.apply_transform(rot)

    allb = np.vstack([m.bounds for m in meshes])
    lo, hi = allb.min(axis=0), allb.max(axis=0)
    shift = np.array([bed[0] / 2 - (lo[0] + hi[0]) / 2,
                      bed[1] / 2 - (lo[1] + hi[1]) / 2,
                      -lo[2]])
    for m in meshes:
        m.apply_translation(shift)
    return meshes


def write_stl(mesh: trimesh.Trimesh, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)
    return path


def write_bambu_3mf(parts, path: str | Path, name: str,
                    bed=(256, 256), orient: bool = True) -> Path:
    """parts: sequence of (part_name, mesh, extruder_index) tuples."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    names = [p[0] for p in parts]
    meshes = [p[1] for p in parts]
    extruders = [p[2] for p in parts]
    if orient:
        meshes = to_print_orientation(meshes, bed=bed)

    objects, components = [], []
    for i, mesh in enumerate(meshes, start=1):
        verts = "".join('<vertex x="%.5f" y="%.5f" z="%.5f"/>' % tuple(v)
                        for v in mesh.vertices)
        tris = "".join('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(f)
                       for f in mesh.faces)
        objects.append(
            f'<object id="{i}" p:UUID="{_uuid(i)}" type="model"><mesh>'
            f"<vertices>{verts}</vertices><triangles>{tris}</triangles>"
            f"</mesh></object>"
        )
        components.append(
            f'<component p:UUID="{_uuid(100 + i)}" objectid="{i}" transform="{IDENTITY_3}"/>'
        )

    assembly_id = len(meshes) + 1
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
        'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
        'requiredextensions="p">\n'
        '<metadata name="Application">standgen</metadata>'
        f'<metadata name="Title">{name}</metadata>\n'
        "<resources>" + "".join(objects) +
        f'<object id="{assembly_id}" p:UUID="{_uuid(assembly_id)}" type="model">'
        f'<components>{"".join(components)}</components></object>'
        "</resources>\n"
        f'<build p:UUID="{_uuid(900)}"><item objectid="{assembly_id}" '
        f'p:UUID="{_uuid(901)}" transform="{IDENTITY_3}" printable="1"/></build>\n'
        "</model>"
    )

    part_xml = ""
    for i, (pname, ext) in enumerate(zip(names, extruders), start=1):
        part_xml += (
            f'    <part id="{i}" subtype="normal_part">\n'
            f'      <metadata key="name" value="{pname}"/>\n'
            f'      <metadata key="matrix" value="{IDENTITY_4}"/>\n'
            f'      <metadata key="extruder" value="{ext}"/>\n'
            f"      {MESH_STAT}\n    </part>\n"
        )

    config = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
        f'  <object id="{assembly_id}">\n'
        f'    <metadata key="name" value="{name}"/>\n'
        '    <metadata key="extruder" value="1"/>\n'
        f"{part_xml}  </object>\n"
        "  <assemble>\n"
        f'   <assemble_item object_id="{assembly_id}" instance_id="0" '
        f'transform="{IDENTITY_4}" offset="0 0 0"/>\n'
        "  </assemble>\n</config>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/model_settings.config", config)
    return path
