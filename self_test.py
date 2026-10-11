"""Self-test: functional / error-path / extreme-edge families. Exit 0 = all PASS."""
from __future__ import annotations

import json
import sys

from cleanroom import (ServerError, audit, canonical, check_determinism,
                       check_idempotence, check_purity, check_schema,
                       check_session_drift, load_manifest, out_hash,
                       surface_score)
from fake_server import FakeCadServer

PASS, FAIL = "PASS", "FAIL"
_results = []


def record(family: str, name: str, ok: bool, detail: str = "") -> None:
    _results.append((family, name, PASS if ok else FAIL, detail))


# ---------------------------------------------------------------- fixtures

def make_manifest(commands):
    return {"commands": commands}


GOOD_MANIFEST = make_manifest([
    {"name": "state_hash", "purity": "read-only", "args": {}, "schema": {"state_hash": "string"}},
    {"name": "list_entities", "purity": "read-only", "args": {}},
    {"name": "get_entity", "purity": "read-only", "args": {"id": "x"}},
    {"name": "add_line", "purity": "mutating", "args": {"id": "l1", "p1": [0, 0], "p2": [3, 4]}},
    {"name": "upsert_circle", "purity": "mutating", "args": {"id": "c1", "center": [1, 1], "r": 2.0}},
    {"name": "delete_all", "purity": "mutating", "args": {}},
])
BAD_MANIFEST = make_manifest([
    {"name": "append_point_seq", "purity": "mutating", "args": {"id": "s1", "point": [1, 1]}},
])
UNKNOWN_MANIFEST = make_manifest([
    {"name": "teleport_model", "purity": "read-only", "args": {}},
])
SCHEMA_FAIL_MANIFEST = make_manifest([
    {"name": "get_entity", "purity": "read-only", "args": {"id": "x"}, "schema": {"entity": "number"}},
])

# ---------------------------------------------------------------- functional


def t_functional():
    s = FakeCadServer()
    r = audit(GOOD_MANIFEST, s)
    record("functional", "good manifest audits PASS", r["verdict"] == "PASS",
           "verdict=%s" % r["verdict"])

    r = audit(BAD_MANIFEST, s)
    record("functional", "non-idempotent append rejected", r["verdict"] == "REJECT",
           "verdict=%s" % r["verdict"])

    # purity honesty: a lying read-only that mutates must FAIL
    class LyingServer(FakeCadServer):
        READ_COMMANDS = {"state_hash", "sneaky_read"}

        def execute(self, name, args):
            if name == "sneaky_read":
                self.entities["ghost"] = {}
                return {"ok": True, "data": {}, "error": None}
            return super().execute(name, args)

    ls = LyingServer()
    pr = check_purity(ls, "sneaky_read", {})
    record("functional", "mutating 'read-only' caught by purity probe", pr["status"] == FAIL)

    r = check_determinism(s, "list_entities", {}, runs=5)
    record("functional", "determinism across 5 runs", r["status"] == PASS)

    r = check_schema(s, "state_hash", {}, {"state_hash": "string"})
    record("functional", "schema conformance", r["status"] == PASS)


# ---------------------------------------------------------------- error paths


def t_error_paths():
    s = FakeCadServer()
    r = audit(UNKNOWN_MANIFEST, s)
    record("error", "unknown command -> ERROR verdict", r["verdict"] == "ERROR")

    bad_args = make_manifest([{"name": "add_line", "purity": "mutating", "args": {"p1": ["a", "b"], "p2": [0, 0]}}])
    r = audit(bad_args, s)
    record("error", "non-numeric coords -> ERROR verdict", r["verdict"] == "ERROR")

    try:
        load_manifest("{not json")
        record("error", "corrupt manifest raises", False)
    except Exception as e:
        record("error", "corrupt manifest raises ServerError", "manifest is not valid JSON" in str(e))

    try:
        load_manifest("[1,2,3]")
        record("error", "non-object manifest rejected", False)
    except Exception as e:
        record("error", "array manifest rejected", "commands" in str(e))

    missing = make_manifest([{"purity": "read-only", "args": {}}])
    r = audit(missing, s)
    record("error", "command without name handled (unknown -> ERROR)", r["verdict"] == "ERROR")


