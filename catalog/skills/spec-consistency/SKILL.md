---
name: spec-consistency
description: Find statements in specification documents that cannot both be true, within one document or across several, and statements that depend on something the documents never provide, without deciding which side is right.
requires:
  tools: [Read, Grep]
---
# Spec consistency

A contradiction is two statements about the same subject, in the same configuration and
at the same time, that cannot both be true. They may be in one document or in different
ones.

A gap is a statement that depends on something the documents never provide: a value
with no source, a sender with no route to its receiver, a mapping between two
identifiers that is never given. Nothing says the opposite, so it is not a contradiction.
A detail left for the implementer to decide is not a gap.

## Method

1. List the documents in scope and read each one in full. Keep track of any you could
   not read.
2. Build an inventory before comparing anything. Go through each document from start to
   end and list every:
   - identifier and its format, including example values
   - field in a payload or table, with its type and where its value comes from
   - endpoint, topic, command, event and interface, with who sends and who receives it
   - component and the job it is given, including its place in any diagram or numbered flow
   - number with its unit
   - absolute claim, such as "all", "only", "never", "requires" or "must", and any list
     presented as the full set of options
3. Work through the inventory line by line, and do not stop because you already have
   findings:
   - The same name must have the same type, format and meaning everywhere it appears.
   - Each value must agree wherever it is stated. Convert units before comparing, so
     2 kW and 2000 W agree and 0.5 L/s and 12 L/min do not.
   - Each absolute claim must hold against every other statement in scope.
   - Both ends of each interface must agree on what is sent, and a sender must have a
     route to its receiver.
   - A diagram and the prose describing it must show the same thing.
4. Work out what the documents imply as well as what they state. A figure in one
   document contradicts another's parts list when the parts do not add up to it.
5. Before reporting a gap, search the documents you can reach outside the review's scope,
   such as the rest of the repo. Drop the gap if they answer it, and do not review them
   for anything else. If you could not search them, say so under `Gaps`.

## Not contradictions

- **Different subjects:** variants, models, environments or units that are meant to differ.
- **Recorded changes:** a document saying X replaced Y, or a section describing an
  earlier revision. Only a document still presenting Y as current is a contradiction.
- **Different measures:** typical against peak, nominal against maximum.
- **Rounding:** a figure given as approximate that is close to the exact one.
- **Silence:** one document covering something another leaves out. It is a gap only when
  a statement depends on the missing part.

## Reporting

- List contradictions first, most severe first whether they span documents or not: the
  severity, the subject, then each side as `path:line` and what it says.
- One finding per subject. Never combine separate subjects in one finding.
- Severity is high or medium. High means a safety limit, a security property such as who
  can access or read something, or a conflict that would stop parts built from different
  documents working together. Everything else is medium.
- When several documents repeat the same conflict, make it one finding listing every
  site, not one finding per pair.
- Do not decide which side is right. You may note each side's `modified` date when
  the documents have one, as evidence for the owner.
- After the contradictions, list gaps under the heading `Gaps`, with no severity: the
  subject, the statement that depends on it as `path:line`, and what is missing. Leave
  the section out when there are none.
- End with `Reviewed N documents.` and name any you could not read.
- With no contradictions, start with the line `No contradictions found in N documents.`.
  With no gaps either, that line is the whole report, plus any you could not read.
