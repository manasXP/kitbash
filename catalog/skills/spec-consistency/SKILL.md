---
name: spec-consistency
description: Find statements in specification documents that cannot both be true, within one document or across several, citing both sides without deciding which is right.
requires:
  tools: [Read, Grep]
---
# Spec consistency

A contradiction is two statements about the same subject, in the same configuration and
at the same time, that cannot both be true. They may be in one document or in different
ones.

## Method

1. List the documents in scope and read them. Keep track of any you could not read.
2. Note the facts that have one correct value: part numbers, quantities, limits and
   timings, interfaces and protocols, names of states, topics and endpoints, which
   component owns a decision, costs and dates.
3. Compare each fact within each document and across documents. Convert units before comparing, so 2 kW and
   2000 W agree and 0.5 L/s and 12 L/min do not.
4. Work out what the documents imply as well as what they state. A figure in one
   document contradicts another's parts list when the parts do not add up to it.

## Not contradictions

- **Different subjects:** variants, models or units that are meant to differ.
- **Recorded changes:** a document saying X replaced Y, or a section describing an
  earlier revision. Only a document still presenting Y as current is a contradiction.
- **Different measures:** typical against peak, nominal against maximum.
- **Rounding:** a figure given as approximate that is close to the exact one.
- **Silence:** one document covering something another leaves out.

## Reporting

- One finding per subject, most severe first whether it spans documents or not: the
  severity, the subject, then each side as `path:line` and what it says.
- Severity is high or medium. High means a safety limit, a security property such as who
  can access or read something, or something that would get built wrong if an engineer
  followed the wrong document. Everything else is medium.
- When several documents repeat the same conflict, make it one finding listing every
  site, not one finding per pair.
- Do not decide which side is right. You may note each side's `modified` date when
  the documents have one, as evidence for the owner.
- End with `Reviewed N documents.` and name any you could not read.
- With no findings, the whole report is the single line
  `No contradictions found in N documents.`, plus any you could not read.
