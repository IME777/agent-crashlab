"""Import published evidence as explicitly recorded history, never fresh runs."""

import argparse
import hashlib
import json
from pathlib import Path

from crashlab.store import Store, now


def seed(root: Path, reports: list[Path]) -> int:
    store = Store(root)
    imported = 0
    for path in reports:
        source_bytes = path.read_bytes()
        payload = json.loads(source_bytes)
        for case in payload.get("cases", []):
            run = case["report"]
            events = run.pop("events")
            run["imported_evidence"] = {"source_file": path.name,
                                        "sha256": hashlib.sha256(source_bytes).hexdigest(), "at": now()}
            run["notes"].append("Imported recorded evidence from a published report; not executed on this host.")
            with store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT 1 FROM runs WHERE id=?", (run["id"],)).fetchone():
                    continue
                db.execute("INSERT INTO runs VALUES(?,?)", (run["id"], json.dumps(run)))
                for event in events:
                    db.execute("INSERT INTO events(run_id,at,kind,message,detail) VALUES(?,?,?,?,?)",
                               (run["id"], event["at"], event["kind"], event["message"], json.dumps(event["detail"])))
                store._event(db, run["id"], "recorded_evidence_imported",
                             "Imported an existing real-run report; not a new inference on this host")
                imported += 1
    return imported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--reports", type=Path, nargs="+", default=[Path("examples/live-check-initial.json"), Path("examples/live-check.json")])
    args = parser.parse_args()
    print(json.dumps({"imported_runs": seed(args.data, args.reports)}))


if __name__ == "__main__":
    main()
