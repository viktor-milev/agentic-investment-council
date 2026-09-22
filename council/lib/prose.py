"""The deterministic prose measure (spec sections U6.2 and U6.3, owner ruling
AC6).

It scores any text on the marks that separate an analyst's prose from a model's
mannered prose: dashes, rhetorical antithesis ("not X, it is Y"), over-long
sentences, rhetorical questions, the number-style lapses of the report design
audit section C2, and - for the chairman's rationale - the share of sentences
that carry a figure, a date or a named source. The thresholds and the pattern
lists are data (council/floors/prose-rules.json); this module is the arithmetic
over them, and the briefs carry the same rules in words, so the council's voice
is carried by its own briefs and this measure, never by a host machine.

The measure never raises on any text. Empty text scores zero words and neither
passes nor fails anything - the caller records it as advisory "no text". This is
an advisory measure with a single re-ask for the chairman, never a gate that
freezes a verdict, so it uses one simple sentence splitter and does not chase
natural-language edge cases.

Stdlib only (ruling X).
"""

import json
import os
import re

_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "floors",
                           "prose-rules.json")

# A dash is an em dash, an en dash, or a hyphen standing alone between spaces
# (a spaced hyphen used as a dash). A hyphen inside a word or a number range
# (a range written low-to-high with a hyphen) is not a dash and is not counted.
_DASH_CHARS = re.compile("[—–]")
_SPACED_HYPHEN = re.compile(r"(?<=\s)-(?=\s)")

# Rhetorical antithesis with a pronoun subject: "not X. It is Y" / "not X, it
# is Y" / "not X; it is Y" and the "not X but it is Y" form. The first pattern
# stops at the first sentence-internal break (. , ;) that a pronoun-and-verb
# follows; the second catches the "but" join. Kept deliberately narrow: a false
# positive costs one advisory re-ask, never a verdict. The subject list is the
# contrast pronouns only - the existential "there is/are" and "we" are left out,
# because "Not sell. There are no borrowings" is not a rhetorical antithesis.
_PRONOUN = r"(?:it|they|this|that|these|those|he|she)"
_ANTITHESIS_PATTERNS = (
    re.compile(r"\bnot\b[^.?!]{0,80}?[.;,]\s*%s\s+(?:is|are|was|were)\b"
               % _PRONOUN, re.IGNORECASE),
    re.compile(r"\bnot\b[^.?!;,]{0,80}?\bbut\b\s+%s\s+(?:is|are|was|were)\b"
               % _PRONOUN, re.IGNORECASE),
)


