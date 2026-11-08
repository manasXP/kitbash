# Parameters in bracket.FCStd

A flat mounting plate with one centred hole, built headless on 2 Nov 2026 by FreeCAD 1.x. All dimensions are
aliased cells in the `Params` spreadsheet (columns Name, Value (mm), Source); every object dimension is an
expression on an alias, never a literal.

Aliases: L_plate 60 (plate length), W_plate 40 (plate width), T_plate 4 (plate thickness), hole_d 5 (M5 clearance hole).
Single-letter aliases are rejected by FreeCAD, which is why the names carry a suffix.
Objects: Plate (Part::Box, Length=Params.L_plate, Width=Params.W_plate, Height=Params.T_plate);
         Hole (Part::Cylinder, Radius=Params.hole_d / 2, Height=Params.T_plate, Placement.Base.x=Params.L_plate / 2, .y=Params.W_plate / 2);
         Bracket (Part::Cut, Base=Plate, Tool=Hole)
