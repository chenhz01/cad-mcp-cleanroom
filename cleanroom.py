"""cad-mcp-cleanroom: cleanroom acceptance harness for CAD-style MCP command surfaces.

Pure standard library. Verifies three properties of a command surface:
  1. Determinism  - same command + args -> byte-identical canonical output.
  2. Purity       - commands declared read-only leave server state untouched.
  3. Idempotence  - mutating commands replayed once more change nothing further.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

# ---------------------------------------------------------------- primitives

def canonical(obj: Any) -> str:
    """Stable serialization: sorted keys, no whitespace, floats via repr."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=repr)


def out_hash(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- contract

class ServerError(Exception):
    pass


class CleanroomServer:
    """Protocol any audited server must satisfy.

    execute(name, args) -> {"ok": bool, "data": Any, "error": str|None}
    state_hash()        -> str  (digest of all persistent state)
    """

    def execute(self, name: str, args: dict) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def state_hash(self) -> str:  # pragma: no cover - interface
        raise NotImplementedError


# ---------------------------------------------------------------- checks

def check_determinism(server: CleanroomServer, name: str, args: dict, runs: int = 3) -> dict:
    """Same input N times -> identical output hashes. Read-only safe to repeat."""
    hashes, last = [], None
    for _ in range(max(1, runs)):
        r = server.execute(name, args)
        if not r.get("ok"):
            return {"check": "determinism", "command": name, "status": "ERROR", "error": r.get("error")}
        h = out_hash(r.get("data"))
        hashes.append(h)
        last = h
    ok = len(set(hashes)) == 1
    return {"check": "determinism", "command": name, "status": "PASS" if ok else "FAIL",
            "hashes": hashes, "detail": "stable" if ok else "output varies across identical calls"}


def check_purity(server: CleanroomServer, name: str, args: dict) -> dict:
    """Declared read-only command must not mutate state."""
    before = server.state_hash()
    r = server.execute(name, args)
    after = server.state_hash()
    if not r.get("ok"):
        return {"check": "purity", "command": name, "status": "ERROR", "error": r.get("error")}
    ok = before == after
    return {"check": "purity", "command": name, "status": "PASS" if ok else "FAIL",
            "detail": "state untouched" if ok else "read-only command mutated state (before=%s after=%s)" % (before[:12], after[:12])}


def check_idempotence(server: CleanroomServer, name: str, args: dict) -> dict:
    """Mutating command: applying twice must equal applying once.

    Execution failures are surfaced as ERROR instead of silently passing
    (a failing command trivially leaves state unchanged).
    """
    server.execute("cleanroom_reset", {})
    r1 = server.execute(name, args)
    if not r1.get("ok"):
        return {"check": "idempotence", "command": name, "status": "ERROR", "error": r1.get("error")}
    s1 = server.state_hash()
    r2 = server.execute(name, args)
    if not r2.get("ok"):
        return {"check": "idempotence", "command": name, "status": "ERROR",
                "error": "first application ok but replay failed: %s" % r2.get("error")}
    s2 = server.state_hash()
    ok = s1 == s2
    return {"check": "idempotence", "command": name, "status": "PASS" if ok else "FAIL",
            "detail": "replay is a no-op" if ok else "second application changed state again (not idempotent)"}


def check_schema(server: CleanroomServer, name: str, args: dict, schema: dict) -> dict:
    """Output data must carry required keys with JSON-compatible types."""
    r = server.execute(name, args)
    if not r.get("ok"):
        return {"check": "schema", "command": name, "status": "ERROR", "error": r.get("error")}
    data = r.get("data")
    problems = []
    if not isinstance(data, dict):
        problems.append("data is not an object")
    else:
        tmap = {"string": str, "number": (int, float), "bool": bool, "array": list, "object": dict, "null": type(None)}
        for key, typ in schema.items():
            if key not in data:
                problems.append("missing key %r" % key)
            elif typ in tmap and not isinstance(data[key], tmap[typ]) or (typ == "bool" and isinstance(data[key], bool) is False):
                if key in data and not isinstance(data[key], tmap.get(typ, object)):
                    problems.append("key %r type mismatch (want %s)" % (key, typ))
    return {"check": "schema", "command": name, "status": "PASS" if not problems else "FAIL", "detail": "; ".join(problems) or "conforms"}


# ---------------------------------------------------------------- v0.1.2 additions

def check_session_drift(server_factory, manifest: dict) -> dict:
    """Replay the same manifest through two freshly built sessions and compare
    every step's output hash plus the final state hash, pairwise.

    Catches behavior that depends on anything outside (command, args):
    module-level globals shared across sessions, wall-clock leakage, RNG state.
    A server can pass per-session determinism and still drift across sessions.
    """
    s1, s2 = server_factory(), server_factory()
    drifts = []
    for cmd in manifest.get("commands", []):
        name, args = cmd.get("name"), cmd.get("args", {})
        r1, r2 = s1.execute(name, args), s2.execute(name, args)
        if r1.get("ok") != r2.get("ok"):
            drifts.append("%s: ok flag differs across sessions (%s vs %s)"
                          % (name, r1.get("ok"), r2.get("ok")))
            continue
        if r1.get("ok") and out_hash(r1.get("data")) != out_hash(r2.get("data")):
            drifts.append("%s: output differs across identical sessions" % name)
    h1, h2 = s1.state_hash(), s2.state_hash()
    if h1 != h2:
        drifts.append("<final state>: state_hash differs across sessions")
    return {"check": "session_drift", "status": "FAIL" if drifts else "PASS",
            "detail": "; ".join(drifts[:5]) or "two sessions behave identically"}


def surface_score(manifest: dict) -> dict:
    """Quantify command-surface exposure from the manifest alone.

    Penalties: mutating share (up to -40), average declared args (up to -20),
    escape hatches (-25 each). Undeclared purity counts as mutating
    (fail-closed, same rule as the gate). 100 = minimal read-only surface.
    """
    cmds = manifest.get("commands", [])
    if not isinstance(cmds, list):
        raise ServerError("manifest must contain a 'commands' array")
    mut, total_args, hatches = 0, 0, []
    for c in cmds:
        if not isinstance(c, dict):
            raise ServerError("each command must be an object")
        if c.get("purity", "mutating") == "mutating":  # undeclared -> mutating
            mut += 1
        total_args += len(c.get("args") or {})
        if c.get("escape_hatch"):
            hatches.append(c.get("name", "<unnamed>"))
    n = len(cmds)
    if n == 0:
        return {"check": "surface_exposure", "commands": 0, "mutating": 0,
                "mutating_ratio": 0.0, "avg_args": 0.0, "escape_hatches": [],
                "score": 100, "grade": "A", "verdict": "minimal", "detail": "empty surface"}
    pen_mut = 40.0 * mut / n
    avg_args = total_args / n
    pen_args = min(20.0, 2.0 * avg_args)
    pen_hatch = 25.0 * len(hatches)
    score = int(round(max(0.0, 100.0 - pen_mut - pen_args - pen_hatch)))
    grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"
    verdict = {"A": "minimal", "B": "moderate", "C": "wide", "D": "excessive"}[grade]
    return {"check": "surface_exposure", "commands": n, "mutating": mut,
            "mutating_ratio": round(mut / n, 2), "avg_args": round(avg_args, 2),
            "escape_hatches": hatches, "score": score, "grade": grade, "verdict": verdict,
            "detail": "penalties: mutating %.1f, args %.1f, hatches %.1f"
                      % (pen_mut, pen_args, pen_hatch)}


# ---------------------------------------------------------------- audit driver

def audit(manifest: dict, server: CleanroomServer, runs: int = 3) -> dict:
    """Run every declared command through the checks its declaration requires."""
    results = []
    for cmd in manifest.get("commands", []):
        name, args, purity = cmd.get("name", ""), cmd.get("args", {}), cmd.get("purity", "read-only")
        if purity == "read-only":
            results.append(check_determinism(server, name, args, runs))
            results.append(check_purity(server, name, args))
        else:
            results.append(check_idempotence(server, name, args))
        if cmd.get("schema"):
            results.append(check_schema(server, name, args, cmd["schema"]))
    failed = [r for r in results if r["status"] == "FAIL"]
    errors = [r for r in results if r["status"] == "ERROR"]
    if errors:
        verdict = "ERROR"
    elif failed:
        verdict = "REJECT"
    else:
        verdict = "PASS"
    return {"tool": "cad-mcp-cleanroom", "verdict": verdict,
            "totals": {"checks": len(results), "fail": len(failed), "error": len(errors)},
            "results": results}


def load_manifest(text: str) -> dict:
    try:
        m = json.loads(text)
    except json.JSONDecodeError as e:
        raise ServerError("manifest is not valid JSON: %s" % e)
    if not isinstance(m, dict) or not isinstance(m.get("commands", []), list):
        raise ServerError("manifest must be an object with a 'commands' array")
    return m
