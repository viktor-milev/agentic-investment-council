"""The blind seal and the reach scan.

The seal (owner ruling K2, ported from the old stack's deterministic
anonymity check): an advisor answer is reviewed blind under a random letter,
so an advisor that identifies its own lens, another lens, or the model that
produced it has broken the review before it starts. The patterns below are
the old stack's proven patterns, adapted to the five lenses of this bench;
they fire on IDENTITY, never on subject matter ("the bear market" and
"Anthropic signed a lease" stay legal; "as the bear advisor" does not).

The reach scan (REBUILD-SPEC section 10.5): every seat reasons over the one
frozen pack and nothing else. A URL in an answer whose host appears nowhere
in the pack's own source strings is evidence the seat reached outside the
record, and a seat that reaches outside the pack publishes nothing.

A violation re-runs the seat once, with the reason; a second violation fails
the run. Nothing is silently cleaned up.
"""

import re
import urllib.parse

# Per-lens identity patterns. The scan applies the UNION over every advisor
# answer: naming ANY lens on this bench is a leak, because the single blind
# reviewer reads all five answers and one label placed anywhere unblinds a
# letter. Word boundaries keep analytical vocabulary ("bearish", "bull
# market") legal; the lookaheads keep "the bear market" legal.
LENS_PATTERNS = {
    "bear": [
        r"\bthe bear\b(?![-\s]+market)", r"\bbear case\b",
        r"\bbear[\u2019']s (?:case|view|argument|seat)\b",
        r"\bas a bear\b", r"\bbear (?:seat|advisor|analyst|lens)\b",
    ],
    "bull": [
        r"\bthe bull\b(?![-\s]+market)", r"\bbull case\b",
        r"\bbull[\u2019']s (?:case|view|argument|seat)\b",
        r"\bas a bull\b", r"\bbull (?:seat|advisor|analyst|lens)\b",
    ],
    "base_rate": [
        r"\bbase[- ]rate skeptic\b", r"\bbase[- ]rate sceptic\b",
        r"\bthe skeptic\b", r"\bthe sceptic\b", r"\bskeptic[\u2019']s\b",
        r"\boutside[- ]view (?:advisor|adviser|seat|analyst|lens)\b",
    ],
    "market_structure": [
        r"\bmarket[- ]structure (?:analyst|seat|advisor|adviser|lens)\b",
        r"\bthe flow (?:analyst|seat)\b", r"\bmicrostructure (?:analyst|seat)\b",
    ],
    "risk": [
        r"\brisk manager\b", r"\brisk (?:seat|officer)\b",
        r"\bthe risk advisor\b", r"\bthe risk lens\b",
        r"\bthe risk analyst\b",
    ],
}

# First-person role identification, whatever the lens.
ROLE_PATTERNS = [
    r"\bI am (?:the|a|an|this|your)\b[^.\n]{0,60}?"
    r"\b(?:advisor|adviser|analyst|manager|skeptic|sceptic|seat|persona|voice|desk|bench member)\b",
    r"\bmy (?:brief|job|role|remit|mandate|assignment|seat|persona|charge|function) (?:is|was|here|as)\b",
    r"\bmy assigned (?:role|seat|persona|view|stance)\b",
    r"\bin my capacity as\b",
    r"\b(?:speaking|writing|arguing) as the\b",
    r"\bas the (?:bear|bull|skeptic|sceptic|risk manager|contrarian)\b",
    r"\bI (?:represent|speak for) the\b",
    r"\bI (?:have been |was )?(?:assigned|appointed|designated|cast) (?:as|to)\b",
    r"\bthis (?:advisor|seat|response) (?:is|was) (?:the|a|an)\b",
    r"\bI (?:was|am|have been) (?:asked|told|instructed|tasked|directed|briefed)\b",
    r"\bmy (?:instruction|instructions|task|tasking|charge) (?:is|was|are|were)\b",
]

