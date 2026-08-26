#!/usr/bin/env python3
"""
Class-aware pronunciation engine for TTS front-end (detection + normalization).

Three automatable mispronunciation classes, each with its own heuristic:

  A. SCIENTIFIC ALPHANUMERIC tokens  — TMEM174, SUCNR1, aquaporin-4, GLP-1
     -> deterministic expansion to spoken form (letters spelled, numbers as words)

  B. HETERONYMS / HOMOGRAPHS         — compound (noun COM-pound vs verb com-POUND),
     record, present, moderate, estimate ...  -> POS tagger picks the sense

  C. HARD / STOCHASTIC words         — autophagy (right once, wrong next)
     -> not predictable from text; handled by a verified phonetic lock list +
        the ASR self-verify re-roll loop, NOT here.

This module is the WHAT-should-be-said layer. The spelling that actually steers
Qwen3-TTS is confirmed separately by the ASR self-verify loop, because the old
caps/hyphen respell ("COM-pounds") is not trusted to move the model.

Two entry points:
  analyze(text)   -> list of detected items by class  (for mining / QA reports)
  normalize(text) -> text with expansions+disambiguations applied (pipeline use)

POS tagging uses NLTK if available; otherwise a conservative context fallback.
"""
import re, json, os

# --------------------------------------------------------------------------- #
# POS tagger (pluggable: NLTK preferred, lightweight fallback otherwise)
# --------------------------------------------------------------------------- #
_TAGGER = None
def _get_tagger():
    global _TAGGER
    if _TAGGER is not None:
        return _TAGGER
    try:
        import nltk
        from nltk import pos_tag, word_tokenize
        nltk.data.find('taggers/averaged_perceptron_tagger_eng')
        def tag(sentence):
            return pos_tag(word_tokenize(sentence))
        _TAGGER = tag
    except Exception:
        _TAGGER = None
    return _TAGGER

# Conservative fallback: infer noun vs verb from the immediately preceding token.
_DET = {'the', 'a', 'an', 'this', 'that', 'these', 'those', 'its', 'their',
        'his', 'her', 'our', 'your', 'my', 'some', 'any', 'each', 'no', 'more',
        'most', 'such', 'one', 'two', 'three', 'new', 'same'}
_VERB_CUE = {'to', 'will', 'would', 'can', 'could', 'may', 'might', 'must',
             'should', 'shall', 'they', 'we', 'i', 'you', 'it', 'he', 'she',
             'and', 'or', 'not', "don't", 'do', 'does', 'did', 'been', 'be'}

def _fallback_pos(prev_word):
    pw = (prev_word or '').lower().strip(".,;:!?")
    if pw in _DET:
        return 'N'
    if pw in _VERB_CUE:
        return 'V'
    return None  # unknown -> leave alone

# --------------------------------------------------------------------------- #
# Class A — scientific alphanumeric tokens
# --------------------------------------------------------------------------- #
# Token that mixes uppercase letters and digits (optionally hyphen), e.g.
# TMEM174, SUCNR1, GLP-1, P53, mTOR2 — the dominant garble class.
_SCI_RE = re.compile(r'\b([A-Za-z]{2,}\d+|[A-Z]{2,}-?\d+|[A-Za-z]+-\d+)\b')
_DIGIT_WORD = {'0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
               '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'}

# GUARD 1 — word-acronyms: pronounced as a word, NOT spelled letter-by-letter.
# Leave these tokens entirely unchanged (the model already says them fine);
# expanding them would be a regression (COVID19 -> "C O V I D ..." is wrong).
# Keyed by the lowercased alphabetic component. Extend as new ones surface.
EXCLUDE_WORD_ACRONYMS = {
    "covid", "sars", "aids", "ebola", "mrsa", "hin", "nasa", "radar", "laser",
    "scuba", "zika", "mers", "hpai",
}

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
         "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
         "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]

def _two_digit_words(n):
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    return _TENS[t] + ((" " + _ONES[o]) if o else "")

def _number_to_spoken(digits):
    """GUARD 2 — read 1-digit as a word, 2-digit as a whole number ('19'->
    'nineteen'), 3+ digits as separate digits (gene IDs: 174 -> 'one seven four')."""
    if len(digits) == 1:
        return _DIGIT_WORD[digits]
    if len(digits) == 2:
        return _two_digit_words(int(digits))
    return ' '.join(_DIGIT_WORD[d] for d in digits)