def load_rules(path=None):
    """The ruled thresholds and pattern lists, as data."""
    with open(path or _RULES_PATH, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def count_words(text):
    """Words the way the fixtures count them: runs of non-whitespace."""
    return len(str(text or "").split())


def split_sentences(text, rules):
    """One simple splitter: break after . ! or ? followed by whitespace, then
    re-join a fragment whose predecessor ended in a known abbreviation so
    "Inc. The" is not read as two sentences. Advisory-grade, not exhaustive."""
    abbreviations = set(a.lower() for a in (rules or {}).get("abbreviations", []))
    raw = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    out = []
    for fragment in raw:
        if not fragment.strip():
            continue
        if out:
            tail = out[-1].split()
            if tail and tail[-1].lower() in abbreviations:
                out[-1] = out[-1] + " " + fragment
                continue
        out.append(fragment)
    return out


def _count_dashes(text):
    return len(_DASH_CHARS.findall(text)) + len(_SPACED_HYPHEN.findall(text))


def _count_antithesis(text):
    return sum(len(pattern.findall(text)) for pattern in _ANTITHESIS_PATTERNS)


def _banned_hits(text, rules):
    hits = []
    for spec in (rules or {}).get("banned_patterns", []):
        flags = re.IGNORECASE if "i" in (spec.get("flags") or "") else 0
        for match in re.compile(spec["regex"], flags).finditer(text):
            hits.append({"id": spec["id"], "match": match.group(0),
                         "message": spec["message"]})
    return hits


def _grounded(sentence, months, cues):
    """A sentence is grounded when it carries a figure, a four-digit year, a
    month name or a named source cue (spec U6.2; the cue list is data)."""
    if re.search(r"\d", sentence):
        return True
    lowered = sentence.lower()
    for month in months:
        if re.search(r"\b" + re.escape(month) + r"\b", lowered):
            return True
    for cue in cues:
        if re.search(r"\b" + re.escape(cue) + r"\b", lowered):
            return True
    return False


def measure(text, rules=None):
    """Score one text. Returns a plain dict of counts and shares; never raises
    on any text. Empty text scores zero words and a null grounded share."""
    rules = rules or load_rules()
    text = str(text or "")
    words = count_words(text)
    sentences = split_sentences(text, rules)
    nsent = len(sentences)
    long_words = rules.get("long_sentence_words", 25)
    longs = [s for s in sentences if len(s.split()) > long_words]
    dashes = _count_dashes(text)
    per_1000 = round(dashes * 1000.0 / words, 2) if words else 0.0
    months = [m.lower() for m in rules.get("months", [])]
    cues = [c.lower() for c in rules.get("source_cues", [])]
    grounded = sum(1 for s in sentences if _grounded(s, months, cues))
    return {
        "words": words,
        "sentences": nsent,
        "dashes": dashes,
        "dashes_per_1000_words": per_1000,
        "antithesis": _count_antithesis(text),
        "long_sentences": len(longs),
        "long_sentence_share": round(len(longs) / nsent, 4) if nsent else 0.0,
        "rhetorical_questions": sum(1 for s in sentences
                                    if s.rstrip().endswith("?")),
        "banned": _banned_hits(text, rules),
        "grounded_sentences": grounded,
        "grounded_share": round(grounded / nsent, 4) if nsent else None,
        "empty": words == 0,
    }


def failures(score, rules, rationale_words=None):
    """Every way this chairman document breaches the ruled thresholds, in
    plain words for the re-ask hit list. An empty list means it passed. Only
    the chairman is judged against these; advisors are scored, never judged.
    `rationale_words`, where given, is checked against the word cap."""
    thresholds = rules["chair_thresholds"]
    out = []
    if score["antithesis"] > thresholds["antithesis_max"]:
        out.append('%d rhetorical antithesis ("not X, it is Y"); the ruled '
                   "maximum is %d - state the point directly"
                   % (score["antithesis"], thresholds["antithesis_max"]))
    if score["dashes_per_1000_words"] > thresholds["dashes_per_1000_words_max"]:
        out.append("%s dashes per 1,000 words; the ruled maximum is %d - end "
                   "the sentence instead of splicing it with a dash"
                   % (score["dashes_per_1000_words"],
                      thresholds["dashes_per_1000_words_max"]))
    if score["long_sentence_share"] > thresholds["long_sentence_share_max"]:
        out.append("%.0f%% of sentences run over %d words; the ruled maximum "
                   "is %.0f%% - break the long ones"
                   % (score["long_sentence_share"] * 100,
                      rules.get("long_sentence_words", 25),
                      thresholds["long_sentence_share_max"] * 100))
    if score["rhetorical_questions"] > thresholds["rhetorical_questions_max"]:
        out.append("%d rhetorical question(s); the ruled maximum is %d - make "
                   "the statement" % (score["rhetorical_questions"],
                                      thresholds["rhetorical_questions_max"]))
    grounded = score.get("grounded_share")
    if grounded is not None and grounded < thresholds["grounded_share_min"]:
        out.append("only %.0f%% of sentences carry a figure, a date or a "
                   "source; the ruled minimum is %.0f%% - ground the claims"
                   % (grounded * 100, thresholds["grounded_share_min"] * 100))
    for hit in score["banned"]:
        out.append("%s (found %r)" % (hit["message"], hit["match"]))
    if rationale_words is not None:
        cap = rules.get("rationale_word_cap")
        if cap is not None and rationale_words > cap:
            out.append("the rationale runs %d words; the cap is %d - tighten "
                       "it to what the front page can carry"
                       % (rationale_words, cap))
    return out


def describe(score):
    """One compact reading of a score, for the report appendix and the run
    record. Empty text says so."""
    if score.get("empty"):
        return "no text to score"
    grounded = score.get("grounded_share")
    grounded_part = ("; %.0f%% of sentences grounded" % (grounded * 100)
                     if grounded is not None else "")
    return ("%d words; %s dashes per 1,000 words; %d antithesis; %.0f%% "
            "long sentences; %d rhetorical questions; %d banned number-style%s"
            % (score["words"], score["dashes_per_1000_words"],
               score["antithesis"], score["long_sentence_share"] * 100,
               score["rhetorical_questions"], len(score["banned"]),
               grounded_part))