# Model / system identity, anchored to the first person so the subject matter
# stays legal (an AI-economy subject makes "AI compute" ordinary vocabulary).
MODEL_PATTERNS = [
    r"\b(?:I am|I['’]m|I was)\s+(?:a|an|the)?\s*(?:claude|gpt|chatgpt|openai|anthropic|gemini|llama|mistral|grok|deepseek|qwen)\b",
    r"\bas (?:claude|gpt|chatgpt|openai|anthropic|gemini|llama|mistral|grok|deepseek|qwen)\b",
    r"\bas an? (?:language model|large language model|llm|ai assistant|ai model|ai system)\b",
    r"\bas an ai\b(?=\s*[,.;:]|\s+(?:i|my)\b)",
    r"\bI (?:am|was) (?:an? )?(?:ai|llm)\b",
    r"\bI (?:am|was) (?:trained|built|created|developed) by\b",
    r"\bmy (?:training data|knowledge cutoff|training cutoff|context window)\b",
    r"\b(?:claude|gpt)[- ]?(?:opus|sonnet|haiku|\d)[\w.-]*",
    r"\b(?:this (?:response|analysis) (?:was|is) (?:written|produced|generated) by|authored by|powered by)"
    r"\s+(?:a|an|the)?\s*(?:claude|gpt|chatgpt|openai|anthropic|gemini|llama)\b",
    r"\b(?:I am|I['\u2019]m|I was)\s+(?:a|an|the)?\s*"
    r"(?:language model|large language model|llm|ai assistant|ai model"
    r"|ai system|ai)\b",
]

# The ruled inventory vocabulary (REBUILD-SPEC section 2): wording that
# belongs to the owner's half of a question and travels to no seat. The
# words are assembled from split literals so the council tree itself never
# contains them - the tree-wide language scan enforces exactly that.
_INVENTORY_WORDS = (
    "he" + "ld", "unhe" + "ld", "posi" + "tion", "sle" + "eve",
    "wei" + "ght", "acco" + "unt", "n" + "lv", "net " + "liqui" + "dation",
)
INVENTORY_PATTERN = re.compile(
    r"\b(?:" + "|".join(
        r"\s+".join(re.escape(part) for part in word.split())
        for word in _INVENTORY_WORDS)
    + r")s?\b", re.IGNORECASE)

# The same words scanned over a copy with LINE BREAKS removed and word
# boundaries kept - a line break INSIDE a word must not smuggle it past
# the seam (round-3 finding), while ordinary spaces still separate
# ordinary words, so honest prose can never be exiled by a cross-word
# match (round-4 finding: "Weigh the evidence" must not read as a hit).
# A split padded with SPACES around the break is hostile craft, not a
# model accident, and sits outside the threat model - registered, not
# chased.
_INVENTORY_JOINED = re.compile(
    r"\b(?:" + "|".join(re.escape(word.replace(" ", ""))
                        for word in _INVENTORY_WORDS)
    + r")s?\b", re.IGNORECASE)


# Owner ruling AB14(2), read per ANCHORLESS-SPEC section 11: hold,
# holds and holding join the sealed inventory as the OWNER'S OWN
# possession language. Unlike every other word on the list these are
# ordinary English verbs, so a bare match fires on a company's own
# facts - measured on the owner's own theme question it fired twice on
# exactly that, and would have exiled two constituents' evidence into
# the half no seat ever reads. The pattern therefore ERRS NARROW: the
# frame's judgment is the backstop above it, and caught the owner's
# sentence unaided at the first live theme. A shape missed here is
# still caught there; a shape over-caught here has no backstop at all.
_OWN = r"(?:i|we)"
_OWN_PRONOUN = r"(?:my|our)"
# Auxiliaries and adverbs the owner might put between the pronoun and
# the verb, as a CLOSED list: a wildcard here is how a net starts
# eating sentences it was never meant to touch.
_BETWEEN = (r"(?:am|are|was|were|have|has|had|been|do|did|does"
            r"|continue|continued|to|still|already|also"
            r"|currently|personally|only|now|long)")
