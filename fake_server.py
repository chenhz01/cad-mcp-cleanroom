"""In-process cleanroom reference server: a minimal deterministic CAD command surface.

Deliberately contains one non-idempotent command (append_point_seq) so the demo
shows a real REJECT, not a staged success.
"""
from __future__ import annotations

import hashlib
import json

from cleanroom import CleanroomServer, ServerError, canonical


class FakeCadServer(CleanroomServer):
    READ_COMMANDS = {"state_hash", "list_entities", "get_entity"}
    MUT_COMMANDS = {"add_line", "upsert_circle", "append_point_seq", "delete_all", "cleanroom_reset"}

    def __init__(self) -> None:
        self.entities: dict = {}
        self.reset_count = 0

    # -- helpers ---------------------------------------------------------
    def _state_digest(self) -> str:
        return hashlib.sha256(canonical(self.entities).encode()).hexdigest()

    # -- protocol --------------------------------------------------------
    def state_hash(self) -> str:
        return self._state_digest()

    def execute(self, name: str, args: dict) -> dict:
        try:
            if name in self.READ_COMMANDS:
                return {"ok": True, "data": self._read(name, args), "error": None}
            if name in self.MUT_COMMANDS:
                self._mutate(name, args)
                return {"ok": True, "data": {"applied": name, "entity_count": len(self.entities)}, "error": None}
            return {"ok": False, "data": None, "error": "unknown command: %s" % name}
        except ServerError as e:
            return {"ok": False, "data": None, "error": str(e)}
        except (TypeError, ValueError, KeyError) as e:
            return {"ok": False, "data": None, "error": "bad arguments: %s" % e}

    # -- command bodies ---------------------------------------------------
    def _read(self, name: str, args: dict) -> dict:
        if name == "state_hash":
            return {"state_hash": self._state_digest()}
        if name == "list_entities":
            return {"entities": sorted(self.entities.keys()), "count": len(self.entities)}
        eid = str(args.get("id", ""))
        return {"entity": self.entities.get(eid), "id": eid}

    def _mutate(self, name: str, args: dict) -> None:
        if name == "cleanroom_reset":
            self.entities = {}
            self.reset_count += 1
            return
        if name == "delete_all":
            self.entities = {}
            return
        if name == "add_line":
            eid = str(args.get("id", ""))
            if not eid:
                raise ServerError("add_line requires 'id'")
            self.entities[eid] = {"type": "line",
                                  "p1": [float(x) for x in args.get("p1", [0, 0])],
                                  "p2": [float(x) for x in args.get("p2", [0, 0])]}
            return
        if name == "upsert_circle":
            eid = str(args.get("id", ""))
            if not eid:
                raise ServerError("upsert_circle requires 'id'")
            self.entities[eid] = {"type": "circle",
                                  "center": [float(x) for x in args.get("center", [0, 0])],
                                  "r": float(args.get("r", 1.0))}
            return
        if name == "append_point_seq":
            eid = str(args.get("id", "seq"))
            seq = self.entities.setdefault(eid, {"type": "point_seq", "points": []})
            seq["points"] = seq.get("points", []) + [float(x) for x in args.get("point", [0, 0])]
            return
        raise ServerError("unhandled mutating command: %s" % name)
