"""
Name matching, against the cases it was built for.

The measured failure mode is a document's phrasing wrapped around a thing's
name, not a typo — so the negative cases matter as much as the positive ones.
Both `ePICSA`/`PICSA` and `Open App Builder`/`OpenChatBuilder` are pairs of
genuinely distinct live records whose strings are very alike, and an earlier
version of this module scored both as matches.
"""
import pytest

from pantograph import similarity

MATCH = [
    ("R-Instat", "r-instat", "case and punctuation"),
    ("Development of R-Instat", "R-Instat", "a gerund wrapper"),
    ("Supporting PICSA in Ghana", "PICSA Ghana support", "reordered words"),
    ("R Package: carbonr", "carbonr", "a Category: prefix"),
    ("Establishing INNODEMS, Kenya", "Supporting INNODEMS, Kenya",
     "two wrappers on one core"),
    ("2nd African STACK Conference", "African STACK conference 2", "reordering"),
    ("OpenChatBuilder", "Open Chat Builder", "spacing only"),
    ("Podcasts", "The IDEMS Podcast", "a word inside a longer name"),
    ("2nd African STACK Conference", "African STACK conference 2",
     "the same ordinal, written two ways"),
    ("2nd African STACK Conference", "Second African STACK Conference",
     "an ordinal as a word"),
    ("ICOTS 2026", "ICOTS 2026 paper submissions", "the same year"),
    ("Open App Builder v0.23.0 release", "Open App Builder v0.23.1 release",
     "two releases of one product still share most of their numbers"),
]

NO_MATCH = [
    # Found by running this against the live data: every word matches, and the
    # ordinal is the entire difference between two real conferences.
    ("2nd African STACK Conference", "3rd African STACK Conference 2025",
     "a different conference in the same series"),
    ("ICOTS 2026", "ICOTS 2025", "the year is the distinguishing part"),
    ("The IDEMS Podcast Episode_200", "The IDEMS Podcast Episode_201",
     "an episode number welded on by an underscore"),
    ("ePICSA", "PICSA", "distinct products, 91% alike as strings"),
    ("Open App Builder", "OpenChatBuilder", "distinct products"),
    ("IDEMS Kenya", "IDEMS Ghana", "one word apart, different places"),
    ("IDEMS Podcast", "IDEMS Database", "shared prefix only"),
    ("Children's Parliament", "Certificator", "unrelated"),
    ("ICOTS 2026", "ISI Conference", "two conferences"),
    ("Global Parenting Initiative", "Parenting for Lifelong Health Digital",
     "a shared word in long names"),
]


@pytest.mark.parametrize("left,right,why", MATCH)
def test_names_that_mean_the_same_thing(left, right, why):
    assert similarity.score(left, right) >= similarity.DEFAULT_THRESHOLD, why


@pytest.mark.parametrize("left,right,why", NO_MATCH)
def test_names_that_do_not(left, right, why):
    assert similarity.score(left, right) < similarity.DEFAULT_THRESHOLD, why


def test_identical_is_one():
    assert similarity.score("R-Instat", "R-Instat") == 1.0


def test_symmetric():
    for left, right, _ in MATCH + NO_MATCH:
        assert similarity.score(left, right) == similarity.score(right, left)


def test_empty_never_matches():
    assert similarity.score("", "R-Instat") == 0.0
    assert similarity.score(None, "R-Instat") == 0.0
    assert similarity.score("R-Instat", "   ") == 0.0


def test_a_name_of_only_stopwords_does_not_match_everything():
    assert similarity.score("The", "R-Instat") < similarity.DEFAULT_THRESHOLD


def test_matches_returns_best_first_and_caps():
    candidates = [(1, "R-Instat"), (2, "r-instat"), (3, "Development of R-Instat"),
                  (4, "Certificator")]
    found = similarity.matches("R-Instat", candidates, limit=2)
    assert [row[0] for row in found] == [1, 2]
    assert all(row[2] >= similarity.DEFAULT_THRESHOLD for row in found)


def test_matches_excludes_below_threshold():
    assert similarity.matches("R-Instat", [(1, "Certificator")]) == []


@pytest.mark.parametrize("name", [
    "Development of R-Instat", "Supporting PICSA in Ghana",
    "Establishing INNODEMS", "Investigating IDEMS Kenya",
])
def test_document_phrasing_detected(name):
    assert similarity.looks_like_document_phrasing(name)


@pytest.mark.parametrize("name", [
    "R-Instat", "ICOTS 2026", "Podcast: ISI 2025", "Children's Parliament",
    "Open App Builder",
])
def test_a_thing_s_own_name_is_not_flagged(name):
    assert not similarity.looks_like_document_phrasing(name)
