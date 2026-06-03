"""
Ingestion runner + simple name screening.

run_ingest() fetches each enabled source, parses, normalizes, stores a
snapshot, and records the diff. screen_name() does basic fuzzy matching of a
query name against the current consolidated set.
"""

import hashlib
import json
import urllib.request

from sources import SOURCES
from parsers import PARSERS
from validation import validate_feed
import db as storage


def _fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "compliance-app/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def run_ingest():
    storage.init_db()
    report = []
    for key, cfg in SOURCES.items():
        if not cfg["enabled"]:
            report.append({"source": key, "status": "disabled",
                           "note": cfg["note"]})
            continue
        try:
            raw = _fetch(cfg["url"])
            file_hash = hashlib.sha256(raw).hexdigest()
            records = PARSERS[cfg["parser"]](raw)

            # --- validate structure BEFORE trusting/storing the snapshot ---
            prev = storage.previous_count(key)
            check = validate_feed(key, raw, records, prev_count=prev,
                                  min_records=cfg.get("min_records"))

            if check["status"] == "fail":
                # Do NOT store: a broken/changed feed must not overwrite good
                # data or generate a false "everything removed" diff.
                report.append({
                    "source": key, "status": "validation_failed",
                    "entries": len(records),
                    "issues": check["issues"],
                    "note": "Snapshot NOT stored. Feed structure changed or fetch failed — fix the parser/URL before trusting this source.",
                })
                continue

            result = storage.save_snapshot_and_diff(key, records, file_hash)

            base = {"source": key, "validation": check["status"],
                    "issues": check["issues"]}
            if result.get("skipped"):
                report.append({**base, "status": "unchanged",
                               "entries": len(records)})
            else:
                added = sum(1 for c in result["changes"] if c["change_type"] == "added")
                removed = sum(1 for c in result["changes"] if c["change_type"] == "removed")
                modified = sum(1 for c in result["changes"] if c["change_type"] == "modified")
                report.append({**base,
                               "status": "updated" if check["status"] == "ok" else "updated_with_warnings",
                               "entries": result["entry_count"],
                               "added": added, "removed": removed,
                               "modified": modified})
        except Exception as e:
            report.append({"source": key, "status": "error", "error": str(e)})
    # refresh the typo-suggestion vocabulary to reflect the latest lists
    try:
        import suggest
        suggest.invalidate_cache()
    except Exception:
        pass
    return report


# --- screening (uses the stacked matching engine) ---------------------------
from matching import best_match, match_score


def screen_name(query, threshold=0.80):
    entries = storage.all_current_entries()
    hits = []
    for e in entries:
        names = [e["primary_name"]] + json.loads(e["aliases_json"] or "[]")
        result = best_match(query, names)
        if result["score"] >= threshold:
            hits.append({
                "uid": e["uid"], "source": e["source"],
                "name": e["primary_name"], "type": e["type"],
                "programs": json.loads(e["programs_json"] or "[]"),
                "score": result["score"],
                "reasons": result["reasons"],
            })
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "screen":
        print(json.dumps(screen_name(" ".join(sys.argv[2:])), indent=2))
    else:
        print(json.dumps(run_ingest(), indent=2))