_ADJECTIVE = (r"(?:current|existing|largest|remaining|core|small|entire"
              r"|whole|own)")
POSSESSION_PATTERN = re.compile(
    r"\b" + _OWN + r"\s+(?:" + _BETWEEN + r"\s+){0,3}hold(?:s|ing)?\b"
    r"|\b" + _OWN_PRONOUN + r"\s+(?:" + _ADJECTIVE + r"\s+)?holdings?\b",
    re.IGNORECASE)


def inventory_hit(text):
    """True when the ruled inventory vocabulary appears in the text,
    however its line breaks fall. The join uses str.splitlines(), the
    same definition of a line break the frame's span-splitter uses -
    one definition, so the two can never diverge (round-5 finding:
    U+2028 was a line to one and not to the other)."""
    joined = "".join(str(text).splitlines())
    if INVENTORY_PATTERN.search(text):
        return True
    if _INVENTORY_JOINED.search(joined) is not None:
        return True
    # The possession shapes are PHRASES, so they are read over the text
    # as written AND over the same line-break-joined copy: a break
    # between the pronoun and the verb must not smuggle the sentence
    # past the seam either.
    return bool(POSSESSION_PATTERN.search(text)
                or POSSESSION_PATTERN.search(joined))


def _remove_link_destinations(text):
    """Remove every `](...)` link destination with a DEPTH WALK, so
    balanced parentheses inside a destination cannot defeat the
    removal the way they defeat any regex (round-8 finding): the label
    stays in place, the destination vanishes whole."""
    out = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] == "]" and index + 1 < length and \
                text[index + 1] == "(":
            depth = 1
            walk = index + 2
            while walk < length and depth:
                # A backslash-escaped character is never structural
                # (round-9 finding: \( miscounted the depth).
                if text[walk] == "\\":
                    walk += 2
                    continue
                if text[walk] == "(":
                    depth += 1
                elif text[walk] == ")":
                    depth -= 1
                walk += 1
            if depth == 0:
                out.append("]")
                index = walk
                continue
        out.append(text[index])
        index += 1
    return "".join(out)


def _hits(kind, pattern, text, out, seen):
    for match in re.finditer(pattern, text, re.IGNORECASE):
        key = (kind, match.group(0).casefold())
        if key in seen:
            continue
        seen.add(key)
        lo = max(0, match.start() - 60)
        hi = min(len(text), match.end() + 60)
        out.append({
            "kind": kind,
            "matched": match.group(0),
            "context": text[lo:hi].replace("\n", " "),
        })


def scan_advisor(markdown):
    """Scan one advisor answer for seal violations. Returns a list of
    {"kind", "matched", "context"} dicts; empty means sealed. Markdown
    emphasis characters are removed before matching, so bold or italic
    delimiters cannot hide an identity from the scan (round-3 finding)."""
    # The seal scans TWO normalized copies and a hit in EITHER counts
    # (rounds 3-7: single-copy normalization always traded adjacency
    # against boundaries; the union has neither blind side).
    #   RENDERED copy - what the reviewer's eye sees: link and image
    #   destinations removed with labels kept in place, emphasis
    #   characters zero-width. Catches Chat**GPT** and [Chat](#x)GPT.
    #   SPACED copy - structural characters as spaces, boundaries
    #   forced. Catches [ChatGPT]analysis and escaped-delimiter
    #   labels, whatever their form.
    text = str(markdown)
    rendered = _remove_link_destinations(text)
    rendered = re.sub(r"!?\[([^\]]*)\]\[[^\]]*\]", r"\1", rendered)
    rendered = re.sub(r"[*_`~\[\]\\!]", "", rendered)
    spaced = re.sub(r"[*_`~\[\]\\()]", " ", text)
    spaced = re.sub(r"[ \t]+", " ", spaced)
    copies = (rendered, spaced)
    violations = []
    seen = set()
    for copy_text in copies:
        for lens, patterns in LENS_PATTERNS.items():
            for pattern in patterns:
                _hits("lens_identity(%s)" % lens, pattern, copy_text,
                      violations, seen)
        for pattern in ROLE_PATTERNS:
            _hits("role_identity", pattern, copy_text, violations, seen)
        for pattern in MODEL_PATTERNS:
            _hits("model_identity", pattern, copy_text, violations, seen)
    return violations


