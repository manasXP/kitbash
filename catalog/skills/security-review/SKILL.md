---
name: security-review
description: Find injection, authentication, authorization, and secret-handling defects in a diff or a file set.
requires:
  tools: [Read, Grep]
  min_model_tier: opus
---
# Security review

Work through the diff hunk by hunk. For each hunk, ask the four questions below
and record only confirmed defects, not style or hypothetical issues.

1. **Input boundary.** Does untrusted data reach a query, shell, template, path,
   or deserializer without parameterization or validation? Name the sink.
2. **Authentication.** Can this code path be reached without the caller's identity
   being established? Look for new routes, handlers, and middleware changes.
3. **Authorization.** Is the caller's right to the specific resource checked, not
   just their login? Watch for IDs taken from the request and used directly.
4. **Secrets.** Are credentials, tokens, or keys written to logs, source, error
   messages, or client responses?

## Reporting

- One finding per line: `path:line` followed by the defect and the sink.
- Severity is one of high, medium, low. High means exploitable without auth, or an injection into a query, shell or template.
- A clean diff gets the single line `No security findings.`
- Do not pad a clean result with advice.
