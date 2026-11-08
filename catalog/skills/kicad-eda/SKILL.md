---
name: kicad-eda
description: Check KiCAD schematics and boards with the kicad-cli ERC and DRC runners, read the JSON reports, and report violations with net names, reference designators, layers, and positions.
requires:
  tools: [Bash, Read, Grep]
  capabilities: [schematic-erc, design-rule-check]
---
# KiCAD checks with kicad-cli

The binary is `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`. Design files are
plain-text s-expressions: `.kicad_sch` for schematics, `.kicad_pcb` for boards. Read them
with Read or Grep when you need context the report does not give, such as a footprint's
reference or a net's other members.

## Running the checks

Schematic (ERC):

    kicad-cli sch erc --format json --severity-all --output /tmp/erc.json <file.kicad_sch>

Board (DRC):

    kicad-cli pcb drc --format json --severity-all --output /tmp/drc.json <file.kicad_pcb>

Always use `--format json` and read the file you wrote. The console only prints counts.

## Reading the reports

- DRC JSON: `violations[]`, `unconnected_items[]`, `schematic_parity[]`. Each entry has
  `severity`, `type`, `description`, and `items[]` with a `description` naming the object
  (for example `Track [GND] on F.Cu`) and a `pos` in the report units.
- ERC JSON: `sheets[]`, each with `violations[]` of the same shape.
- `severity` is `error`, `warning`, or `exclusion`. Report errors first, then warnings.
  An exclusion was deliberately silenced by the designer; mention the count, do not relist them.

## Reporting

One line per violation: severity, type, the nets or references involved, the layer, the
position, and the measured versus required value when the description gives one. Group
identical types together and give the count. End with one verdict line per file:
`<file>: FAIL, N errors, M warnings, U unconnected` when there is at least one error, otherwise
`<file>: PASS, clean` (warnings alone do not fail a file; list them). Do not speculate about
causes the report does not support, and do not propose layout changes unless asked. If asked
for a fix, give exactly one sentence naming one change; do not list alternatives.