_URL = re.compile(r"https?://[^\s<>()\"'\]]+", re.IGNORECASE)

# Any scheme's URL, for scrubbing SOURCE text: a URL of whatever scheme
# is parsed for its true hostname and never matched as prose - an
# ftp://a.com@evil.net source must not leave a.com lying in the prose
# pool (round-4 finding).
_ANY_SCHEME_URL = re.compile(
    r"\b[a-z][a-z0-9+.-]*://[^\s<>()\"'\]]+", re.IGNORECASE)


def pack_source_text(pack):
    """The pack's source strings split into two pools: the PARSED
    hostnames of every URL the sources carry, and the remaining prose
    with those URLs removed. A URL's text is never matched as prose -
    `https://a.com@evil.net/` names evil.net, whatever its text looks
    like (round-3 finding)."""
    capture = pack.get("capture", {})
    parts = []
    for fact in capture.get("tier1", []):
        parts.append(str(fact.get("source", "")))
    for passage in capture.get("tier2", []):
        parts.append(str(passage.get("source", "")))
    text = " ".join(parts)
    hostnames = set()
    for raw in _ANY_SCHEME_URL.findall(text):
        try:
            parsed = urllib.parse.urlsplit(raw.rstrip(".,;:!?")).hostname
        except ValueError:
            parsed = None
        if parsed:
            hostnames.add(parsed.lower().removeprefix("www."))
    prose = _ANY_SCHEME_URL.sub(" ", text).lower()
    return {"hostnames": hostnames, "prose": prose}


def _host_named_in(host, sources):
    """True when a source names the host: either a parsed source-URL
    hostname equals it or is one of its subdomains (sec.gov matches via
    data.sec.gov), or the host occurs in the sources' non-URL prose as
    a whole name - never as a fragment of a longer one (the
    neighbouring characters may not be letters, digits or hyphens; a
    PRECEDING dot stays legal; a TRAILING dot followed by another label
    is a different host)."""
    for named in sources["hostnames"]:
        if named == host or named.endswith("." + host):
            return True
    pattern = (r"(?<![A-Za-z0-9-])" + re.escape(host)
               + r"(?![A-Za-z0-9-])(?!\.[A-Za-z0-9])")
    return re.search(pattern, sources["prose"]) is not None


def reach_scan(markdown, pack):
    """URLs in the answer whose host appears nowhere in the pack's source
    strings. Each is evidence of a reach outside the frozen record."""
    sources = pack_source_text(pack)
    offending = []
    for raw in _URL.findall(markdown):
        url = raw.rstrip(".,;:!?")
        try:
            host = urllib.parse.urlsplit(url).hostname or ""
        except ValueError:
            host = ""
        host = host.lower()
        if host.startswith("www."):
            host = host[len("www."):]
        if not host or not _host_named_in(host, sources):
            offending.append(url)
    return offending


def violation_reason(violations, offending_urls):
    """One plain sentence the retry request can carry."""
    parts = []
    if violations:
        matched = ", ".join(sorted({repr(v["matched"]) for v in violations}))
        parts.append("the answer broke the blind seal by identifying a seat, "
                      "a lens or the producing model (matched: %s)" % matched)
    if offending_urls:
        parts.append("the answer cites material outside the frozen pack "
                      "(URLs whose host no pack source names: %s)"
                      % ", ".join(sorted(set(offending_urls))))
    return "; ".join(parts)
