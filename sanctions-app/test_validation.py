"""Verify the validation layer catches real-world feed failure modes."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from parsers import parse_ofac
from validation import validate_feed, pre_parse_check

def ofac_xml(n, name_first="firstName", name_last="lastName", id_tag="uid"):
    entries = "".join(
        f"<sdnEntry><{id_tag}>{i}</{id_tag}>"
        f"<{name_first}>Person</{name_first}><{name_last}>Number{i}</{name_last}>"
        f"<sdnType>Individual</sdnType></sdnEntry>"
        for i in range(n))
    return (f'<sdnList xmlns="http://tempuri.org/sdnList.xsd">{entries}</sdnList>').encode()

def run(label, raw, prev=None):
    try:
        recs = parse_ofac(raw) if raw.strip().startswith(b"<sdn") or b"sdnList" in raw[:80] else []
    except Exception:
        recs = []
    rep = validate_feed("OFAC", raw, recs, prev_count=prev)
    print(f"\n[{label}]")
    print(f"  status: {rep['status'].upper()}  (stage: {rep['stage']})")
    for i in rep["issues"]:
        print(f"    - {i}")
    return rep

print("="*64)
print("VALIDATION TEST — does it catch feed drift / bad fetches?")
print("="*64)

# 1. Healthy feed, large enough.
r1 = run("Healthy feed (1500 records)", ofac_xml(1500))
assert r1["status"] == "ok", "healthy feed should pass"

# 2. HTML error page instead of XML (very common: login/redirect/maintenance).
r2 = run("HTML error page returned", b"<!DOCTYPE html><html><body>503 Service Unavailable</body></html>")
assert r2["status"] == "fail"

# 3. Malformed / truncated XML.
r3 = run("Truncated XML", b'<sdnList><sdnEntry><uid>1</uid><lastName>Bro')
assert r3["status"] == "fail"

# 4. Schema change: source renamed the record element.
schema_changed = ofac_xml(1500).replace(b"sdnEntry", b"entityRecord")
r4 = run("Schema change (record element renamed)", schema_changed)
assert r4["status"] == "fail"

# 5. Schema change: name fields renamed -> parses but records have no names.
name_changed = ofac_xml(1500, name_first="givenName", name_last="surname")
r5 = run("Schema change (name fields renamed)", name_changed, prev=1500)
assert r5["status"] in ("warn", "fail")

# 6. Suspicious collapse: feed suddenly tiny vs previous snapshot.
r6 = run("Count collapse (1500 -> 50)", ofac_xml(50), prev=1500)
assert r6["status"] in ("warn", "fail")

# 7. Healthy but modest change vs previous (should stay OK).
r7 = run("Normal small change (1500 -> 1520)", ofac_xml(1520), prev=1500)
assert r7["status"] == "ok"

print("\n" + "="*64)
print("ALL VALIDATION CHECKS PASSED — drift and bad fetches are caught.")
print("="*64)
