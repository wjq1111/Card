---
name: texas-holdem-development-flow
description: Development workflow for TexasHoldemOnline requirement changes, feature work, rule updates, and bug fixes. Use when Codex needs to add, remove, or change behavior before release work, especially when product requirements, poker rules, protocol changes, code, tests, and self-validation must stay synchronized.
---

# Texas Holdem Development Flow

Use this skill before `texas-holdem-release-flow`. Treat requirement delivery as gated work. Do not claim completion until documentation, code, tests, and self-validation are all updated or explicitly marked unchanged with a reason.

## Delivery Gates

1. Confirm the requirement delta
   - Identify the exact behavior being added, changed, or removed.
   - Map it to the authoritative artifacts:
     - `docs/product_requirements.md` for product behavior and acceptance criteria
     - `docs/poker-rule-test-cases.md` for natural-language gameplay rules
     - `src/proto/poker.proto` when RPCs or message shapes change
   - If the request conflicts with the docs, update the docs first or in the same change before touching implementation.

2. Build an impact list
   - List affected files in four buckets: requirements docs, implementation, tests, validation commands.
   - Inspect the likely change surface across `src/server/`, `src/client/`, `src/shared/`, `src/proto/`, `tests/`, and `tools/`.
   - Treat "no doc change" and "no test change" as claims that need a short justification.

3. Update docs and executable specs
   - Update `docs/product_requirements.md` whenever user-visible behavior, acceptance criteria, state transitions, or error handling changes.
   - Update `docs/poker-rule-test-cases.md` whenever rule legality, betting flow, showdown, settlement, side pots, or reconnect semantics change.
   - Keep rule case ids and meanings aligned with `tools/check_rules.py` and `tests/test_rule_cases.py`.

4. Update tests before or with code
   - Add or update targeted automated tests for the changed behavior.
   - For gameplay rule changes, keep these artifacts synchronized:
     - `docs/poker-rule-test-cases.md`
     - `tools/check_rules.py`
     - `tests/test_rule_cases.py`
   - For protocol or API changes, update tests that cover the affected client/server integration points.
   - Do not leave test updates as follow-up work unless the user explicitly approves that split.

5. Implement the code change
   - Modify the smallest coherent set of files that satisfies the requirement.
   - Regenerate generated artifacts after interface changes:

```powershell
python tools\generate_grpc.py
```

6. Run self-validation
   - Run syntax and baseline validation for non-trivial changes:

```powershell
python -m compileall src tools tests
```

   - Run `python tools\generate_grpc.py` after `src/proto/` changes.
   - Run `python tools\check_rules.py` after gameplay, action-flow, hand-evaluation, or settlement changes.
   - Run targeted tests for the touched area.
   - Run the full test suite when the change is broad or touches shared gameplay state:

```powershell
python -m unittest discover -s tests -v
```

   - Stop and fix failures before moving on.

7. Report completion explicitly
   - End with a compact checklist that states:
     - requirements docs: updated or unchanged with reason
     - code: updated
     - tests: updated or unchanged with reason
     - self-validation: commands run and pass/fail result
     - residual risks or approved follow-up work
   - If any gate is incomplete, say the work is not done.

## Working Rules

- Prefer one coherent change set for the requirement rather than separate doc/code/test follow-ups.
- Update tests even for bug fixes; the bug should be guarded by at least one automated assertion.
- If a request is ambiguous, clarify the requirement delta before changing code.
- Never treat "it should still work" as a substitute for running self-validation.
- Do not keep temporary compatibility layers, duplicate package trees, or deprecated directories once the final path is known. Remove obsolete structure in the same change.

## Handoff

After all development gates pass and the user wants deployment, remote verification, or branch promotion, switch to `texas-holdem-release-flow`.
