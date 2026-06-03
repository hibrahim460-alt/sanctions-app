"""
Source definitions for sanctions / watchlist feeds.

Only sources that publish official machine-readable feeds are enabled for
automatic ingestion. EU requires an auth token; INTERPOL has no feed and
prohibits scraping, so it is present but disabled.
"""

SOURCES = {
    "OFAC_SDN": {
        "name": "OFAC SDN List (Specially Designated Nationals)",
        "enabled": True,
        "format": "xml",
        # Current Sanctions List Service (SLS) endpoint. The old
        # treasury.gov/ofac/downloads/* URLs now redirect here and the new host
        # REQUIRES a User-Agent header (the fetcher sends one).
        "url": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        "parser": "parse_ofac",
        "min_records": 1000,   # SDN list is large (thousands)
        "note": "Main OFAC blocked-persons list. Large. Updated on enforcement actions.",
    },
    "OFAC_CONS": {
        "name": "OFAC Consolidated List (non-SDN: SSI, FSE, etc.)",
        "enabled": True,
        "format": "xml",
        "url": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/CONSOLIDATED.XML",
        "parser": "parse_ofac",
        "min_records": 50,     # non-SDN list is small (hundreds); 442 is normal
        "note": "Supplementary non-SDN lists. Small by design. Some sub-lists may be empty.",
    },
    "UN": {
        "name": "UN Security Council Consolidated List",
        "enabled": True,
        "format": "xml",
        "url": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
        "parser": "parse_un",
        "min_records": 100,
        "note": "Official UN canonical XML feed.",
    },
    "EU": {
        "name": "EU Consolidated Financial Sanctions List",
        "enabled": False,  # requires a free auth token from the EU FSF system
        "format": "xml",
        "url": "",  # set this to your tokenised EU FSF download URL
        "parser": "parse_eu",
        "min_records": 100,
        "note": "Requires a free EU FSF login token. Set the URL and enable once you have it.",
    },
    "INTERPOL": {
        "name": "INTERPOL Red Notices",
        "enabled": False,  # no official bulk feed; scraping violates ToS
        "format": "manual",
        "url": "",
        "parser": None,
        "note": "No official feed. Add entries manually or via a licensed provider. Do NOT scrape.",
    },
}
