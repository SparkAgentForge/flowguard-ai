# Skill verification contract

The Skill uses five independent gates. Passing a local syntax check alone is
not sufficient to call a release verified.

## 1. Cataloged

The Skill has a stable name, description, UI entry, and endpoint operation
manual. Keep these synchronized:

- `SKILL.md` frontmatter and routing rules;
- `agents/openai.yaml` display metadata;
- `references/api-catalog.md` FlowGuard API table;
- `SKILL_CARD.md` identity and scope.

## 2. Scanned

Run `scripts/quick_validate_skill.sh`. It invokes the standard Skill validator
and `scripts/scan_skill.sh`, which checks the Skill tree for private-key blocks,
common credential prefixes, credential-bearing URLs, and executable syntax
errors. A real product release should additionally attach the organization's
SkillSpector or equivalent security scan report.

## 3. Evaluated

Use `BENCHMARK.md` for routing cases and `references/acceptance-matrix.md` for
the runtime business flow. A runtime evaluation must preserve request paths,
provider, resource IDs, status transitions, failure reason, and cleanup result.
Do not report `PASS` from a provider response without FlowGuard evidence gates.

## 4. Signed

Run `scripts/sign_skill_manifest.sh` only with an owner-controlled signing key:

```bash
FLOWGUARD_SKILL_SIGNING_KEY=/secure/path/skill-signing-key.pem \
  scripts/sign_skill_manifest.sh
```

The script writes a file manifest and detached `skill.oms.sig` beside the Skill.
The private key is never copied into the repository. If no approved key or
signature verifier is available, report the gate as pending.

## 5. Documented

Document the purpose, accepted inputs, boundaries, interface table, provider
contracts, benchmark state, and known verification gaps in `SKILL.md`,
`SKILL_CARD.md`, and the linked references. Keep documentation synchronized
with the actual OpenAPI contract; use `/api/openapi.json` for request fields.

## Release rule

`Verified = Cataloged + Scanned + Evaluated + Signed + Documented`.
The Skill may be used before all gates are complete, but its response must
state the missing gate instead of implying trust that has not been established.