def expand_sci_token(tok):
    """TMEM174 -> 'T M E M one seven four'.  aquaporin-4 -> 'aquaporin four'.
    COVID-19 -> unchanged (word-acronym guard).  CD20 -> 'C D twenty'.
    Heuristic: an all-caps (or mostly-caps) letter run is an initialism (spell
    it); a lowercase word stays a word; numbers read per _number_to_spoken."""
    m = re.match(r'^([A-Za-z]+)-?(\d+)$', tok)
    if not m:
        return tok
    letters, digits = m.group(1), m.group(2)
    if letters.lower() in EXCLUDE_WORD_ACRONYMS:    # GUARD 1: leave word-acronyms
        return tok
    caps = sum(1 for c in letters if c.isupper())
    if caps >= max(2, len(letters) - 1):           # initialism: TMEM, SUCNR, GLP
        spoken_letters = ' '.join(letters.upper())
    else:                                           # real word: aquaporin, p
        spoken_letters = letters
    return f"{spoken_letters} {_number_to_spoken(digits)}"

# --------------------------------------------------------------------------- #
# Class B — heteronyms / homographs (POS-conditioned)
# --------------------------------------------------------------------------- #
# pron hints are human-readable targets; the verified spelling is set by the
# ASR self-verify loop. noun/adj = reduced ending, verb = stressed ending.
HETERONYMS = {
    # noun/verb stress pairs (NOUN: stress 1st; VERB: stress 2nd)
    "compound":  {"N": "COM-pound",  "V": "com-POUND"},
    "record":    {"N": "REC-ord",    "V": "re-CORD"},
    "present":   {"N": "PRES-ent",   "V": "pre-SENT"},
    "object":    {"N": "OB-ject",    "V": "ob-JECT"},
    "subject":   {"N": "SUB-ject",   "V": "sub-JECT"},
    "project":   {"N": "PROJ-ect",   "V": "pro-JECT"},
    "contract":  {"N": "CON-tract",  "V": "con-TRACT"},
    "conduct":   {"N": "CON-duct",   "V": "con-DUCT"},
    "conflict":  {"N": "CON-flict",  "V": "con-FLICT"},
    "contrast":  {"N": "CON-trast",  "V": "con-TRAST"},
    "convert":   {"N": "CON-vert",   "V": "con-VERT"},
    "increase":  {"N": "IN-crease",  "V": "in-CREASE"},
    "decrease":  {"N": "DE-crease",  "V": "de-CREASE"},
    "produce":   {"N": "PRO-duce",   "V": "pro-DUCE"},
    "progress":  {"N": "PROG-ress",  "V": "pro-GRESS"},
    "permit":    {"N": "PER-mit",    "V": "per-MIT"},
    "rebel":     {"N": "REB-el",     "V": "re-BEL"},
    "refund":    {"N": "RE-fund",    "V": "re-FUND"},
    "reject":    {"N": "RE-ject",    "V": "re-JECT"},
    "research":  {"N": "RE-search",  "V": "re-SEARCH"},
    "transfer":  {"N": "TRANS-fer",  "V": "trans-FER"},
    "transport": {"N": "TRANS-port", "V": "trans-PORT"},
    "upgrade":   {"N": "UP-grade",   "V": "up-GRADE"},
    "update":    {"N": "UP-date",    "V": "up-DATE"},
    "impact":    {"N": "IM-pact",    "V": "im-PACT"},
    "import":    {"N": "IM-port",    "V": "im-PORT"},
    "export":    {"N": "EX-port",    "V": "ex-PORT"},
    "insert":    {"N": "IN-sert",    "V": "in-SERT"},
    "insult":    {"N": "IN-sult",    "V": "in-SULT"},
    "extract":   {"N": "EX-tract",   "V": "ex-TRACT"},
    "segment":   {"N": "SEG-ment",   "V": "seg-MENT"},
    "suspect":   {"N": "SUS-pect",   "V": "sus-PECT"},
    "survey":    {"N": "SUR-vey",    "V": "sur-VEY"},
    "addict":    {"N": "AD-dict",    "V": "ad-DICT"},
    "default":   {"N": "DE-fault",   "V": "de-FAULT"},
    # -ate set: NOUN/ADJ reduced 'it'/'uht' ending; VERB full 'ate'
    "moderate":   {"N": "MOD-er-it",    "V": "MOD-er-ate"},
    "estimate":   {"N": "ES-ti-mit",    "V": "ES-ti-mate"},
    "aggregate":  {"N": "AG-gre-git",   "V": "AG-gre-gate"},
    "duplicate":  {"N": "DU-pli-kit",   "V": "DU-pli-cate"},
    "separate":   {"N": "SEP-rit",      "V": "SEP-a-rate"},
    "delegate":   {"N": "DEL-e-git",    "V": "DEL-e-gate"},
    "graduate":   {"N": "GRAD-u-it",    "V": "GRAD-u-ate"},
    "advocate":   {"N": "AD-vo-kit",    "V": "AD-vo-cate"},
    "associate":  {"N": "as-SO-shit",   "V": "as-SO-shee-ate"},
    "approximate":{"N": "ap-PROX-i-mit","V": "ap-PROX-i-mate"},
    "deliberate": {"N": "de-LIB-er-it", "V": "de-LIB-er-ate"},
    "elaborate":  {"N": "e-LAB-o-rit",  "V": "e-LAB-o-rate"},
    "alternate":  {"N": "AL-ter-nit",   "V": "AL-ter-nate"},
    # sound (not stress) pairs
    "read":      {"N": "reed", "V": "reed", "VBD": "red", "VBN": "red"},
    "lead":      {"N": "leed", "V": "leed"},      # metal 'led' is rarer; leave default
    "live":      {"ADJ": "lyve", "V": "liv"},
    "use":       {"N": "yooss", "V": "yooz"},
    "close":     {"ADJ": "kloce", "V": "kloze", "N": "kloze"},
}

