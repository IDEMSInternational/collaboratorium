"""
similarity.py
Deciding whether two record names mean the same thing.

Built for one measured failure mode, not for typos. A reading of IDEMS's annual
reports expected 80-90% of the initiatives it would propose to exist already
under a *shorter* name — `R-Instat`, not `Development of R-Instat` — and found
`Investigating IDEMS Kenya`, `Establishing INNODEMS, Kenya` and
`Supporting INNODEMS, Kenya` to be three names for one thing. An edit-distance
measure passes all of those as unrelated, because the strings genuinely differ
by a lot; what they share is the noun at the end.

So the shape of the problem is a wrapper around a core:

    Development of  |  R-Instat
    R Package:      |  carbonr
    Supporting      |  INNODEMS, Kenya

Strip the wrapper, compare the core. Only 5 of 153 live initiative names begin
with a gerund, which is why a gerund in a *proposal* is a strong signal that a
document's phrasing has survived into a record that should not carry it.

What this cannot do, and should not be extended to try: `IDEMS Kenya` and
`INNODEMS, Kenya` are the same organisation renamed, and no measure over
strings can know that. It happens to score them alike because the words
resemble each other, which is luck rather than correctness. Knowing that one
name succeeded another is an **alias list**, it belongs to whoever holds the
history, and the right place for it is the producer rather than here.

Nothing here blocks an import. The advisory is reported and the record is staged
anyway: duplicate names are sometimes legitimate, and in the live data there are
no duplicates at all, so this exists to catch re-wording rather than repetition.
"""
import difflib
import re

# Phrases a document wraps a thing's name in. Order matters only in that longer
# ones are tried first, so "development of" wins over "development".
_WRAPPERS = (
    "development of", "developing", "creation of", "creating",
    "establishment of", "establishing", "implementation of", "implementing",
    "support for", "supporting", "investigation of", "investigating",
    "exploration of", "exploring", "understanding", "planning for",
    "teaching", "improving", "building", "work on", "working on",
    "research into", "research methods support for", "maintenance of",
    "maintaining", "rollout of", "launch of", "review of", "update to",
    "updates to", "upgrade of", "migration of", "migrating",
)

# Words that carry no distinguishing weight once the wrapper is gone. The
# organisation's own name is deliberately *not* here: it looks like noise on
# every record until you meet `IDEMS Kenya`, where it is the subject.
_STOPWORDS = frozenset((
    "the", "a", "an", "of", "for", "in", "on", "at", "to", "and", "with",
    "by", "from", "into", "its", "our",
))

DEFAULT_THRESHOLD = 0.72


def _normalise(name):
    """
    Lowercase, punctuation out, whitespace collapsed.

    Underscores separate rather than join, which `\\w` would not do: live
    activity names include `The IDEMS Podcast Episode_200`, and an episode
    number welded to the word before it is a number no comparison can see.
    """
    text = (name or "").lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return " ".join(text.split())


def _strip_category(name):
    """
    Drop a leading `Category:` prefix.

    14% of live initiative names and 16% of activity names use one — `R Package:
    carbonr`, `Podcast: ISI 2025` — so `carbonr` and `R Package: carbonr` are
    the same thing named at two levels of specificity. The colon is only taken
    as a prefix when something follows it and the prefix is short, so a title
    containing a colon mid-sentence is left alone.
    """
    head, sep, tail = (name or "").partition(":")
    if sep and tail.strip() and len(head.split()) <= 3:
        return tail.strip()
    return name or ""


def _core(name):
    """The name with its document-ese wrapper and stopwords removed."""
    text = _normalise(_strip_category(name))
    for wrapper in sorted(_WRAPPERS, key=len, reverse=True):
        if text.startswith(wrapper + " "):
            text = text[len(wrapper) + 1:]
            break
    tokens = [t for t in text.split() if t not in _STOPWORDS]
    # Everything was a stopword: keep what there was rather than nothing, or a
    # name like "The IDEMS Podcast" would compare as empty and match anything.
    return " ".join(tokens) if tokens else text


