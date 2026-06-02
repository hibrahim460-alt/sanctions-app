"""
SQLite storage with full snapshot history + a diff engine.

Tables:
  snapshots(id, source, fetched_at, entry_count, file_hash)
  entries(snapshot_id, uid, source, source_id, type, primary_name,
          aliases_json, programs_json, listed_on, raw_fingerprint)
  changes(id, run_at, source, change_type, uid, primary_name, detail_json)

This gives you the audit trail regulators typically ask for: what the list
looked like at each fetch, and exactly what changed between fetches.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sanctions.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT, fetched_at TEXT, entry_count INTEGER, file_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS entries(
            snapshot_id INTEGER, uid TEXT, source TEXT, source_id TEXT,
            type TEXT, primary_name TEXT, aliases_json TEXT,
            programs_json TEXT, listed_on TEXT, raw_fingerprint TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_entries_snap ON entries(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_entries_uid ON entries(uid);
        CREATE TABLE IF NOT EXISTS changes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT, source TEXT, change_type TEXT,
            uid TEXT, primary_name TEXT, detail_json TEXT
        );
        """)


def latest_snapshot(c, source):
    return c.execute(
        "SELECT * FROM snapshots WHERE source=? ORDER BY id DESC LIMIT 1",
        (source,)).fetchone()


def _entries_map(c, snapshot_id):
    rows = c.execute("SELECT * FROM entries WHERE snapshot_id=?",
                     (snapshot_id,)).fetchall()
    return {r["uid"]: r for r in rows}


def save_snapshot_and_diff(source, records, file_hash):
    """Persist a new snapshot and compute the diff against the previous one.
    Returns the list of change dicts."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        prev = latest_snapshot(c, source)

        # skip if identical file we've already ingested
        if prev and prev["file_hash"] == file_hash:
            return {"skipped": True, "reason": "unchanged file", "changes": []}

        cur = c.execute(
            "INSERT INTO snapshots(source,fetched_at,entry_count,file_hash) "
            "VALUES(?,?,?,?)", (source, now, len(records), file_hash))
        snap_id = cur.lastrowid

        c.executemany(
            "INSERT INTO entries(snapshot_id,uid,source,source_id,type,"
            "primary_name,aliases_json,programs_json,listed_on,raw_fingerprint)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(snap_id, r["uid"], r["source"], r["source_id"], r["type"],
              r["primary_name"], json.dumps(r["aliases"]),
              json.dumps(r["programs"]), r["listed_on"], r["raw_fingerprint"])
             for r in records])

        changes = []
        new_map = {r["uid"]: r for r in records}

        if prev is None:
            # first ingest: everything is an addition (recorded compactly)
            for r in records:
                changes.append({"change_type": "added", "uid": r["uid"],
                                "primary_name": r["primary_name"],
                                "detail": {"initial_load": True}})
        else:
            old_map = _entries_map(c, prev["id"])
            old_keys, new_keys = set(old_map), set(new_map)

            for uid in new_keys - old_keys:
                r = new_map[uid]
                changes.append({"change_type": "added", "uid": uid,
                                "primary_name": r["primary_name"], "detail": {}})
            for uid in old_keys - new_keys:
                r = old_map[uid]
                changes.append({"change_type": "removed", "uid": uid,
                                "primary_name": r["primary_name"], "detail": {}})
            for uid in old_keys & new_keys:
                if old_map[uid]["raw_fingerprint"] != new_map[uid]["raw_fingerprint"]:
                    changes.append({
                        "change_type": "modified", "uid": uid,
                        "primary_name": new_map[uid]["primary_name"],
                        "detail": {
                            "old_name": old_map[uid]["primary_name"],
                            "new_name": new_map[uid]["primary_name"],
                        }})

        c.executemany(
            "INSERT INTO changes(run_at,source,change_type,uid,primary_name,"
            "detail_json) VALUES(?,?,?,?,?,?)",
            [(now, source, ch["change_type"], ch["uid"], ch["primary_name"],
              json.dumps(ch["detail"])) for ch in changes])

        return {"skipped": False, "snapshot_id": snap_id,
                "entry_count": len(records), "changes": changes}


def recent_changes(limit=200):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM changes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def all_current_entries():
    """Latest snapshot per source, flattened — used for screening."""
    out = []
    with _conn() as c:
        sources = [r["source"] for r in c.execute(
            "SELECT DISTINCT source FROM snapshots").fetchall()]
        for s in sources:
            snap = latest_snapshot(c, s)
            if not snap:
                continue
            for r in c.execute("SELECT * FROM entries WHERE snapshot_id=?",
                               (snap["id"],)).fetchall():
                out.append(dict(r))
    return out


def previous_count(source):
    """Entry count of the most recent stored snapshot for this source, or None."""
    with _conn() as c:
        snap = latest_snapshot(c, source)
        return snap["entry_count"] if snap else None


def stats():
    with _conn() as c:
        rows = c.execute(
            "SELECT source, MAX(fetched_at) AS last, "
            "(SELECT entry_count FROM snapshots s2 WHERE s2.source=s1.source "
            " ORDER BY id DESC LIMIT 1) AS count "
            "FROM snapshots s1 GROUP BY source").fetchall()
        return [dict(r) for r in rows]