def _coarse_pos(penn):
    """Map a Penn Treebank tag to N / V / ADJ / VBD / VBN."""
    if penn in ('VBD',):
        return 'VBD'
    if penn in ('VBN',):
        return 'VBN'
    if penn.startswith('V') or penn == 'MD':
        return 'V'
    if penn.startswith('JJ'):
        return 'ADJ'
    if penn.startswith('N'):
        return 'N'
    return None

def _pick(entry, coarse):
    if coarse and coarse in entry:
        return entry[coarse]
    # fall back across families
    if coarse in ('VBD', 'VBN') and 'V' in entry:
        return entry['V']
    if coarse == 'ADJ' and 'N' in entry:
        return entry['N']
    return None

# --------------------------------------------------------------------------- #
# analyze + normalize
# --------------------------------------------------------------------------- #
def analyze(text):
    """Return detected items: [{class, token, pos, suggestion, context}]."""
    items = []
    # Class A
    for m in _SCI_RE.finditer(text):
        tok = m.group(1)
        if any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
            items.append({"class": "A_sci", "token": tok, "pos": None,
                          "suggestion": expand_sci_token(tok)})
    # Class B
    tagger = _get_tagger()
    words = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?|\S", text)
    if tagger:
        try:
            tagged = tagger(text)
        except Exception:
            tagged = None
    else:
        tagged = None
    if tagged:
        for i, (w, penn) in enumerate(tagged):
            lw = w.lower()
            if lw in HETERONYMS:
                coarse = _coarse_pos(penn)
                sugg = _pick(HETERONYMS[lw], coarse)
                items.append({"class": "B_heteronym", "token": w, "pos": penn,
                              "coarse": coarse, "suggestion": sugg})
    else:
        toks = re.findall(r"[A-Za-z']+", text)
        for i, w in enumerate(toks):
            lw = w.lower()
            if lw in HETERONYMS:
                coarse = _fallback_pos(toks[i-1] if i else None)
                sugg = _pick(HETERONYMS[lw], coarse) if coarse else None
                items.append({"class": "B_heteronym", "token": w,
                              "pos": "fallback", "coarse": coarse,
                              "suggestion": sugg})
    return items

def normalize(text, heteronyms=False):
    """Apply class-A expansion (always — safe, only fires on alphanumeric sci
    tokens) and optionally class-B heteronym respelling. Returns rewritten text.

    Class-B is opt-in because its respelling isn't ASR-verifiable (stress is
    inaudible to ASR); it's a proactive linguistic rule, applied only when asked.
    """
    # Class A — expand scientific alphanumeric tokens in place
    def _sub_sci(m):
        tok = m.group(1)
        if any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
            return expand_sci_token(tok)
        return tok
    out = _SCI_RE.sub(_sub_sci, text)

    # Class B — proactive POS-correct heteronym respelling (opt-in)
    if heteronyms:
        tagger = _get_tagger()
        try:
            tagged = tagger(out) if tagger else None
        except Exception:
            tagged = None
        if tagged:
            pieces, idx = [], 0
            for w, penn in tagged:
                lw = w.lower()
                if lw in HETERONYMS:
                    sugg = _pick(HETERONYMS[lw], _coarse_pos(penn))
                    pieces.append((w, sugg))
            for orig, sugg in pieces:
                if sugg:
                    out = re.sub(r'\b' + re.escape(orig) + r'\b', sugg, out, count=1)
    return out


if __name__ == "__main__":
    import sys
    mode = "analyze"
    args = sys.argv[1:]
    if args and args[0] in ("analyze", "normalize"):
        mode, args = args[0], args[1:]
    txt = open(args[0]).read() if args else sys.stdin.read()
    if mode == "normalize":
        sys.stdout.write(normalize(txt, heteronyms=("--het" in sys.argv)))
    else:
        for it in analyze(txt):
            print(it)
