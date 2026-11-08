Fixture: a cut-down Epicura cloud API (Fastify 5, Zod, TypeScript, Vitest), in-memory store, no database.
Setup and tests: `pnpm install` then `pnpm test` from this directory; `pnpm lint` type-checks.
Known defect used by the backend-engineer evals: `POST /recipes` casts the body instead of validating it,
so a malformed body answers 500 instead of 400.
