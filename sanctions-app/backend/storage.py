"""
MongoDB storage layer with full snapshot history + a diff engine.

Collections:
  snapshots -> metadata for each fetch session
  entries   -> normalized entries tied to a snapshot_id
  changes   -> historical log of additions, deletions, and modifications
"""

import os
import json
from datetime import datetime, timezone
from bson.objectid import ObjectId
from pymongo import MongoClient, DESCENDING

# Pull the MongoDB connection URI from environment variables (configured later on Render)
# Fallback to local MongoDB if environment variable isn't present during local testing
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.environ.get("MONGO_DB_NAME", "sanctions_compliance")

_db_client = None

def _get_db():
    global _db_client
    if _db_client is None:
        _db_client = MongoClient(MONGO_URI)
    return _db_client[DB_NAME]


def init_db():
    """Initializes indexes to ensure blazing fast screenings and database lookups."""
    db = _get_db()
    
    # Optimize indexes for entries collection search queries
    db.entries.create_index([("snapshot_id", DESCENDING)])
    db.entries.create_index([("uid", DESCENDING)])
    db.entries.create_index([("source", DESCENDING)])
    
    # Optimize indexes for snapshots metadata
    # (Removed custom _id index definitions because MongoDB handles _id sorting natively)
    db.snapshots.create_index([("source", DESCENDING)])


def latest_snapshot(db, source):
    """Returns the most recent snapshot document for a specific source feed."""
    return db.snapshots.find_one({"source": source}, sort=[("_id", DESCENDING)])


def _entries_map(db, snapshot_id):
    """Retrieves all entries for a snapshot and maps them by UID into memory for diffing."""
    cursor = db.entries.find({"snapshot_id": snapshot_id})
    return {doc["uid"]: doc for doc in cursor}


def save_snapshot_and_diff(source, records, file_hash):
    """Persists a new snapshot and computes document diffs natively against the previous one."""
    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    prev = latest_snapshot(db, source)

    # Skip if an identical file hash has already been successfully processed
    if prev and prev.get("file_hash") == file_hash:
        return {"skipped": True, "reason": "unchanged file", "changes": []}

    # 1. Insert snapshot metadata
    snap_doc = {
        "source": source,
        "fetched_at": now,
        "entry_count": len(records),
        "file_hash": file_hash
    }
    snap_id = db.snapshots.insert_one(snap_doc).inserted_id

    # 2. Bulk insert normalized records natively
    if records:
        mongo_records = []
        for r in records:
            mongo_records.append({
                "snapshot_id": snap_id,
                "uid": r["uid"],
                "source": r["source"],
                "source_id": r["source_id"],
                "type": r["type"],
                "primary_name": r["primary_name"],
                "aliases": r["aliases"],        # Saved natively as a flexible BSON array list
                "programs": r["programs"],      # Saved natively as a flexible BSON array list
                "listed_on": r["listed_on"],
                "raw_fingerprint": r["raw_fingerprint"]
            })
        db.entries.insert_many(mongo_records)

    # 3. Compute Delta Changes (The Diff Engine)
    changes = []
    new_map = {r["uid"]: r for r in records}

    if prev is None:
        # First-time load configuration tracking
        for r in records:
            changes.append({
                "change_type": "added", "uid": r["uid"],
                "primary_name": r["primary_name"],
                "detail": {"initial_load": True}
            })
    else:
        old_map = _entries_map(db, prev["_id"])
        old_keys, new_keys = set(old_map.keys()), set(new_map.keys())

        # Discovered Additions
        for uid in new_keys - old_keys:
            r = new_map[uid]
            changes.append({"change_type": "added", "uid": uid, "primary_name": r["primary_name"], "detail": {}})
            
        # Discovered Removals
        for uid in old_keys - new_keys:
            r = old_map[uid]
            changes.append({"change_type": "removed", "uid": uid, "primary_name": r["primary_name"], "detail": {}})
            
        # Discovered Modifications via structural fingerprint mismatches
        for uid in old_keys & new_keys:
            if old_map[uid]["raw_fingerprint"] != new_map[uid]["raw_fingerprint"]:
                changes.append({
                    "change_type": "modified", "uid": uid,
                    "primary_name": new_map[uid]["primary_name"],
                    "detail": {
                        "old_name": old_map[uid]["primary_name"],
                        "new_name": new_map[uid]["primary_name"],
                    }
                })

    # Save tracking delta logs if modifications took place
    if changes:
        mongo_changes = []
        for ch in changes:
            mongo_changes.append({
                "run_at": now,
                "source": source,
                "change_type": ch["change_type"],
                "uid": ch["uid"],
                "primary_name": ch["primary_name"],
                "detail": ch["detail"]
            })
        db.changes.insert_many(mongo_changes)

    return {"skipped": False, "snapshot_id": str(snap_id), "entry_count": len(records), "changes": changes}


def recent_changes(limit=200):
    """Fetches the latest database change logs for audit tracking."""
    db = _get_db()
    cursor = db.changes.find({}, sort=[("_id", DESCENDING)]).limit(limit)
    out = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])  # Make ObjectId safely JSON serializable
        # Recreate expected relational detail_json string for the UI dashboard compatibility
        doc["detail_json"] = json.dumps(doc.get("detail", {}))
        out.append(doc)
    return out


def all_current_entries():
    """Aggregates the active snapshot data layers for current fuzzy screening routines."""
    db = _get_db()
    out = []
    sources = db.snapshots.distinct("source")
    
    for s in sources:
        snap = latest_snapshot(db, s)
        if not snap:
            continue
        cursor = db.entries.find({"snapshot_id": snap["_id"]})
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc["snapshot_id"] = str(doc["snapshot_id"])
            
            # Map native array values back into stringified JSON format 
            # so backend/ingest.py screen_name loop can parse them without crashes
            doc["aliases_json"] = json.dumps(doc.get("aliases", []))
            doc["programs_json"] = json.dumps(doc.get("programs", []))
            out.append(doc)
    return out


def previous_count(source):
    """Reads the exact item length of the latest historical track record."""
    db = _get_db()
    snap = latest_snapshot(db, source)
    return snap["entry_count"] if snap else None


def stats():
    """Calculates active overview parameters for client tracking screens."""
    db = _get_db()
    out = []
    sources = db.snapshots.distinct("source")
    for s in sources:
        snap = latest_snapshot(db, s)
        if snap:
            out.append({
                "source": s,
                "last": snap["fetched_at"],
                "count": snap["entry_count"]
            })
    return out
