---
name: issue-triage
description: Classify an issue by type and severity, check it for missing information,
  and draft a short first reply that asks only for what is missing.
requires:
  tools:
  - Read
  capabilities:
  - source-control
---
# Issue triage procedure

1. Read the title, the body, and any template sections. Ignore emoji and greetings.
2. **Type**, pick exactly one:
   - `bug`: existing behavior is wrong, crashes, or contradicts the docs.
   - `feature`: asks for new behavior or a change to intended behavior.
   - `question`: asks how to do something and reports no defect.
   If the issue mixes types, pick the type that is blocking the reporter and note the other in one line.
3. **Severity**, pick exactly one:
   - `sev:critical`: data loss, a security exposure, or the product is unusable for every user.
   - `sev:high`: the app crashes or exits, or a core feature is broken with no reasonable workaround.
     Any crash is at least `sev:high`; needing to redo work by hand does not count as a workaround for a crash.
   - `sev:medium`: wrong behavior that does not crash and has a reasonable workaround.
   - `sev:low`: cosmetic issues, typos, and all feature requests and questions unless they block production.
   Base severity on the impact the reporter describes. Do not assign high severity just because the reporter is upset,
   and do not lower it because the report is thin; missing details go in the reply, not into the severity.
4. **Completeness checklist**:
   - bug: version, environment (OS/runtime), steps to reproduce, expected vs. actual result, logs or stack trace for crashes.
   - feature: the use case or problem, the proposed behavior, the alternatives considered.
   - question: what was tried and where it failed.
   List only the items that are actually absent. Do not count an item as missing if it appears anywhere in the body.
5. **Duplicates**: search open issues for the key error string or title terms. Name a candidate only if the symptom matches. Otherwise, say nothing about duplicates.
6. **Draft reply** (under 120 words):
   - Thank the reporter in one short clause.
   - If items are missing, give them as a numbered list of specific requests. Write "which version of the CLI are you running?", not "more info".
   - If nothing is missing, ask for nothing. Confirm the issue is understood and give the next step.
   - Do not promise fixes, dates, or root causes.
7. **Output**, one block per issue:
   ```
   Issue: <id or file>
   Labels: <type>, <sev:level>
   Missing: <comma list or 'none'>
   Draft reply:
   <text>
   ```
