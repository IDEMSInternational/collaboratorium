"""
expressions.py
The small expression language used by `relevant:` (and, later, `constraint:`).

Deliberately not Python `eval`. Config is operator-supplied and so nominally
trusted, but a form dialect that reaches `eval` is a landmine for whoever later
lets a less-trusted user edit config — and the grammar we actually need is tiny:

    expr       := or_expr
    or_expr    := and_expr ( 'or' and_expr )*
    and_expr   := not_expr ( 'and' not_expr )*
    not_expr   := 'not' not_expr | comparison
    comparison := primary ( ('=' | '!=' | '>' | '>=' | '<' | '<=') primary )?
    primary    := '(' expr ')' | 'selected' '(' expr ',' expr ')'
                | '${' NAME [ '.' NAME ] '}' | STRING | NUMBER
                | 'true' | 'false' | 'null'

Written as a tokeniser plus recursive-descent parser producing an AST, which is
then evaluated against a mapping of element name to current value. Parsing is
separated from evaluation so config can be validated at startup — an expression
that does not parse, or that references an element the form does not define,
should fail before anyone opens the form.

`=` is used for equality rather than `==`, following ODK, whose conventions this
config dialect already borrows.

`${data_field.special_category}` reads a column of the row a link element points
at. This module stays ignorant of databases: a `LinkRef` evaluates by calling a
resolver handed to `evaluate`, so the thing that knows how to fetch a row is the
caller's business and an expression remains a pure function of its inputs. The
dot lives *inside* the braces so that `${a}.__class__` is still the syntax error
it has always been — attribute access is a reference form, not an operator.
"""
import re


class ExpressionError(Exception):
    """Raised for an expression that cannot be tokenised, parsed or resolved."""


# --------------------------------------------------------------------------
# Tokeniser
# --------------------------------------------------------------------------

# Inner captures are *named*, not positional: positional indices shift
# whenever a rule is added above them, which is a silent breakage.
_TOKEN_SPEC = [
    ("WS",      r"\s+"),
    # The dotted form is tokenised with any number of segments so that a chain
    # two links deep is a *rejected reference* rather than an unexpected
    # character, which lets the parser say why it is refused.
    ("REF",     r"\$\{\s*(?P<ref_name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}"),
    ("NUMBER",  r"-?\d+\.\d+|-?\d+"),
    ("STRING",  r"'(?P<sq>[^']*)'|\"(?P<dq>[^\"]*)\""),
    ("OP",      r"!=|>=|<=|=|>|<"),
    ("LPAREN",  r"\("),
    ("RPAREN",  r"\)"),
    ("COMMA",   r","),
    ("NAME",    r"[A-Za-z_][A-Za-z0-9_]*"),
]
_TOKEN_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC))

_KEYWORDS = {"and", "or", "not", "true", "false", "null", "selected"}


class _Token:
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind, value, pos):
        self.kind, self.value, self.pos = kind, value, pos

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<{self.kind} {self.value!r} @{self.pos}>"


def tokenise(source):
    tokens, pos = [], 0
    while pos < len(source):
        match = _TOKEN_RE.match(source, pos)
        if not match:
            raise ExpressionError(
                f"Unexpected character {source[pos]!r} at position {pos} in {source!r}"
            )
        kind = match.lastgroup
        # lastgroup can name an inner capture, so map those back to their rule.
        if kind == "ref_name":
            kind = "REF"
        elif kind in ("sq", "dq"):
            kind = "STRING"
        if kind == "WS":
            pass
        elif kind == "REF":
            tokens.append(_Token("REF", match.group("ref_name"), pos))
        elif kind == "STRING":
            text = match.group("sq")
            if text is None:
                text = match.group("dq")
            tokens.append(_Token("STRING", text, pos))
        elif kind == "NAME":
            word = match.group()
            if word.lower() in _KEYWORDS:
                tokens.append(_Token(word.lower().upper(), word.lower(), pos))
            else:
                raise ExpressionError(
                    f"Unknown name {word!r} at position {pos} in {source!r}. "
                    f"Element references must be written ${{{word}}}."
                )
        else:
            tokens.append(_Token(kind, match.group(), pos))
        pos = match.end()
    tokens.append(_Token("EOF", None, len(source)))
    return tokens


