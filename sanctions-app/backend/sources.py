"""
Source definitions for sanctions / watchlist feeds.

Only sources that publish official machine-readable feeds are enabled for
automatic ingestion. EU requires an auth token; INTERPOL has no feed and
prohibits scraping, so it is present but disabled.
"""

SOURCES = {
    "OFAC": {
        "name": "OFAC (US Treasury) Consolidated List",
        "enabled": True,
        "format": "xml",
        # Modern OFAC consolidated list (SDN + non-SDN), machine-readable.
        "url": "https://www.treasury.gov/ofac/downloads/consolidated/consolidated.xml",
        "parser": "parse_ofac",
        "note": "Official OFAC feed. Updated on enforcement actions (often several times/week).",
    },
    "UN": {
        "name": "UN Security Council Consolidated List",
        "enabled": True,
        "format": "xml",
        "url": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
        "parser": "parse_un",
        "note": "Official UN canonical XML feed.",
    },
    "EU": {
        "name": "EU Consolidated Financial Sanctions List",
        "enabled": False,  # requires a free auth token from the EU FSF system
        "format": "xml",
        "url": "",  # set this to your tokenised EU FSF download URL
        "parser": "parse_eu",
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
