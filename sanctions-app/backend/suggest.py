"""
Input typo suggestions for screening queries.

DESIGN PRINCIPLE (important for compliance):
We never silently rewrite a user's query. The query of record is exactly what
the user typed, and screening always runs on that raw input (the fuzzy +
phonetic matcher already tolerates typos). This module only *suggests* cleaner
spellings, drawn from the real name tokens present on the loaded lists, so a
human can choose to refine and re-screen. Both the original and any accepted
suggestion should be logged.

How it works:
  - Build a vocabulary of name tokens (+ frequencies) from current list entries.
  - For each query token, if it isn't already a known token, find close
    vocabulary tokens by edit distance and phonetic key.
  - Return ranked "did you mean" candidates per token, plus whole-name
    suggestions assembled from the best per-token candidates.
"""

import json
from collections import Counter

import os
import sys

# Guarantee this module can locate sibling modules like matching.py
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import storage
from matching import (normalize, tokens, _lev_ratio, _ALIAS_LOOKUP)

# Look safely for phonetic_key or fall back gracefully
try:
    from matching import phonetic_key
except ImportError:
    from matching import phonetic_code as phonetic_key

# module-level cache of the vocabulary so we don't rebuild every keystroke
_VOCAB = None              # Counter: token -> frequency
_PHON_INDEX = None         # phonetic_key -> set(tokens)


def build_vocabulary(force=False):
    """Scan current list entries (primary names + aliases) into a token vocab."""
    global _VOCAB, _PHON_INDEX
    if _VOCAB is not None and not force:
        return _VOCAB

    vocab = Counter()
    phon = {}
    
    try:
        entries = storage.all_current_entries()
    except Exception:
        entries = []

    for e in entries:
        # Collect primary name + any aliases
        raw_names = [e["primary_name"]]
        if e.get("aliases_json"):
            try:
                raw_names.extend(json.loads(e["aliases_json"]))
            except Exception:
                pass
        
        for name in raw_names:
            for t in tokens(name):
                vocab[t] += 1
                pk = phonetic_key(t)
                if pk:
                    if pk not in phon:
                        phon[pk] = set()
                    phon[pk].add(t)

    _VOCAB = vocab
    _PHON_INDEX = phon
    return _VOCAB


def suggest(query, max_per_token=3, max_whole=2, threshold=0.70):
    """Analyze query for typos and generate 'did you mean' suggestions from list vocab."""
    build_vocabulary()
    
    qtokens = tokens(query)
    if not qtokens:
        return {
            "query": query,
            "has_suggestions": False,
            "tokens": [],
            "did_you_mean": [],
        }

    per_token = []
    any_correction = False

    for t in qtokens:
        # If it's a known common word or perfectly matches a vocabulary word, no correction needed
        if t in _VOCAB or len(t) <= 2:
            per_token.append({"input": t, "suggestions": []})
            continue

        # Look up candidates via phonetics first (sound-alikes)
        pk = phonetic_key(t)
        candidates = _PHON_INDEX.get(pk, set()) if pk else set()

        # Also check alias clusters
        if t in _ALIAS_LOOKUP:
            candidates.update(_ALIAS_LOOKUP[t])

        # If phonetic index is sparse, fall back to scanning nearby high-freq vocab tokens
        if len(candidates) < 5:
            # simple length filter to avoid scanning the entire database
            candidates.update(k for k in _VOCAB.keys() if abs(len(k) - len(t)) <= 2)

        scored = []
        for cand in candidates:
            if cand == t:
                continue
            ratio = _lev_ratio(t, cand)
            if ratio >= threshold:
                # Score components: similarity weighted by token prominence in database
                freq_bonus = min(0.05, (_VOCAB[cand] / 10000))
                score = ratio + freq_bonus
                scored.append({"token": cand, "confidence": round(score, 2)})

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        cands = scored[:max_per_token]
        
        per_token.append({"input": t, "suggestions": cands})
        if cands:
            any_correction = True

    whole = []
    if any_correction:
        # Build alternative phrases based on top choices
        best_tokens = []
        for slot in per_token:
            if slot["suggestions"]:
                best_tokens.append(slot["suggestions"][0]["token"])
            else:
                best_tokens.append(slot["input"])
        candidate = " ".join(best_tokens)
        if candidate != " ".join(qtokens):
            whole.append(candidate)

        # Build secondary choice if available
        for i, slot in enumerate(per_token):
            if len(slot["suggestions"]) > 1:
                alt = best_tokens[:]
                alt[i] = slot["suggestions"][1]["token"]
                alt_str = " ".join(alt)
                if alt_str not in whole and alt_str != " ".join(qtokens):
                    whole.append(alt_str)
            if len(whole) >= max_whole:
                break

    return {
        "query": query,
        "has_suggestions": any_correction,
        "tokens": per_token,
        "did_you_mean": whole[:max_whole],
        "note": "Suggestions only — screening runs on your original input.",
    }


def invalidate_cache():
    """Call after an ingest so the vocabulary reflects the latest lists."""
    global _VOCAB, _PHON_INDEX
    _VOCAB = None
    _PHON_INDEX = None