# --------------------------------------------------------------------------
# AST
# --------------------------------------------------------------------------

class Node:
    pass


class Ref(Node):
    def __init__(self, name):
        self.name = name


class LinkRef(Node):
    """
    `${data_field.special_category}` — a column of the row `data_field` points at.

    `link` is an element of the *same* form; `column` is a column of the table
    that element draws its options from. Only one hop: see the parser.
    """

    def __init__(self, link, column):
        self.link, self.column = link, column


class Literal(Node):
    def __init__(self, value):
        self.value = value


class Compare(Node):
    def __init__(self, op, left, right):
        self.op, self.left, self.right = op, left, right


class BoolOp(Node):
    def __init__(self, op, left, right):
        self.op, self.left, self.right = op, left, right


class Not(Node):
    def __init__(self, operand):
        self.operand = operand


class Selected(Node):
    """`selected(${x}, 'v')` — is 'v' among the choices held by x?"""

    def __init__(self, haystack, needle):
        self.haystack, self.needle = haystack, needle


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens, source):
        self.tokens, self.source, self.i = tokens, source, 0

    @property
    def current(self):
        return self.tokens[self.i]

    def _advance(self):
        token = self.tokens[self.i]
        self.i += 1
        return token

    def _expect(self, kind):
        if self.current.kind != kind:
            raise ExpressionError(
                f"Expected {kind} but found {self.current.value!r} at position "
                f"{self.current.pos} in {self.source!r}"
            )
        return self._advance()

    def parse(self):
        node = self._or()
        if self.current.kind != "EOF":
            raise ExpressionError(
                f"Unexpected {self.current.value!r} at position {self.current.pos} "
                f"in {self.source!r}"
            )
        return node

    def _or(self):
        node = self._and()
        while self.current.kind == "OR":
            self._advance()
            node = BoolOp("or", node, self._and())
        return node

    def _and(self):
        node = self._not()
        while self.current.kind == "AND":
            self._advance()
            node = BoolOp("and", node, self._not())
        return node

    def _not(self):
        if self.current.kind == "NOT":
            self._advance()
            return Not(self._not())
        return self._comparison()

    def _comparison(self):
        left = self._primary()
        if self.current.kind == "OP":
            op = self._advance().value
            return Compare(op, left, self._primary())
        return left

    def _primary(self):
        token = self.current
        if token.kind == "LPAREN":
            self._advance()
            node = self._or()
            self._expect("RPAREN")
            return node
        if token.kind == "SELECTED":
            self._advance()
            self._expect("LPAREN")
            haystack = self._or()
            self._expect("COMMA")
            needle = self._or()
            self._expect("RPAREN")
            return Selected(haystack, needle)
        if token.kind == "REF":
            self._advance()
            parts = token.value.split(".")
            if len(parts) == 1:
                return Ref(token.value)
            if len(parts) == 2:
                return LinkRef(parts[0], parts[1])
            # Two hops would let one form's condition walk the whole schema, and
            # each hop is a row fetch on every keystroke. One is the case the
            # register actually has; refuse the rest rather than half-support it.
            raise ExpressionError(
                f"${{{token.value}}} at position {token.pos} in {self.source!r} "
                f"follows more than one link. A reference may cross at most one."
            )
        if token.kind == "STRING":
            self._advance()
            return Literal(token.value)
        if token.kind == "NUMBER":
            self._advance()
            text = token.value
            return Literal(float(text) if "." in text else int(text))
        if token.kind in ("TRUE", "FALSE"):
            self._advance()
            return Literal(token.kind == "TRUE")
        if token.kind == "NULL":
            self._advance()
            return Literal(None)
        raise ExpressionError(
            f"Unexpected {token.value!r} at position {token.pos} in {self.source!r}"
        )


def parse(source):
    """Parse an expression string into an AST. Raises ExpressionError."""
    if not isinstance(source, str) or not source.strip():
        raise ExpressionError(f"Empty expression: {source!r}")
    return _Parser(tokenise(source), source).parse()


def _children(node):
    for attr in ("left", "right", "operand", "haystack", "needle"):
        child = getattr(node, attr, None)
        if isinstance(child, Node):
            yield child


