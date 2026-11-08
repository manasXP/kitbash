---
name: backend-service
description: Change TypeScript (Fastify, Next.js, Drizzle, Zod) and Python services safely, validating at the boundary and running the project's tests.
requires:
  tools: [Read, Edit, Bash]
  capabilities: [service-toolchain]
---
# Backend services

## Non-negotiables

- Every request body, query and path parameter is validated against a schema at the
  route boundary and a failure answers 400 with the validation issues. A type cast
  (`as Foo`, `request.body!`) is never validation.
- Every external result is checked: a database call, a queue publish, a subprocess, an HTTP
  call. A failure is surfaced to the caller or logged with context, never swallowed.
- State machines reject invalid transitions with an explicit error instead of moving anyway.
- Secrets come from the environment. None is written into source, fixtures or logs.
- No blocking work inside an event handler, MQTT callback or request hook; hand it to a
  queue or an async task.

## Procedure for a change

1. Read the entry point first: the app factory and route registration for a TypeScript
   service, the package `__init__` and the service's main loop for a Python one. Reuse the
   existing schema, store and error helpers rather than adding parallel ones.
2. Find the test command before editing: `scripts` in `package.json` (prefer the
   workspace filter for a monorepo), a `tests/` directory with `unittest` or `pytest`
   for Python. Install dependencies once, in the project directory, when `node_modules`
   is missing.
3. Make the smallest change that fixes the cause. Do not restyle neighbouring code.
4. Add or extend a test that fails before the change and passes after it.
5. Run the test command and the type-check or lint when the project has one.

## Reporting

State what changed and why, the exact test command that ran, and its result. If a
command could not run (no database, no network, missing toolchain), say so and what
is missing; never describe the change as verified without a run.
