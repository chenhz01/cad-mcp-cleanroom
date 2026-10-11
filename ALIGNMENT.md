# Alignment Audit (Rules 85-100 / 16 items) — cad-mcp-cleanroom

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Safety/Ethics section | N/A | Not a security-research repo; no dangerous content. |
| 2 | Privacy/keys | PASS | No keys/tokens/real names/emails in any file; grep `(sk-\|ghp_\|api[_-]?key)` = 0 hits. |
| 3 | Copyright boundary | PASS | No text copied from source repos (candidate card used as inspiration only, <50 words); MIT LICENSE present. |
| 4 | Fact-check numbers | PASS | Test counts/timing from `python self_test.py` (22 checks, ~2 s, repro command in README); other timings marked [estimated]; anchor facts dated as-of. |
| 5 | Confidence grading | PASS | README has two explicit labels: High (85%) and Medium (65%) [estimated], each with basis. |
| 6 | Minimal Fallback | PASS | README "Minimal Fallback (PLAN B)" section — curl+diff enforcement path, zero deps. |
| 7 | Quickstart timing | PASS | Quickstart labelled ~2 min with staged steps (self-test → demo → own manifest). |
| 8 | Conflict arbitration | PASS | "Design Trade-offs" states priority safety > simplicity > coverage with concrete examples. |
| 9 | Changelog ≥2 iterations | PASS | CHANGELOG v0.1.0 → v0.1.1 → v0.1.2; v0.1.2 adds anchor-differentiation features (session drift, exposure score). |
| 10 | Exemption (session rule) | N/A | Session-level governance item; static repo not applicable. |
| 11 | Knowledge cutoff | PASS | README footer: "Data as of 2026-10-11"; anchor facts (CAD-MCP README, stars) dated same. |
| 12 | Explicit assumptions | PASS | `[Core Assumptions]` lists 4 premises (state_hash coverage, upsert idempotence, SHA-256 sufficiency, manifest-as-code). |
| 13 | Three-part self-test | PASS | self_test.py covers functional (8), error paths (6), extreme edges (8); 22/22 PASS. |
| 14 | Socratic FAQ | PASS | FAQ "When NOT to use this?" — stateless servers and design-phase projects. |
| 15 | Pareto iteration | PASS | Round 2: 13→16 tests (+23%). Round 3 (v0.1.2): 16→22 tests (+38%) + two new capabilities; CHANGELOG-traceable. |
| 16 | ≤60-word opening | PASS | First paragraph is 58 words, states what/who-needs-it with a judgment sentence. |

Additional: **Second-order effects** — README "Limits & Second-order Effects" covers declaration gaming, unaudited side channels, and PASS≠correct.
