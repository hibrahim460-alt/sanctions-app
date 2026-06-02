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
        "name_fields": ["firstName", "lastName"],  # need at least one of these
    },
    "UN": {
        "record_tag": ("INDIVIDUAL", "ENTITY"),
        "min_records": 100,
        "required_fields": ["DATAID"],
        "name_fields": ["FIRST_NAME", "SECOND_NAME"],
    },
    "EU": {
        "record_tag": "sanctionEntity",
        "min_records": 100,
        "required_fields": [],
        "name_fields": ["nameAlias"],
    },
}


def _looks_like_html(raw):
    head = raw[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def pre_parse_check(source, raw):
    """Stage 1: validate the raw bytes look like the expected XML feed."""
    issues = []
    contract = CONTRACTS.get(source)
    if contract is None:
        return {"status": "warn", "issues": [f"No contract defined for {source}"]}

    if not raw or len(raw.strip()) == 0:
        return {"status": "fail", "issues": ["Empty response from feed"]}

    if _looks_like_html(raw):
        return {"status": "fail",
                "issues": ["Response looks like an HTML page (error/redirect/login), not the XML feed"]}

    # Must parse as XML at all.
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError as e:
        return {"status": "fail", "issues": [f"Not well-formed XML: {e}"]}

    # Expected record element must appear somewhere.
    tags = contract["record_tag"]
    if isinstance(tags, str):
        tags = (tags,)
    found = any(_localname(el.tag) in tags for el in root.iter())
    if not found:
        issues.append(
            f"Expected record element {tags} not found — feed structure may have changed")
        return {"status": "fail", "issues": issues, "root": _localname(root.tag)}

    return {"status": "ok", "issues": issues, "root": _localname(root.tag)}


def post_parse_check(source, records, prev_count=None):
    """Stage 2: validate the parsed records are sane in count and shape."""
    issues = []
    status = "ok"
    contract = CONTRACTS.get(source, {})
    n = len(records)

    # Count floor.
    floor = contract.get("min_records", 1)
    if n == 0:
        return {"status": "fail",
                "issues": ["Parser produced 0 records — likely a schema change"]}
    if n < floor:
        issues.append(
            f"Only {n} records parsed (expected at least ~{floor}); possible partial fetch or schema change")
        status = "warn"

    # Sudden large swing vs. the previous snapshot is suspicious.
    if prev_count:
        if prev_count > 0:
            change_ratio = abs(n - prev_count) / prev_count
            if change_ratio > 0.40:
                issues.append(
                    f"Record count moved {prev_count} -> {n} "
                    f"({change_ratio*100:.0f}% swing); review before trusting the diff")
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
    return {"source": source, "status": status,
            "stage": "post-parse" if post["status"] != "ok" else "complete",
            "issues": issues, "record_count": post.get("record_count")}
