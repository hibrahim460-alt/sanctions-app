"""
Parsers convert each source's native XML into a common normalized record:

{
    "uid": "<source>:<source_id>",
    "source": "OFAC" | "UN" | "EU" | ...,
    "source_id": str,
    "type": "individual" | "entity" | "unknown",
    "primary_name": str,
    "aliases": [str, ...],
    "programs": [str, ...],
    "listed_on": str | None,
    "raw_fingerprint": str,   # hash of the fields we care about, for diffing
}
"""

import hashlib
from lxml import etree


def _fingerprint(rec):
    """Stable hash of the meaningful fields so we can detect modifications."""
    basis = "|".join([
        rec.get("primary_name", ""),
        ";".join(sorted(rec.get("aliases", []))),
        ";".join(sorted(rec.get("programs", []))),
        rec.get("type", ""),
        rec.get("listed_on") or "",
    ])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _localname(tag):
    return etree.QName(tag).localname if tag else tag


# ----------------------------------------------------------------------------
# OFAC consolidated.xml
# ----------------------------------------------------------------------------
def parse_ofac(xml_bytes):
    records = []
    root = etree.fromstring(xml_bytes)
    ns = {"o": root.nsmap.get(None, "")} if root.nsmap.get(None) else {}

    def find(el, path):
        if ns:
            return el.findall(path, ns)
        return el.findall(path.replace("o:", ""))

    for entry in root.iter():
        if _localname(entry.tag) != "sdnEntry":
            continue

        uid = (entry.findtext("{*}uid") or "").strip()
        first = (entry.findtext("{*}firstName") or "").strip()
        last = (entry.findtext("{*}lastName") or "").strip()
        sdn_type = (entry.findtext("{*}sdnType") or "").strip().lower()
        primary = " ".join(p for p in [first, last] if p).strip()

        aliases = []
        for aka in entry.iter():
            if _localname(aka.tag) == "aka":
                a_first = (aka.findtext("{*}firstName") or "").strip()
                a_last = (aka.findtext("{*}lastName") or "").strip()
                full = " ".join(p for p in [a_first, a_last] if p).strip()
                if full:
                    aliases.append(full)

        programs = [p.text.strip() for p in entry.iter()
                    if _localname(p.tag) == "program" and p.text]

        rtype = "individual" if sdn_type == "individual" else (
            "entity" if sdn_type else "unknown")

        rec = {
            "uid": f"OFAC:{uid}",
            "source": "OFAC",
            "source_id": uid,
            "type": rtype,
            "primary_name": primary or "(unnamed)",
            "aliases": sorted(set(aliases)),
            "programs": sorted(set(programs)),
            "listed_on": None,
        }
        rec["raw_fingerprint"] = _fingerprint(rec)
        records.append(rec)
    return records


# ----------------------------------------------------------------------------
# UN consolidated.xml
# ----------------------------------------------------------------------------
def parse_un(xml_bytes):
    records = []
    root = etree.fromstring(xml_bytes)

    for entry in root.iter():
        ln = _localname(entry.tag)
        if ln not in ("INDIVIDUAL", "ENTITY"):
            continue
        rtype = "individual" if ln == "INDIVIDUAL" else "entity"

        dataid = (entry.findtext("{*}DATAID") or "").strip()
        name_parts = []
        for f in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME"):
            v = entry.findtext("{*}" + f)
            if v and v.strip():
                name_parts.append(v.strip())
        primary = " ".join(name_parts).strip()

        aliases = []
        for alias in entry.iter():
            if _localname(alias.tag) in ("INDIVIDUAL_ALIAS", "ENTITY_ALIAS"):
                an = alias.findtext("{*}ALIAS_NAME")
                if an and an.strip():
                    aliases.append(an.strip())

        programs = []
        ref = entry.findtext("{*}UN_LIST_TYPE")
        if ref and ref.strip():
            programs.append(ref.strip())

        listed = entry.findtext("{*}LISTED_ON")

        rec = {
            "uid": f"UN:{dataid}",
            "source": "UN",
            "source_id": dataid,
            "type": rtype,
            "primary_name": primary or "(unnamed)",
            "aliases": sorted(set(aliases)),
            "programs": sorted(set(programs)),
            "listed_on": (listed or "").strip() or None,
        }
        rec["raw_fingerprint"] = _fingerprint(rec)
        records.append(rec)
    return records


# ----------------------------------------------------------------------------
# EU (placeholder — schema varies; fill in once you have the token + sample)
# ----------------------------------------------------------------------------
def parse_eu(xml_bytes):
    # The EU FSF schema uses <sanctionEntity> with <nameAlias> children.
    # Left minimal intentionally; wire up against a real sample file.
    records = []
    root = etree.fromstring(xml_bytes)
    for entry in root.iter():
        if _localname(entry.tag) != "sanctionEntity":
            continue
        sid = entry.get("logicalId") or entry.get("euReferenceNumber") or ""
        names = [n.get("wholeName") for n in entry.iter()
                 if _localname(n.tag) == "nameAlias" and n.get("wholeName")]
        primary = names[0] if names else "(unnamed)"
        rec = {
            "uid": f"EU:{sid}",
            "source": "EU",
            "source_id": sid,
            "type": "unknown",
            "primary_name": primary,
            "aliases": sorted(set(names[1:])),
            "programs": [],
            "listed_on": None,
        }
        rec["raw_fingerprint"] = _fingerprint(rec)
        records.append(rec)
    return records


PARSERS = {
    "parse_ofac": parse_ofac,
    "parse_un": parse_un,
    "parse_eu": parse_eu,
}
