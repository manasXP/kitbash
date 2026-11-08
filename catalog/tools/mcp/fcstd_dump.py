#!/usr/bin/env python3
"""Print the structure of a FreeCAD document (.FCStd) without FreeCAD in the loop.

    fcstd_dump.py FILE.FCStd

An .FCStd is a zip whose Document.xml lists every object with its properties. This prints, per object, its type
and label, scalar properties (lengths, radii, placement), links (Base, Tool, Group) and every expression binding,
and for a spreadsheet its cells with aliases. Used by run_evals.py as the `inspect` command for .FCStd fixtures, so
the judge sees what changed in the model rather than a binary diff. The file on disk is what is dumped: an agent
must save the document for its edits to show.
"""
import sys
import xml.etree.ElementTree as ET
import zipfile

SKIP = {"Label2", "Visibility", "Shape", "ExpressionEngine", "Proxy", "cells", "columnWidths", "rowHeights",
        "PropertyXLink", "Material", "AttachmentSupport", "MapMode", "MapPathParameter", "MapReversed",
        "AttachmentOffset", "AttacherType", "AttacherEngine"}


def scalar(prop):
    """One-line value for a property element, or None when it carries nothing worth printing."""
    for child in prop:
        a = child.attrib
        if child.tag in ("Float", "Integer", "Bool", "String", "Link", "Angle"):
            return a.get("value", "")
        if child.tag == "PropertyPlacement":
            return "base=({Px}, {Py}, {Pz}) axis=({Ox}, {Oy}, {Oz}) angle={A}".format(**{k: a.get(k, "0") for k in
                                                                                         ("Px", "Py", "Pz", "Ox", "Oy", "Oz", "A")})
        if child.tag == "LinkList":
            return "[" + ", ".join(l.attrib.get("value", "") for l in child) + "]"
        if child.tag == "PropertyVector":
            return "({valueX}, {valueY}, {valueZ})".format(**{k: a.get(k, "0") for k in ("valueX", "valueY", "valueZ")})
    return None


def main(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("Document.xml"))
    objects = root.find("Objects")
    types = {o.attrib["name"]: o.attrib["type"] for o in objects.findall("Object")} if objects is not None else {}
    data = root.find("ObjectData")
    print(f"DOCUMENT {path.rsplit('/', 1)[-1]}: {len(types)} object(s)")
    for obj in (data.findall("Object") if data is not None else []):
        name = obj.attrib["name"]
        props = {p.attrib["name"]: p for p in obj.find("Properties").findall("Property")}
        label = scalar(props["Label"]) if "Label" in props else name
        print(f"\n{name} [{types.get(name, '?')}]" + (f" label={label!r}" if label != name else ""))
        for pname, p in props.items():
            if pname in SKIP or pname == "Label":
                continue
            v = scalar(p)
            if v not in (None, "", "[]", "false"):
                print(f"  {pname} = {v}")
        ee = props.get("ExpressionEngine")
        if ee is not None:
            for ex in ee.iter("Expression"):
                print(f"  expr {ex.attrib.get('path')} = {ex.attrib.get('expression')}")
        cells = props.get("cells")
        if cells is not None:
            for c in cells.iter("Cell"):
                alias = f"  alias={c.attrib['alias']}" if "alias" in c.attrib else ""
                print(f"  cell {c.attrib.get('address')}: {c.attrib.get('content', '')}{alias}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
