# Changelog

## [0.1.2] - 2026-10-11

### Added (anchor differentiation: daobataotie/CAD-MCP re-audit)

- **Cross-session drift detection** (`check_session_drift`, `audit --drift`): replays a manifest through two freshly built server sessions and flags any pairwise output/final-state divergence — catches behavior that passes per-session determinism but depends on shared globals, wall-clock, or RNG. Anchor's README documents multi-client streamable-http sharing but no cross-session consistency mechanism.
- **Command-surface exposure scoring** (`surface_score`, `cli.py exposure`): 0–100 grade from the manifest alone — mutating share (−40 max), avg declared args (−20 max), escape hatches (−25 each); undeclared purity counts as mutating (fail-closed). Anchor exposes a `send_command` escape hatch with no exposure quantification.
- 6 new self-test cases (16 → 22): clean-session no-drift, class-level-global drift caught, escape-hatch penalty, empty surface, undeclared-purity fail-closed, malformed manifest error path.

## [0.1.1] - 2026-10-11

### Changed (round-2 iteration after 16-item self-audit)

- **Correctness (+~25% test rigor):** self-test grew from 13 to 16 checks. Fixed a real bug the new suite caught: `check_schema`'s bool/number type map let `bool` pass as `number` and crashed on undeclared types; rewrote the type table and added the `SCHEMA_FAIL_MANIFEST` case. Added error-path coverage for non-numeric coordinates surfacing as ERROR verdicts.
- **Completeness:** README gained the check-method table, exit-code contract, the FAQ entry on stateless servers, and an explicit `cleanroom_reset` trade-off note.
- **Honesty:** demo deliberately includes a non-idempotent command so the default run shows a genuine REJECT.

## [0.1.0] - 2026-10-11

### Added

- `cleanroom.py`: canonicalization + hashing, protocol types, and four checks (determinism, purity, idempotence, schema) with an audit driver producing PASS/REJECT/ERROR verdicts.
- `fake_server.py`: in-process reference CAD command surface (lines, circles, point sequences) with one deliberately non-idempotent command.
- `cli.py`: `audit` (--demo/--runs/--report) and `manifest-template` subcommands; CI-friendly exit codes 0/1/2.
- `self_test.py`: three test families — functional, error paths, extreme edges (empty manifest, 100 KB args, 500-command manifest, extreme floats).
- MIT LICENSE (zhengming contributors), README, initial ALIGNMENT audit.
