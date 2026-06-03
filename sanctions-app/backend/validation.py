"""
Feed structure validation.

Goal: detect when a source has changed its format (or returned something
unexpected — an error page, an empty file, a redirect to HTML) BEFORE we
parse and diff it. Without this, a structural change silently produces either
zero records (looks like "everything was removed!") or garbage that floods the
change feed with false modifications.

Each source has a lightweight "contract": things that must be true of a healthy
feed. Validation runs in two stages:

  1. PRE-PARSE  : is this even the right kind of document? (XML? expected root?
                  expected record elements present? not an HTML error page?)
  2. POST-PARSE : did we get a sane number of records, and do sampled records
                  have the fields we depend on?

validate_feed() returns a report with status ok | warn | fail and a list of
human-readable issues. ingest.py uses this to decide whether to trust + store a
snapshot, or to skip it and raise a warning instead.
"""

from lxml import etree


def _localname(tag):
    try:
        return etree.QName(tag).localname
    except Exception:
        return str(tag)


# Per-source structural contracts.
# min_records is a floor: real lists are large, so a tiny count almost always
# means a broken fetch rather than a genuinely empty list.
CONTRACTS = {
    "OFAC": {
        "record_tag": "sdnEntry",
        "min_records": 1000,
        "required_fields": ["uid"],          # at least the id must be present
        "name_fields": ["firstName", "lastName"],
    },
    "UN": {
        "record_tag": "INDIVIDUAL",
        "min_records": 100,
        "required_fields": ["DATAID"],
        "name_fields": ["FIRST_NAME", "SECOND_NAME"],
    }
}


def pre_parse_check(source, raw_bytes):
    """Stage 1: Surface structural blockages before handing off to individual parsers."""
    issues = []
    status = "ok"

    if not raw_bytes or len(raw_bytes.strip()) == 0:
        return {"status": "fail", "issues": ["Downloaded feed data is completely empty (0 bytes)"]}

    # Catch common proxy, CDN or firewall redirects to custom HTML maintenance pages
    prefix = raw_bytes.strip()[:200].lower()
    if prefix.startswith(b"<!doctype html") or b"<html" in prefix:
        return {"status": "fail", "issues": ["Received HTML text instead of valid compliance XML schema"]}

    # Test basic structural parse tree integrity
    try:
        parser = etree.XMLParser(recover=False)
        root = etree.fromstring(raw_bytes, parser=parser)
    except Exception as e:
        return {"status": "fail", "issues": [f"Malformed or truncated XML structure: {str(e)}"]}

    # Verify the specific record container tags are found inside the document
    contract = CONTRACTS.get(source)
    if contract:
        found_tag = False
        # scan a small subset to verify entry layout signatures
        for elem in root.iter():
            if _localname(elem.tag) == contract["record_tag"]:
                found_tag = True
                break
        if not found_tag:
            issues.append(f"Expected record tag '{contract['record_tag']}' is absent from document hierarchy")
            status = "fail"

    return {"status": status, "issues": issues}


def post_parse_check(source, records, prev_count=None):
    """Stage 2: Statistical logic limits ensuring data continuity constraints."""
    issues = []
    status = "ok"
    n = len(records)

    contract = CONTRACTS.get(source, {"min_records": 10})

    if n < contract["min_records"]:
        issues.append(f"Suspiciously small entry subset extracted ({n}). Minimum safe layout threshold is {contract['min_records']}.")
        status = "fail"

    # Delta sanity boundary checks: flag drastic data evaporation anomalies
    if prev_count and prev_count > 0:
        drop_ratio = (prev_count - n) / prev_count
        if drop_ratio > 0.40:
            issues.append(f"Drastic dataset contraction risk: record pool dropped by {(drop_ratio*100):.1f}% vs historical version.")
            status = "warn"

    # Field-level sampling: do records actually carry the fields we depend on?
    sample = records[: min(50, n)]
    missing_name = sum(
        1 for r in sample
        if not r.get("primary_name") or r["primary_name"] == "(unnamed)")
    if missing_name > len(sample) * 0.5:
        issues.append(
            f"{missing_name}/{len(sample)} sampled records have no usable name — "
            "name field mapping may have changed")
        status = "warn"

    missing_id = sum(1 for r in sample if not r.get("source_id"))
    if missing_id > 0:
        issues.append(
            f"{missing_id}/{len(sample)} sampled records have no source id")
        status = "warn"

    return {"status": status, "issues": issues, "record_count": n}


def validate_feed(source, raw, records, prev_count=None):
    """Combine both stages into one report. Worst status wins."""
    pre = pre_parse_check(source, raw)
    if pre["status"] == "fail":
        return {"source": source, "status": "fail", "stage": "pre-parse",
                "issues": pre["issues"]}

    post = post_parse_check(source, records, prev_count)
    issues = pre["issues"] + post["issues"]
    order = {"ok": 0, "warn": 1, "fail": 2}
    status = pre["status"] if order[pre["status"]] >= order[post["status"]] else post["status"]

    return {"source": source, "status": status, "stage": "post-parse", "issues": issues, "entry_count": n if 'n' in locals() else len(records)}