def referenced_elements(node):
    """
    Every element name an expression reads, for validation and callback wiring.

    A cross-link reference contributes the *link* element, which is exactly what
    the callback has to watch: the linked row can only change when the link
    itself is re-pointed.
    """
    if isinstance(node, Ref):
        return {node.name}
    if isinstance(node, LinkRef):
        return {node.link}
    found = set()
    for child in _children(node):
        found |= referenced_elements(child)
    return found


def referenced_links(node):
    """
    Every `(link_element, column)` pair an expression reads across a link.

    Separate from `referenced_elements` because the two are checked against
    different things: element names against this form, columns against the
    linked table.
    """
    if isinstance(node, LinkRef):
        return {(node.link, node.column)}
    found = set()
    for child in _children(node):
        found |= referenced_links(child)
    return found


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def is_truthy(value):
    """
    Emptiness is falsehood: an unanswered question is not a yes.

    Mirrors the emptiness test the submit-button validation already uses, so
    "answered" means the same thing to `relevant:` as it does to `required:`.
    """
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return bool(value)


def _as_number(value):
    """Return value as a number, or None if it is not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return None
    return None


def _as_choices(value):
    """
    Normalise a select_multiple value to a list of strings.

    Dash hands these over as a list, but the same value read back from the
    database is comma-joined (see how form_gen writes list values), so both
    shapes have to work or an expression would behave differently on an edit
    form than on an add form.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value)]


def _compare(op, left, right):
    # Numeric when both sides genuinely are; otherwise string. This keeps
    # "3" = 3 true, which matters because a dcc.Input yields strings even for
    # a field the config declares as an integer.
    left_num, right_num = _as_number(left), _as_number(right)
    if left_num is not None and right_num is not None:
        left_cmp, right_cmp = left_num, right_num
    else:
        if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
            # A multi-select holding exactly one choice compares as that choice;
            # otherwise it is not equal to any scalar. Use selected() instead.
            left = left[0] if isinstance(left, (list, tuple)) and len(left) == 1 else left
            right = right[0] if isinstance(right, (list, tuple)) and len(right) == 1 else right
        left_cmp = "" if left is None else str(left)
        right_cmp = "" if right is None else str(right)

    if op == "=":
        return left_cmp == right_cmp
    if op == "!=":
        return left_cmp != right_cmp
    try:
        if op == ">":
            return left_cmp > right_cmp
        if op == ">=":
            return left_cmp >= right_cmp
        if op == "<":
            return left_cmp < right_cmp
        if op == "<=":
            return left_cmp <= right_cmp
    except TypeError as exc:  # pragma: no cover - defensive
        raise ExpressionError(f"Cannot compare {left!r} {op} {right!r}") from exc
    raise ExpressionError(f"Unknown operator {op!r}")


def _value(node, context, resolve):
    """Evaluate a node to a raw value (not yet coerced to a boolean)."""
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, Ref):
        return context.get(node.name)
    if isinstance(node, LinkRef):
        # No resolver means nothing can follow the link, so the reference reads
        # as unanswered — the same reading an unset link gets. Erroring instead
        # would make every caller that does not care about links pass one.
        if resolve is None:
            return None
        return resolve(node.link, node.column, context.get(node.link))
    if isinstance(node, Compare):
        return _compare(node.op,
                        _value(node.left, context, resolve),
                        _value(node.right, context, resolve))
    if isinstance(node, BoolOp):
        left = is_truthy(_value(node.left, context, resolve))
        if node.op == "and":
            return left and is_truthy(_value(node.right, context, resolve))
        return left or is_truthy(_value(node.right, context, resolve))
    if isinstance(node, Not):
        return not is_truthy(_value(node.operand, context, resolve))
    if isinstance(node, Selected):
        needle = _value(node.needle, context, resolve)
        return str(needle) in _as_choices(_value(node.haystack, context, resolve))
    raise ExpressionError(f"Cannot evaluate node {node!r}")  # pragma: no cover


def evaluate(node, context, resolve=None):
    """
    Evaluate a parsed expression against {element_name: value} to a bool.

    `resolve(link_element, column, link_value) -> value` reads a column of a
    linked row, and is the only way this module reaches anything outside
    `context`. Injecting it keeps the parser and evaluator free of the database
    and keeps the language incapable of any lookup its caller did not supply.
    """
    return is_truthy(_value(node, context, resolve))
