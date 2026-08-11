"""
The `relevant:` expression language.

Parsing is tested separately from evaluation because config validation at
startup needs the first without the second — an expression that cannot parse
should fail before anyone opens the form.
"""
import pytest

from pantograph.expressions import (
    ExpressionError,
    evaluate,
    is_truthy,
    parse,
    referenced_elements,
    referenced_links,
)


def ev(source, **context):
    return evaluate(parse(source), context)


# --------------------------------------------------------------------------
# The motivating case
# --------------------------------------------------------------------------

LAWFUL_BASIS = "${lawful_basis} = 'legitimate_interest'"


def test_the_ropa_lawful_basis_rule():
    assert ev(LAWFUL_BASIS, lawful_basis="legitimate_interest") is True
    assert ev(LAWFUL_BASIS, lawful_basis="consent") is False
    # Unanswered is not a match, rather than an error.
    assert ev(LAWFUL_BASIS, lawful_basis=None) is False
    assert ev(LAWFUL_BASIS) is False


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

@pytest.mark.parametrize("source, expected", [
    ("${a} = 'x'", True),
    ("${a} != 'x'", False),
    ("${a} = 'y'", False),
    ("${a} != 'y'", True),
])
def test_equality(source, expected):
    assert ev(source, a="x") is expected


def test_numbers_compare_numerically_even_when_held_as_strings():
    """A dcc.Input yields a string even for a field declared as an integer."""
    assert ev("${n} > 5", n="10") is True
    assert ev("${n} > 5", n="10.5") is True
    assert ev("${n} = 3", n="3") is True
    assert ev("${n} >= 3 and ${n} <= 5", n=4) is True


def test_non_numeric_strings_compare_as_strings():
    assert ev("${a} = 'apple'", a="apple") is True
    assert ev("${a} < 'b'", a="a") is True


def test_double_and_single_quoted_strings_are_equivalent():
    assert ev('${a} = "x"', a="x") is True


def test_missing_element_reads_as_empty_not_an_error():
    """
    A form can legitimately reference an element that has not been answered.
    Erroring would make a partially filled form unusable.
    """
    assert ev("${nope} = ''") is True
    assert ev("${nope}") is False


# --------------------------------------------------------------------------
# Booleans and truthiness
# --------------------------------------------------------------------------

def test_and_or_not():
    assert ev("${a} = '1' and ${b} = '2'", a="1", b="2") is True
    assert ev("${a} = '1' and ${b} = '2'", a="1", b="9") is False
    assert ev("${a} = '1' or ${b} = '2'", a="9", b="2") is True
    assert ev("not ${a} = '1'", a="9") is True


def test_parentheses_override_precedence():
    ctx = dict(a="1", b="0", c="1")
    # and binds tighter than or, so without parentheses this is a or (b and c)
    assert ev("${a} = '1' or ${b} = '1' and ${c} = '1'", **ctx) is True
    assert ev("(${a} = '1' or ${b} = '1') and ${c} = '1'", **ctx) is True
    assert ev("(${b} = '1' or ${a} = '9') and ${c} = '1'", **ctx) is False


def test_a_bare_reference_is_an_answered_test():
    assert ev("${a}", a="something") is True
    assert ev("${a}", a="") is False
    assert ev("${a}", a="   ") is False
    assert ev("${a}", a=[]) is False
    assert ev("${a}", a=["x"]) is True
    assert ev("${a}", a=0) is False


@pytest.mark.parametrize("value, expected", [
    ("", False), ("  ", False), ("x", True),
    ([], False), (["a"], True), ({}, False),
    (None, False), (0, False), (1, True), (False, False), (True, True),
])
def test_emptiness_is_falsehood(value, expected):
    """Matches the emptiness test the submit-button validation already uses."""
    assert is_truthy(value) is expected


# --------------------------------------------------------------------------
# selected(), for select_multiple
# --------------------------------------------------------------------------

def test_selected_over_a_list():
    assert ev("selected(${tags}, 'health')", tags=["health", "climate"]) is True
    assert ev("selected(${tags}, 'nope')", tags=["health", "climate"]) is False
    assert ev("selected(${tags}, 'health')", tags=[]) is False
    assert ev("selected(${tags}, 'health')", tags=None) is False


def test_selected_over_a_comma_joined_string():
    """
    The same value read back from the database is comma-joined, so an
    expression must behave the same on an edit form as on an add form.
    """
    assert ev("selected(${tags}, 'climate')", tags="health,climate") is True
    assert ev("selected(${tags}, 'climate')", tags="health, climate") is True
    assert ev("selected(${tags}, 'nope')", tags="health,climate") is False


def test_a_single_choice_multiselect_compares_as_that_choice():
    """Convenience; anything longer must use selected()."""
    assert ev("${tags} = 'health'", tags=["health"]) is True
    assert ev("${tags} = 'health'", tags=["health", "climate"]) is False


# --------------------------------------------------------------------------
# Reading across a link
# --------------------------------------------------------------------------

SPECIAL_CATEGORY = "${data_field.special_category} = 'yes'"


