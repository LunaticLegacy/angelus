"""Enforce the repository SQL binding rules.

The rules exist to catch the two failure modes that SQLite itself will not:

* **value misalignment** - positional ``?`` binding silently writes the wrong
  value into the wrong column whenever the neighbouring values share a type
  (``(scope, note_id)``, ``title`` vs ``content``), and a non-STRICT table will
  even accept a string in an INTEGER PRIMARY KEY column.
* **identifier interpolation** - a table name spliced into a statement cannot be
  validated by SQLite and turns a typo into either a crash or, worse, a query
  against the wrong table.

Rules (all fail-level, no exemptions):

1. ``INSERT`` must name its target columns, so adding a column cannot silently
   re-align the values.
2. SQL must never be assembled by interpolation: no f-string, ``+``, ``%`` or
   ``.format()``. A part-built statement only fails on the first query that
   reaches it in production, and it defeats every static check below.
3. Parameterised SQL must use ``:name`` placeholders bound with a dict.
4. Identifiers (table / column names) must come from a literal allowlist or a
   dict dispatch, never from interpolation.

Statements that legitimately carry no parameters are recognised and skipped:
transaction control and ``PRAGMA`` (by leading keyword), and parameter-free
statements (no placeholder of either kind and no binding argument).

Every SQL argument must be statically resolvable, because a dict of literals is
what makes a rule violation visible without connecting to a database. A module
constant, a variable bound in an enclosing scope, an ``if``/``else`` pair, a
``Subscript`` of a literal ``dict`` (identifier dispatch), and nested combinations
of those are all understood.

Usage:
    python scripts/check_sql_binding.py [--root PATH] [--path DIR ...]
    python scripts/check_sql_binding.py --self-test

Exit status is 1 when any violation is found.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

# Only these attributes issue SQL. ``sqlite3.connect`` is deliberately absent: a
# ``file:...?mode=ro`` URI is a connection string, not a statement.
CALL_ATTRIBUTES = frozenset({"execute", "executemany", "executescript"})

# Transaction control and PRAGMA take no parameters, so the binding rules do not
# apply to them. They are recognised by their leading keyword.
UNBOUND_LEADERS = frozenset(
    {"BEGIN", "COMMIT", "END", "ROLLBACK", "SAVEPOINT", "RELEASE", "PRAGMA"}
)

# Where a caller can hand the binding over under a name instead of positionally.
PARAMETER_KEYWORDS = frozenset({"parameters", "params", "seq_of_parameters"})

# Build artefacts and virtualenvs hold stale copies of the same SQL.
SKIP_DIRECTORIES = frozenset(
    {
        "build",
        "dist",
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "site-packages",
        ".angelus-state",
        ".mypy_cache",
        ".ruff_cache",
    }
)

DEFAULT_ROOTS = ("angelus", "llmfetcher", "tests", "scripts")

INSERT_PATTERN = re.compile(
    r"\bINSERT\s+(?:OR\s+[A-Za-z]+\s+)?INTO\s+(?P<table>[A-Za-z_][A-Za-z0-9_.]*)",
    re.IGNORECASE,
)
NAMED_PLACEHOLDER = re.compile(r":[A-Za-z_][A-Za-z0-9_]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"--[^\n]*")
STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")
# An identifier slot filled by interpolation, e.g. ``FROM {table}``.
IDENTIFIER_SLOT = re.compile(
    r"\b(?:FROM|INTO|JOIN|UPDATE|TABLE|ORDER\s+BY|GROUP\s+BY)\s*\{",
    re.IGNORECASE,
)


def _strip_noise(sql: str) -> str:
    """Remove comments and string literals so scanning sees code only.

    A ``?`` or ``:name`` inside a comment or a quoted value is data, not a
    placeholder, and must not be reported.

    Args:
        sql: Raw statement text.

    Returns:
        The statement with block comments, line comments and single-quoted
        literals replaced by an empty literal.
    """
    text = BLOCK_COMMENT.sub(" ", sql)
    text = LINE_COMMENT.sub(" ", text)
    return STRING_LITERAL.sub("''", text)


@dataclass(frozen=True)
class Violation:
    """One rule breach, located by file and line."""

    path: str
    line: int
    rule: int
    message: str

    def render(self) -> str:
        """Format this violation as a single reportable line."""
        return f"{self.path}:{self.line}: rule {self.rule}: {self.message}"


class _Scope:
    """Name bindings visible at a line, chained to the enclosing scope.

    A statement is resolved at the line that uses it, so a module constant
    assigned above the function wins over a same-named local assigned below it.
    """

    def __init__(
        self,
        assignments: dict[str, list[tuple[int, ast.expr]]] | None = None,
        parent: "_Scope | None" = None,
    ) -> None:
        self._assignments = assignments or {}
        self._parent = parent

    def lookup(self, name: str, lineno: int) -> ast.expr | None:
        """Return the last binding of ``name`` assigned at or before ``lineno``."""
        chosen = None
        for line, node in self._assignments.get(name, ()):
            if line > lineno:
                break
            chosen = node
        if chosen is not None:
            return chosen
        if self._parent is not None:
            return self._parent.lookup(name, lineno)
        return None


def _collect_assignments(nodes: list[ast.stmt]) -> dict[str, list[tuple[int, ast.expr]]]:
    """Collect ``name = value`` bindings that live directly in ``nodes``.

    Nested function, class and lambda bodies are skipped: their names are not
    visible in the scope that owns ``nodes``.
    """
    found: dict[str, list[tuple[int, ast.expr]]] = {}
    pending = list(nodes)
    while pending:
        node = pending.pop()
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.setdefault(target.id, []).append((node.lineno, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                found.setdefault(node.target.id, []).append((node.lineno, node.value))
        pending.extend(ast.iter_child_nodes(node))
    for entries in found.values():
        entries.sort(key=lambda item: item[0])
    return found


def _fstring_source(node: ast.JoinedStr) -> str:
    """Return the literal text of an f-string, keeping its interpolation slots."""
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append("{...}")
    return "".join(parts)


class _FileChecker:
    """Walk one module and apply the four rules to every SQL call site."""

    def __init__(self, path: Path, tree: ast.Module) -> None:
        self.path = path
        self.tree = tree
        self.violations: list[Violation] = []
        self.statements = 0
        self.call_sites = 0
        self.module_scope = _Scope(_collect_assignments(tree.body))

    # -- reporting ---------------------------------------------------------
    def _fail(self, node: ast.AST, rule: int, message: str) -> None:
        """Record one violation against the line of ``node``.

        A dict-dispatched call site resolves to several statement variants; when
        they share a defect the identical finding is reported once.
        """
        violation = Violation(str(self.path), getattr(node, "lineno", 0), rule, message)
        if violation not in self.violations:
            self.violations.append(violation)

    # -- SQL text resolution ----------------------------------------------
    def _resolve(
        self,
        node: ast.expr,
        scope: _Scope,
        seen: frozenset[str] = frozenset(),
    ) -> tuple[list[str], list[str]]:
        """Resolve a SQL argument into literal texts plus interpolation reasons.

        Args:
            node: Expression passed as the statement argument.
            scope: Name bindings visible at the call site.
            seen: Names already followed, to stop on a self-referencing binding.

        Returns:
            ``(texts, reasons)``. ``texts`` holds every statically known variant
            of the statement; ``reasons`` names each way the text was assembled
            dynamically instead of written as one literal.
        """
        if isinstance(node, ast.Constant):
            return ([node.value], []) if isinstance(node.value, str) else ([], [])
        if isinstance(node, ast.JoinedStr):
            return [], ["f-string"]
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Add):
                return [], ["'+' concatenation"]
            if isinstance(node.op, ast.Mod):
                return [], ["'%' formatting"]
            return [], ["an arithmetic expression"]
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "format":
                return [], [".format()"]
            if isinstance(func, ast.Attribute) and func.attr == "join":
                return [], ["str.join()"]
            return [], ["a computed expression"]
        if isinstance(node, ast.IfExp):
            texts: list[str] = []
            reasons: list[str] = []
            for branch in (node.body, node.orelse):
                branch_texts, branch_reasons = self._resolve(branch, scope, seen)
                texts.extend(branch_texts)
                reasons.extend(branch_reasons)
            return texts, reasons
        if isinstance(node, ast.BoolOp):
            texts = []
            reasons = []
            for value in node.values:
                value_texts, value_reasons = self._resolve(value, scope, seen)
                texts.extend(value_texts)
                reasons.extend(value_reasons)
            return texts, reasons
        if isinstance(node, ast.Dict):
            # Identifier dispatch: every literal branch is a candidate statement.
            texts = []
            reasons = []
            for value in node.values:
                value_texts, value_reasons = self._resolve(value, scope, seen)
                texts.extend(value_texts)
                reasons.extend(value_reasons)
            return texts, reasons
        if isinstance(node, ast.Subscript):
            return self._resolve(node.value, scope, seen)
        if isinstance(node, ast.Name):
            if node.id in seen:
                return [], [f"a self-referencing binding {node.id!r}"]
            bound = scope.lookup(node.id, node.lineno)
            if bound is None:
                return [], [f"an unresolved name {node.id!r}"]
            return self._resolve(bound, scope, seen | {node.id})
        return [], ["a non-literal expression"]

    def _param_kind(
        self,
        node: ast.expr | None,
        scope: _Scope,
        seen: frozenset[str] = frozenset(),
    ) -> str:
        """Classify a binding argument as ``dict``, ``sequence`` or ``unknown``."""
        if node is None:
            return "absent"
        if isinstance(node, (ast.Dict, ast.DictComp)):
            return "dict"
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "dict":
                return "dict"
            return "unknown"
        if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            return "dict" if isinstance(node.elt, (ast.Dict, ast.DictComp)) else "sequence"
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if not node.elts:
                return "dict"
            if all(isinstance(element, (ast.Dict, ast.DictComp)) for element in node.elts):
                return "dict"
            return "sequence"
        if isinstance(node, ast.IfExp):
            # ``{"a": value} if flag else {}`` is still a dict: judge both branches
            # and demand they agree, so a conditional cannot hide a sequence.
            kinds = {
                self._param_kind(branch, scope, seen)
                for branch in (node.body, node.orelse)
            }
            return kinds.pop() if len(kinds) == 1 else "unknown"
        if isinstance(node, ast.BoolOp):
            kinds = {self._param_kind(value, scope, seen) for value in node.values}
            return kinds.pop() if len(kinds) == 1 else "unknown"
        if isinstance(node, ast.Name):
            if node.id in seen:
                return "unknown"
            bound = scope.lookup(node.id, node.lineno)
            if bound is None:
                return "unknown"
            return self._param_kind(bound, scope, seen | {node.id})
        return "unknown"

    # -- rule application --------------------------------------------------
    def _apply_sql_rules(
        self,
        node: ast.AST,
        sql: str,
        params: ast.expr | None,
        scope: _Scope,
    ) -> None:
        """Apply rules 1 and 3 to one statically known statement."""
        body = sql.strip()
        if not body:
            return
        head = body.split(None, 1)[0].upper() if " " in body else body.upper()
        if head in UNBOUND_LEADERS:
            return
        self.statements += 1
        code = _strip_noise(sql)

        # Rule 1: INSERT must name its target columns.
        match = INSERT_PATTERN.search(code)
        if match is not None:
            remainder = code[match.end() :].lstrip()
            if not remainder.startswith("("):
                self._fail(
                    node,
                    1,
                    f"INSERT into {match.group('table')!r} without a column list; "
                    "list the columns so a new column cannot silently re-align the values",
                )

        has_positional = "?" in code
        has_named = NAMED_PLACEHOLDER.search(code) is not None
        kind = self._param_kind(params, scope)

        # Rule 3: named placeholders bound with a dict.
        if has_positional:
            self._fail(
                node,
                3,
                "positional '?' placeholder; bind by name with ':name' and a dict",
            )
        if kind == "absent":
            if has_named:
                self._fail(
                    node,
                    3,
                    "statement declares ':name' placeholders but no parameter mapping "
                    "was supplied",
                )
            return
        if not has_named:
            if not has_positional:
                self._fail(
                    node,
                    3,
                    "parameters were supplied but the statement declares no ':name' "
                    "placeholder",
                )
            return
        if kind == "sequence":
            self._fail(
                node,
                3,
                "parameters are a sequence; bind a dict so each value is tied to its name",
            )
        elif kind == "unknown":
            self._fail(
                node,
                3,
                "cannot verify that the binding is a dict; use a dict literal, a dict "
                "comprehension, or a name bound to one",
            )

    def _inspect_call(self, node: ast.Call, scope: _Scope) -> None:
        """Apply the rules to one ```execute``-family call."""
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in CALL_ATTRIBUTES:
            return
        self.call_sites += 1
        if not node.args:
            self._fail(node, 3, f".{func.attr}() called without a SQL argument")
            return
        sql_node = node.args[0]
        params: ast.expr | None = node.args[1] if len(node.args) > 1 else None
        if params is None:
            for keyword in node.keywords:
                if keyword.arg in PARAMETER_KEYWORDS:
                    params = keyword.value

        texts, reasons = self._resolve(sql_node, scope)
        for reason in reasons:
            self._fail(
                node,
                2,
                f"SQL assembled with {reason}; write the statement as one literal and "
                "select variants by dict lookup",
            )
            if isinstance(sql_node, ast.JoinedStr):
                if IDENTIFIER_SLOT.search(_fstring_source(sql_node)):
                    self._fail(
                        node,
                        4,
                        "identifier interpolated into the statement; dispatch on a "
                        "literal allowlist instead, e.g. "
                        "{'messages': '...', 'archive': '...'}",
                    )
        if not texts:
            return
        seen_texts: set[str] = set()
        for sql in texts:
            if sql in seen_texts:
                continue
            seen_texts.add(sql)
            self._apply_sql_rules(node, sql, params, scope)

    # -- traversal ---------------------------------------------------------
    def _walk_body(self, body: list[ast.stmt], scope: _Scope) -> None:
        """Walk a statement list in ``scope``."""
        for statement in body:
            self._walk(statement, scope)

    def _walk(self, node: ast.AST, scope: _Scope) -> None:
        """Walk ``node``, opening a nested scope at every function definition.

        The node itself is dispatched first: a method reached through its class
        body must open its own scope, exactly like a module-level function.
        """
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._walk_signature(node, scope)
            inner = _Scope(_collect_assignments(node.body), parent=scope)
            self._walk_body(node.body, inner)
            return
        if isinstance(node, ast.Lambda):
            # A lambda body closes over the enclosing scope.
            self._walk(node.body, scope)
            return
        if isinstance(node, ast.ClassDef):
            self._walk_signature(node, scope)
            self._walk_body(node.body, scope)
            return
        if isinstance(node, ast.Call):
            self._inspect_call(node, scope)
        for child in ast.iter_child_nodes(node):
            self._walk(child, scope)

    def _walk_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        scope: _Scope,
    ) -> None:
        """Walk the decorators, defaults and annotations evaluated in ``scope``."""
        for decorator in getattr(node, "decorator_list", ()):
            self._walk(decorator, scope)
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                self._walk(base, scope)
            return
        arguments = node.args
        for default in list(arguments.defaults) + [
            value for value in arguments.kw_defaults if value is not None
        ]:
            self._walk(default, scope)
        if node.returns is not None:
            self._walk(node.returns, scope)

    def run(self) -> None:
        """Check the whole module."""
        self._walk(self.tree, self.module_scope)


def _iter_sources(root: Path, bases: tuple[str, ...]) -> list[Path]:
    """Return every ``.py`` file under ``bases``, skipping build artefacts."""
    found: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        start = root / base
        if start.is_file():
            candidates = [start]
        elif start.is_dir():
            candidates = sorted(start.rglob("*.py"))
        else:
            continue
        for path in candidates:
            if any(part in SKIP_DIRECTORIES for part in path.relative_to(root).parts):
                continue
            if path in seen:
                continue
            seen.add(path)
            found.append(path)
    return found


def check_file(path: Path) -> _FileChecker:
    """Parse and check one file, recording an unparsable file as a violation."""
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(path))
    checker = _FileChecker(path, tree)
    checker.run()
    return checker


_SELF_TEST_SOURCE = """
_TABLE_SQL = {
    "notes": "SELECT COUNT(*) FROM notes",
    "archive": "SELECT COUNT(*) FROM archive",
}

_PAGE_ROWS_SQL = {
    (False, False): "SELECT timeline FROM messages ORDER BY timeline DESC LIMIT :limit",
    (False, True): (
        "SELECT timeline FROM messages WHERE timeline < :before "
        "ORDER BY timeline DESC LIMIT :limit"
    ),
}


def rule_1_insert_without_columns(db):
    db.execute("INSERT INTO notes VALUES (:a, :b)", {"a": 1, "b": 2})


def rule_2_fstring(db, value):
    db.execute(f"SELECT * FROM notes WHERE note_id = '{value}'")


def rule_2_plus(db, value):
    db.execute("SELECT * FROM notes WHERE note_id = '" + value + "'")


def rule_2_format(db, value):
    db.execute("SELECT * FROM notes WHERE note_id = '{}'".format(value))


def rule_2_percent(db, value):
    db.execute("SELECT * FROM notes WHERE note_id = '%s'" % value)


def rule_2_unresolved(db, statement):
    db.execute(statement)


def rule_3_positional(db, value):
    db.execute("SELECT * FROM notes WHERE note_id = ?", (value,))


def rule_3_sequence_for_named(db, value):
    db.execute("SELECT * FROM notes WHERE note_id = :note_id", (value,))


def rule_3_cannot_verify(db, params):
    db.execute("SELECT * FROM notes WHERE note_id = :note_id", params)


def rule_4_identifier_interpolation(db, table):
    db.execute(f"SELECT COUNT(*) FROM {table}")


def good_dict_binding(db, value):
    db.execute("SELECT * FROM notes WHERE note_id = :note_id", {"note_id": value})


def good_executemany_dicts(db, rows):
    db.executemany(
        "INSERT OR REPLACE INTO notes(note_id, title) VALUES (:note_id, :title)",
        [{"note_id": key, "title": title} for key, title in rows],
    )


def good_dict_dispatch(db, table):
    db.execute(_TABLE_SQL[table])


def good_page_variant(db, include_archive, has_cursor):
    parameters = {"limit": 10, "before": None}
    db.execute(_PAGE_ROWS_SQL[(include_archive, has_cursor)], parameters)


def good_conditional_variant(db, has_cursor):
    statement = _TABLE_SQL["notes"] if has_cursor else _TABLE_SQL["archive"]
    db.execute(statement)


def good_ddl_and_transaction(db):
    db.execute("BEGIN IMMEDIATE")
    db.execute("COMMIT")
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        "CREATE TABLE IF NOT EXISTS notes(note_id TEXT PRIMARY KEY, title TEXT)"
    )


def good_noise_only(db):
    db.execute("SELECT * FROM notes WHERE title = 'why? because: sure' -- trailing ?")


def good_superset_parameters(db, before, limit):
    parameters = {"before": before, "limit": limit}
    db.execute("SELECT * FROM notes WHERE note_id < :before LIMIT :limit", parameters)
    db.execute("SELECT * FROM notes WHERE note_id > :before", parameters)
"""

# Each expected finding as ``(rule, function)``. Pairing the two means a dead
# rule cannot hide behind another rule firing twice on the same line.
_SELF_TEST_EXPECTED = frozenset(
    {
        (1, "rule_1_insert_without_columns"),
        (2, "rule_2_fstring"),
        (2, "rule_2_plus"),
        (2, "rule_2_format"),
        (2, "rule_2_percent"),
        (2, "rule_2_unresolved"),
        (3, "rule_3_positional"),
        (3, "rule_3_sequence_for_named"),
        (3, "rule_3_cannot_verify"),
        (2, "rule_4_identifier_interpolation"),
        (4, "rule_4_identifier_interpolation"),
    }
)


def _self_test() -> int:
    """Check the planted cases and return a process exit status."""
    source = textwrap.dedent(_SELF_TEST_SOURCE).lstrip("\n")
    tree = ast.parse(source, filename="<self-test>")
    checker = _FileChecker(Path("<self-test>"), tree)
    checker.run()

    lines = source.splitlines()

    def owner(lineno: int) -> str:
        """Return the module-level function that encloses ``lineno``."""
        found = "<module>"
        for position, text in enumerate(lines[:lineno], start=1):
            stripped = text.lstrip()
            if stripped.startswith("def "):
                found = stripped[4:].split("(", 1)[0]
        return found

    found = {(violation.rule, owner(violation.line)) for violation in checker.violations}
    for violation in checker.violations:
        print(f"  {violation.render()}")
    missing = sorted(_SELF_TEST_EXPECTED - found)
    unexpected = sorted(found - _SELF_TEST_EXPECTED)
    for rule, name in missing:
        print(f"MISSED: rule {rule} did not fire on {name}()")
    for rule, name in unexpected:
        print(f"FALSE POSITIVE: rule {rule} fired on {name}()")
    verdict = "PASS" if not missing and not unexpected else "FAIL"
    print(
        f"self-test {verdict}: {len(checker.violations)} violations over "
        f"{checker.call_sites} call sites, {len(_SELF_TEST_EXPECTED)} expected"
    )
    return 0 if verdict == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    """Run the checker over the repository and return a process exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="repository root to scan (default: current directory)",
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        help="restrict the scan to this root-relative path (repeatable)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="verify the checker against planted rule violations and exit",
    )
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        return _self_test()
    root = Path(arguments.root).resolve()
    bases = tuple(arguments.paths) if arguments.paths else DEFAULT_ROOTS

    violations: list[Violation] = []
    statements = 0
    call_sites = 0
    scanned = 0
    for path in _iter_sources(root, bases):
        try:
            checker = check_file(path)
        except (OSError, SyntaxError, UnicodeDecodeError) as error:
            violations.append(Violation(str(path), 0, 0, f"cannot parse: {error}"))
            continue
        scanned += 1
        violations.extend(checker.violations)
        statements += checker.statements
        call_sites += checker.call_sites

    violations.sort(key=lambda violation: (violation.path, violation.line, violation.rule))
    for violation in violations:
        print(violation.render())

    per_rule = {rule: 0 for rule in (0, 1, 2, 3, 4)}
    for violation in violations:
        per_rule[violation.rule] = per_rule.get(violation.rule, 0) + 1
    print(
        f"\nscanned {scanned} files, {call_sites} execute call sites, "
        f"{statements} SQL statements, {len(violations)} violations "
        f"(rule 1: {per_rule[1]}, rule 2: {per_rule[2]}, "
        f"rule 3: {per_rule[3]}, rule 4: {per_rule[4]}, "
        f"unparsable: {per_rule[0]})"
    )
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
