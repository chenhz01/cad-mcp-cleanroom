"""CLI for cad-mcp-cleanroom. Pure argparse, no third-party deps."""
from __future__ import annotations

import argparse
import json
import sys

from cleanroom import audit, check_session_drift, load_manifest, surface_score
from fake_server import FakeCadServer

DEMO_MANIFEST = {
    "commands": [
        {"name": "state_hash", "purity": "read-only", "args": {},
         "schema": {"state_hash": "string"}},
        {"name": "list_entities", "purity": "read-only", "args": {},
         "schema": {"entities": "array", "count": "number"}},
        {"name": "get_entity", "purity": "read-only", "args": {"id": "l1"}},
        {"name": "add_line", "purity": "mutating", "args": {"id": "l1", "p1": [0, 0], "p2": [10, 10]}},
        {"name": "upsert_circle", "purity": "mutating", "args": {"id": "c1", "center": [5, 5], "r": 2.5}},
        {"name": "append_point_seq", "purity": "mutating", "args": {"id": "seq1", "point": [1, 2]}},
        {"name": "delete_all", "purity": "mutating", "args": {}},
    ]
}


def cmd_audit(args: argparse.Namespace) -> int:
    if args.demo:
        manifest, text = DEMO_MANIFEST, None
    else:
        with open(args.manifest, "r", encoding="utf-8") as f:
            text = f.read()
        manifest = load_manifest(text)
    server = FakeCadServer()
    report = audit(manifest, server, runs=args.runs)
    if args.drift:
        d = check_session_drift(lambda: FakeCadServer(), manifest)
        report["drift"] = d
        if d["status"] == "FAIL" and report["verdict"] == "PASS":
            report["verdict"] = "REJECT"
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, sort_keys=True)
    return {"PASS": 0, "REJECT": 1, "ERROR": 2}[report["verdict"]]


def cmd_exposure(args: argparse.Namespace) -> int:
    manifest = DEMO_MANIFEST if args.demo else load_manifest(open(args.manifest, encoding="utf-8").read())
    print(json.dumps(surface_score(manifest), indent=2, sort_keys=True))
    return 0


def cmd_manifest_template(_args: argparse.Namespace) -> int:
    print(json.dumps(DEMO_MANIFEST, indent=2))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cad-mcp-cleanroom",
                                description="Cleanroom acceptance audit for CAD-style MCP command surfaces.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit a command manifest against the cleanroom protocol")
    a.add_argument("manifest", nargs="?", help="path to manifest JSON")
    a.add_argument("--demo", action="store_true", help="run the built-in demo manifest")
    a.add_argument("--runs", type=int, default=3, help="determinism repetitions (default 3)")
    a.add_argument("--report", help="write JSON report to this path")
    a.add_argument("--drift", action="store_true",
                   help="also replay the manifest through two fresh sessions and flag cross-session drift")
    a.set_defaults(func=cmd_audit)

    t = sub.add_parser("manifest-template", help="print a starter manifest")
    t.set_defaults(func=cmd_manifest_template)

    e = sub.add_parser("exposure", help="score command-surface exposure from a manifest (no server needed)")
    e.add_argument("manifest", nargs="?", help="path to manifest JSON")
    e.add_argument("--demo", action="store_true", help="score the built-in demo manifest")
    e.set_defaults(func=cmd_exposure)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