def _rows(**tables):
    """A resolver over rows held in the test, standing in for the database."""
    calls = []

    def resolve(link_name, column, link_value):
        calls.append((link_name, column, link_value))
        return (tables.get(link_name) or {}).get(link_value, {}).get(column)

    resolve.calls = calls
    return resolve


def test_a_condition_reads_a_column_of_the_linked_row():
    """
    The motivating case: the record stops asking whether this is special
    category data, because the data_fields row it points at already says.
    """
    resolve = _rows(data_field={7: {"special_category": "yes"},
                                8: {"special_category": "no"}})
    assert evaluate(parse(SPECIAL_CATEGORY), {"data_field": 7}, resolve) is True
    assert evaluate(parse(SPECIAL_CATEGORY), {"data_field": 8}, resolve) is False


def test_the_resolver_is_given_the_links_current_value():
    resolve = _rows(data_field={7: {"special_category": "yes"}})
    evaluate(parse(SPECIAL_CATEGORY), {"data_field": 7}, resolve)
    assert resolve.calls == [("data_field", "special_category", 7)]


def test_a_reference_through_an_unset_link_reads_as_unanswered():
    """A question about a row nobody has picked yet is not a yes."""
    resolve = _rows(data_field={7: {"special_category": "yes"}})
    assert evaluate(parse(SPECIAL_CATEGORY), {}, resolve) is False
    assert evaluate(parse("${data_field.special_category}"), {}, resolve) is False


def test_a_column_the_row_does_not_answer_reads_as_empty():
    resolve = _rows(data_field={7: {}})
    assert evaluate(parse("${data_field.special_category}"), {"data_field": 7}, resolve) is False


def test_without_a_resolver_a_cross_link_reference_is_empty_rather_than_an_error():
    """
    Callers that never linked anything must not have to supply a resolver, and a
    condition they cannot answer has to read as unanswered like any other.
    """
    assert evaluate(parse(SPECIAL_CATEGORY), {"data_field": 7}) is False


def test_a_cross_link_reference_composes_with_the_rest_of_the_language():
    resolve = _rows(recipient={2: {"transfer_standing": "third_country"}})
    node = parse("${disposition} != 'removed' and ${recipient.transfer_standing} = 'third_country'")
    assert evaluate(node, {"disposition": "declared", "recipient": 2}, resolve) is True
    assert evaluate(node, {"disposition": "removed", "recipient": 2}, resolve) is False
    assert referenced_elements(node) == {"disposition", "recipient"}


def test_the_watched_element_is_the_link_itself():
    """The linked row can only change when the link is re-pointed."""
    node = parse("${data_field.special_category} = 'yes'")
    assert referenced_elements(node) == {"data_field"}
    assert referenced_links(node) == {("data_field", "special_category")}


def test_referenced_links_finds_every_pair_and_ignores_plain_references():
    node = parse("${a} and ${b.c} or selected(${d.e}, 'x')")
    assert referenced_links(node) == {("b", "c"), ("d", "e")}
    assert referenced_links(parse("${a} = '1'")) == set()


def test_a_reference_cannot_chain_two_links_deep():
    """
    Two hops would let one form's condition walk the whole schema, and each hop
    is a row fetch on every keystroke.
    """
    with pytest.raises(ExpressionError, match="more than one"):
        parse("${data_field.product.name}")


# --------------------------------------------------------------------------
# Parsing and validation
# --------------------------------------------------------------------------

def test_referenced_elements_finds_every_name():
    node = parse("${a} = '1' and (not ${b}) or selected(${c}, ${d})")
    assert referenced_elements(node) == {"a", "b", "c", "d"}


@pytest.mark.parametrize("source", [
    "",
    "   ",
    "${a} =",
    "= '1'",
    "${a} = 'unterminated",
    "(${a} = '1'",
    "${a} = '1')",
    "selected(${a})",
    "selected(${a}, 'b'",
    "${a} == '1'",       # '=' is the operator, following ODK
    "${a} & ${b}",
    "@",
    "${a}.b",            # the dot is part of a reference, not an operator
    "${a.}",
    "${.b}",
])
def test_malformed_expressions_are_rejected(source):
    with pytest.raises(ExpressionError):
        parse(source)


def test_a_bare_word_is_rejected_and_says_how_to_reference_an_element():
    """
    The likeliest authoring mistake is writing `lawful_basis` for
    `${lawful_basis}`, so the message should name the fix.
    """
    with pytest.raises(ExpressionError, match=r"\$\{lawful_basis\}"):
        parse("lawful_basis = 'consent'")


def test_errors_locate_themselves_in_the_source():
    with pytest.raises(ExpressionError, match="position"):
        parse("${a} = = '1'")


def test_literals_parse():
    assert ev("true") is True
    assert ev("false") is False
    assert ev("null") is False
    assert ev("${a} = null", a=None) is True


def test_there_is_no_way_to_reach_python():
    """
    The reason this is a parser and not eval(). These are all rejected as
    unknown names or bad syntax rather than executed.
    """
    for source in [
        "__import__('os').system('echo pwned')",
        "().__class__.__bases__",
        "${a}.__class__",
        "exec('x=1')",
    ]:
        with pytest.raises(ExpressionError):
            parse(source)
