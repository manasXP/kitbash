---
name: mechanical-design
description: Create and revise parametric parts in a FreeCAD document (.FCStd) through the freecad-mcp server, keeping every dimension bound to the document's Params spreadsheet.
requires:
  capabilities: [mechanical-cad]
---
# Designing in FreeCAD

Never read or edit an `.FCStd` file with file tools. It is a zip of XML and BREP that only FreeCAD
writes consistently. Everything goes through the freecad MCP server, which addresses documents open
in the running app by document name (the file name without `.FCStd`).

## Before modelling

1. Call `list_documents`. If the task's file is not open, open it with `execute_code`:
   `FreeCAD.openDocument("/absolute/path/to/file.FCStd")`.
2. Call `get_objects` on the document and read the `Params` spreadsheet. Dimensions live there as
   aliased cells (columns `Name`, `Value (mm)`, `Source`); every object dimension is an expression on an
   alias (`Params.L_plate`), never a literal. FreeCAD rejects single-letter aliases, so names carry a suffix. Treat the aliases as the design's tokens.
3. Note the object tree: which `Part::Box`, `Part::Cylinder` and boolean (`Part::Cut`, `Part::Fuse`)
   objects exist, and what links them. Reuse them before adding anything.

## While modelling

- Change a dimension by changing its `Params` cell, not the object property.
- A new dimension gets a new `Params` row: name in column A, value in B with `setAlias`, and in column C
  why it is that value, prefixed `decided:`, `inference:` or `PLACEHOLDER:` like the existing rows.
- Bind every new object dimension and placement with `setExpression`, for example
  `obj.setExpression("Radius", "Params.hole_d / 2")` and `obj.setExpression(".Placement.Base.x", "Params.L_plate / 2")`.
- One change per request. Do not restyle or rename objects you were not asked to touch.
- Keep object names meaningful; a reviewer should understand the tree without opening the app.

## Before finishing

- Recompute (`doc.recompute()`) and check that no object reports an error and that the final shape
  `isValid()`. Read a dimension back from the object to confirm the expression took.
- Save the document (`doc.save()`), since the app does not write to disk on its own and the file on
  disk is what gets reviewed.
- Report the objects added or changed, each new `Params` alias with its reason, and the recompute result.
