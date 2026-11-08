---
name: kicad-schematic
description: Create and modify KiCAD schematics programmatically with the kicad-sch-api Python library, using symbols from the installed KiCAD libraries, and verify every change with kicad-cli ERC and a netlist export.
requires:
  tools: [Bash, Read, Write]
  capabilities: [schematic-capture, schematic-erc]
---
# Schematic capture with kicad-sch-api

Interpreter: `/Users/manaspradhan/Desktop/Design-Studio/KiCAD/.venv/bin/python`, with
`KICAD_SYMBOL_DIR=/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols` set.
Write a short Python script per change and run it; do not hand-edit `.kicad_sch` text.

## Reading before changing

Run `tools/cli/kicad_sch_dump.py <file>` (system python3) first. It prints the components,
the ERC result, and every net with its `ref.pin` members. Decide what is missing from that,
not from assumptions. If the schematic already satisfies the request, change nothing and say so.

## The API that works

```python
import kicad_sch_api as ksa
sch = ksa.load_schematic("x.kicad_sch")          # or ksa.create_schematic("Title")
sch.components.add(lib_id="Device:C", reference="C1", value="10uF",
                   position=(85, 90), footprint="Capacitor_SMD:C_0805_2012Metric")
sch.components.add(lib_id="power:GND", reference="#PWR03", value="GND", position=(100, 100))
sch.add_wire_between_pins("C1", "2", "U1", "1")   # straight wire, pin end to pin end
sch.components.get("U1").pins                     # pin numbers and names
sch.get_component_pin_position("U1", "3")
sch.save("x.kicad_sch")
```

- Symbols come from the KiCAD libraries as `Library:Name`, for example `Regulator_Linear:AMS1117-3.3`,
  `Device:R`, `Device:LED`, `power:+3V3`, `power:GND`, `power:PWR_FLAG`. Check pin numbers with
  `.pins` before wiring; regulator pin order is not always VI, GND, VO.
- Every power net that is not driven by a power-output pin needs a `power:PWR_FLAG` wired to it,
  or ERC reports "power pin not driven". Power symbols and flags use `#PWR`/`#FLG` references.
- Keep new parts on a 2.54 mm grid and near the pins they connect to. Place parts, then wire.
- Do not use `sch.nets`, `are_pins_connected`, or `run_erc` from the library; its connectivity
  analyzer is unreliable. Verify with kicad-cli instead.

## Verifying

After saving, run `tools/cli/kicad_sch_dump.py <file>` again. The change is done only when:
ERC is clean (or has no new violations), the NETS section shows the intended `ref.pin`
members on the intended nets, and nothing else moved net. Report the before and after nets
for the parts you touched and the ERC line.
