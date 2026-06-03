"""
Fuzzy name matching engine.
Includes basic string similarity metrics, token cleaning, phonetic mapping,
and name variation generators. Satisfies all compliance pipeline modules.
"""

import re

# Internal lookup cache to support vocabulary structures in suggest.py
_ALIAS_LOOKUP = {}

def normalize(text):
    """Lowercases string and strips trailing/leading whitespaces."""
    if not text:
        return ""
    return text.lower().strip()

def tokens(text):
    """Split text into lowercase alphanumeric components, removing noise punctuation."""
    if not text:
        return []
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    return [t for t in cleaned.split() if t]

def phonetic_key(word):
    """
    Generates a Soundex-style phonetic representation code for names.
    Satisfies requirements for typo suggestions and alternative key sound maps.
    """
    if not word:
        return ""
    word = word.upper()
    first_letter = word[0]
    
    # Character conversion dictionary mapping equivalent sounds
    mappings = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
    }
    
    code = first_letter
    prev_val = mappings.get(first_letter, '0')
    
    for char in word[1:]:
        val = mappings.get(char, '0')
        if val != '0':
            if val != prev_val:
                code += val
                prev_val = val
        else:
            prev_val = '0'
            
    # Normalize to a standard 4 character string pattern
    code = code.replace('0', '')
    if len(code) < 4:
        code += '0' * (4 - len(code))
    return code[:4]

def phonetic_code(word):
    """Fallback alias reference redirecting directly to phonetic_key mapping."""
    return phonetic_key(word)

def levenshtein_similarity(s1, s2):
    """Calculates normalized Levenshtein similarity score between 0.0 and 1.0."""
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
        
    rows = len(s1) + 1
    cols = len(s2) + 1
    distance = [[0] * cols for _ in range(rows)]

    for i in range(1, rows):
        distance[i][0] = i
    for j in range(1, cols):
        distance[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            if s1[i-1] == s2[j-1]:
                cost = 0
            else:
                cost = 1
            distance[i][j] = min(
                distance[i-1][j] + 1,      # Deletion
                distance[i][j-1] + 1,      # Insertion
                distance[i-1][j-1] + cost  # Substitution
            )

    lev_dist = distance[rows-1][cols-1]
    max_len = max(len(s1), len(s2))
    return 1.0 - (lev_dist / max_len)

def _lev_ratio(s1, s2):
    """Alias helper ratio mapping required by suggest module."""
    return levenshtein_similarity(s1, s2)

def match_score(name1, name2):
    """Wrapper function evaluating similarity between two singular name targets."""
    return levenshtein_similarity(name1, name2)

def best_match(query, target_names):
    """
    Evaluates a query string against an array of target names/aliases.
    Returns the maximum score observed and specific reasons.
    """
    if not query or not target_names:
        return {"score": 0.0, "reasons": ["Empty query or target dataset."]}

    highest_score = 0.0
    matched_target = ""

    q_clean = " ".join(tokens(query))

    for target in target_names:
        if not target:
            continue
        t_clean = " ".join(tokens(target))
        
        score = levenshtein_similarity(q_clean, t_clean)
        if score > highest_score:
            highest_score = score
            matched_target = target

    reasons = []
    if highest_score >= 0.85:
        reasons.append(f"Strong spelling profile similarity matched against '{matched_target}'")
    elif highest_score >= 0.75:
        reasons.append(f"Fuzzy character transposition layout matched against '{matched_target}'")
    else:
        reasons.append("No matches detected above validation benchmarks.")

    return {
        "score": round(highest_score, 4),
        "reasons": reasons
    }

def generate_variants(name):
    """Produces structural spelling layout variations for an identity string."""
    tks = tokens(name)
    if not tks:
        return []
    variants = [" ".join(tks)]
    if len(tks) > 1:
        variants.append("".join(tks))
    return list(set(variants))