def score(left, right):
    """
    How alike two names are, from 0.0 to 1.0.

    The bands are deliberately coarse. A number here is read by a person
    deciding "is this the same thing", so it needs to separate "almost
    certainly" from "worth a look" and nothing finer.
    """
    if not (left or "").strip() or not (right or "").strip():
        return 0.0

    if _normalise(left) == _normalise(right):
        return 1.0

    # Found by running this against the live data: `2nd African STACK
    # Conference` scored 85% against the existing `3rd African STACK Conference
    # 2025`, which is a different conference. Where a name is distinguished
    # from its siblings by an ordinal or a year, that number is the whole of
    # the difference, and every other signal says they are the same — the words
    # really are identical. So two names that each carry numbers, sharing none,
    # are not the same thing however alike they read.
    left_numbers, right_numbers = _numbers(left), _numbers(right)
    if left_numbers and right_numbers and not (left_numbers & right_numbers):
        return 0.0

    left_core, right_core = _core(left), _core(right)
    if left_core and left_core == right_core:
        # Same thing, different wrapper: `R-Instat` vs `Development of R-Instat`.
        return 0.95

    left_tokens = set(left_core.split())
    right_tokens = set(right_core.split())
    if not left_tokens or not right_tokens:
        return 0.0

    # A name that is one word after stripping carries no token evidence, and
    # character similarity is actively misleading on exactly this kind of name:
    # `ePICSA` and `PICSA` are distinct products whose strings are 91% alike,
    # and so are `Open App Builder` and `OpenChatBuilder`. Both are live records
    # here. So a single-token comparison must be an identity, give or take how
    # the name is spaced and pluralised — `OpenChatBuilder` against
    # `Open Chat Builder`, `Podcasts` against `The IDEMS Podcast`.
    if len(left_tokens) == 1 or len(right_tokens) == 1:
        if _squashed(left_core) == _squashed(right_core):
            return 0.90
        # The one word may still *be* one of the other's words: `Podcasts`
        # against `The IDEMS Podcast`, both of which are live initiatives and
        # plausibly one thing. It has to be a whole word, so `PICSA` still does
        # not reach `ePICSA`.
        one, other = ((left_tokens, right_tokens) if len(left_tokens) == 1
                      else (right_tokens, left_tokens))
        if _squashed(next(iter(one))) in {_squashed(t) for t in other}:
            return 0.78
        return 0.0

    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    if left_tokens <= right_tokens or right_tokens <= left_tokens:
        # One name is the other plus qualifiers: `INNODEMS kenya` inside
        # `establishing INNODEMS kenya partnership`. Scaled by how much of the
        # longer name the shorter one accounts for, so a single shared word in a
        # long title does not read as a match.
        shared = min(len(left_tokens), len(right_tokens))
        total = max(len(left_tokens), len(right_tokens))
        return 0.75 + 0.20 * (shared / total)

    ratio = difflib.SequenceMatcher(None, left_core, right_core).ratio()
    # Token overlap catches reordering; the sequence ratio catches a genuine
    # misspelling, but only once there are enough tokens for it to mean
    # something, and only when it is high enough to be a spelling rather than a
    # resemblance.
    return max(overlap, ratio if ratio >= 0.85 else 0.0)


# Ordinals as a name writes them, against the number they mean, so that
# `2nd African STACK Conference` and `African STACK conference 2` agree.
_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}


def _numbers(name):
    """
    The ordinals and years in a name, as integers.

    `second`, `2nd` and `2` are the same number. A version string such as
    `v0.23.0` contributes its parts, which is why two releases of one product
    still share most of their numbers and go on matching.
    """
    found = set()
    for token in _normalise(name).split():
        if token in _ORDINAL_WORDS:
            found.add(_ORDINAL_WORDS[token])
        elif token.isdigit():
            found.add(int(token))
        else:
            match = re.fullmatch(r"(\d+)(st|nd|rd|th)", token)
            if match:
                found.add(int(match.group(1)))
    return found


def _squashed(core):
    """A core with spacing and a trailing plural removed, for comparing names
    that differ only in how they are written."""
    text = core.replace(" ", "")
    return text[:-1] if text.endswith("s") and len(text) > 3 else text


def matches(name, candidates, threshold=DEFAULT_THRESHOLD, limit=3):
    """
    The candidates that plausibly name the same thing as `name`, best first.

    `candidates` is an iterable of `(identifier, name)`. Returns a list of
    `(identifier, name, score)`, at most `limit` of them.
    """
    scored = []
    for identifier, candidate_name in candidates:
        value = score(name, candidate_name)
        if value >= threshold:
            scored.append((identifier, candidate_name, round(value, 2)))
    scored.sort(key=lambda row: (-row[2], str(row[0])))
    return scored[:limit]


def looks_like_document_phrasing(name):
    """
    True when a name reads as a document's description of work rather than as
    the thing's own name.

    Advisory only, and reported separately from a match, because it fires on
    names that have no counterpart yet — which is the case where it is the only
    warning available. 5 of 153 live initiatives start with a gerund, so this is
    uncommon in practice and worth mentioning when it happens.
    """
    text = _normalise(_strip_category(name))
    if any(text.startswith(wrapper + " ") for wrapper in _WRAPPERS):
        return True
    first = text.split(" ", 1)[0] if text else ""
    return bool(first.endswith("ing") and len(first) > 5)
