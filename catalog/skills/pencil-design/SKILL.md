---
name: pencil-design
description: Create and revise screens in a Pen.dev (.pen) design file through the Pencil MCP server, reusing the file's existing design tokens and components.
requires:
  capabilities: [design-canvas]
---
# Designing in Pen.dev

Never read or edit a `.pen` file with file tools. The Pen app holds the live
document state and only it writes the file. Everything goes through the Pencil
MCP server, which only addresses documents that are open in the app.

## Before drawing

1. If the task names a `.pen` file, work on that file: pass its absolute path as
   `filePath` on every `execute` call. Otherwise call `get_app_state` to find the
   open document.
2. Call `read_skill` and follow what it returns. It is the authoritative guide to
   the `.pen` schema and the `execute` tool.
3. In one `execute`, print `GetVariables()` and list the reusable components
   (`Get(n => n.reusable && Print(n.id, n.name))`). These are the design tokens
   and components you must reuse.

## While drawing

- Reuse existing components and tokens. Introduce a new token only when no
  existing one fits, and name it in the same convention as the file.
- Build one screen per request. Do not restyle screens you were not asked to touch.
- Keep layer names meaningful. A reviewer should understand the tree without
  opening every node.

## Before finishing

- Read the new screen back with `Get` and confirm every color, spacing, and radius
  is a `$variable` reference, not a literal value.
- Report the screen name, the components reused, and any new token with its reason.