# ---------------------------------------------------------------- extreme edges


def t_extreme_edges():
    s = FakeCadServer()

    empty = make_manifest([])
    r = audit(empty, s)
    record("edge", "empty manifest -> PASS with 0 checks", r["verdict"] == "PASS" and r["totals"]["checks"] == 0)

    r = check_determinism(s, "state_hash", {}, runs=1)
    record("edge", "runs=1 still yields a verdict", r["status"] == PASS)

    big_args = {"id": "big", "p1": [0, 0], "p2": [1e6, -1e6], "note": "x" * 100000}
    r = check_idempotence(s, "add_line", big_args)
    record("edge", "100KB args idempotence", r["status"] == PASS)

    huge_seq = make_manifest([
        {"name": "upsert_circle", "purity": "mutating",
         "args": {"id": "c%d" % i, "center": [i, i], "r": 0.5}}
        for i in range(500)
    ])
    r = audit(huge_seq, s)
    record("edge", "500-command manifest fully audited",
           r["verdict"] == "PASS" and r["totals"]["checks"] == 500)

    floats = {"a": 1.7976931348623157e308, "b": -0.0, "c": 2.2250738585072014e-308}
    record("edge", "extreme floats hash stably", out_hash(floats) == out_hash(dict(reversed(list(floats.items())))))

    nested = {"k": [{"z": 1, "a": [2, {"m": None}]}]}
    record("edge", "nested structure canonicalization stable",
           canonical(nested) == canonical(json.loads(canonical(nested))))


# ------------------------------------------- v0.1.2: drift + surface exposure


def t_drift_and_exposure():
    r = check_session_drift(FakeCadServer, GOOD_MANIFEST)
    record("functional", "two identical sessions show no drift", r["status"] == PASS,
           r.get("detail", ""))

    class GlobalCountServer(FakeCadServer):
        _calls = 0  # class-level counter: leaks across sessions

        def execute(self, name, args):
            GlobalCountServer._calls += 1
            r = super().execute(name, args)
            if r.get("ok") and name == "list_entities":
                r = dict(r)
                r["data"] = dict(r["data"], session_calls=GlobalCountServer._calls)
            return r

    GlobalCountServer._calls = 0
    r = check_session_drift(GlobalCountServer, GOOD_MANIFEST)
    record("functional", "cross-session global counter caught as drift", r["status"] == FAIL,
           r.get("detail", ""))

    base = make_manifest([
        {"name": "read_a", "purity": "read-only", "args": {}},
        {"name": "read_b", "purity": "read-only", "args": {}},
        {"name": "write_a", "purity": "mutating", "args": {"id": 1}},
        {"name": "write_b", "purity": "mutating", "args": {"id": 1, "v": 2}},
    ])
    s_clean = surface_score(base)
    s_hatch = surface_score(make_manifest(base["commands"] + [
        {"name": "send_command", "purity": "mutating", "args": {"cmd": "x"}, "escape_hatch": True}]))
    record("functional", "escape hatch lowers exposure score",
           s_hatch["score"] < s_clean["score"] and s_clean["escape_hatches"] == [],
           "clean=%s hatched=%s" % (s_clean["score"], s_hatch["score"]))

    empty = surface_score(make_manifest([]))
    record("edge", "empty surface scores 100/A", empty["score"] == 100 and empty["grade"] == "A")

    undeclared = surface_score(make_manifest([{"name": "mystery", "args": {}}]))
    record("edge", "undeclared purity counted as mutating (fail-closed)",
           undeclared["mutating"] == 1 and undeclared["score"] < 100)

    try:
        surface_score({"commands": "nope"})
        record("error", "malformed surface manifest raises", False)
    except ServerError:
        record("error", "malformed surface manifest raises ServerError", True)


def main() -> int:
    t_functional()
    t_error_paths()
    t_extreme_edges()
    t_drift_and_exposure()
    fails = [r for r in _results if r[2] == FAIL]
    for fam, name, status, detail in _results:
        print("[%s] %-9s %s%s" % (status, fam, name, (" | " + detail) if detail else ""))
    print("\n%d checks, %d failed" % (len(_results), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
