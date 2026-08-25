"""Synchronize generated Function Map and Class Map sections in every INDEX.

The nearest ``INDEX.md`` owns source files below it. Traversal stops when a
nested index is encountered, which keeps each map local and prevents symbols
from being duplicated in parent maps.
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BEGIN = "<!-- BEGIN GENERATED SYMBOL MAP -->"
END = "<!-- END GENERATED SYMBOL MAP -->"
SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".rs"}
SKIP_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "workspace",
}


@dataclass(frozen=True)
class FunctionSymbol:
    """One searchable function or method map row.

    Attributes:
        path: Source path relative to the owning index directory.
        line: One-based declaration line used by the source link.
        name: Function name, qualified by its class for methods.
        inputs: Parameter names paired with declared or unknown types.
        output: Declared return type or a conservative unknown type.
        semantics: Concise behavior derived from source documentation.
    """

    path: Path
    line: int
    name: str
    inputs: str
    output: str
    semantics: str


@dataclass(frozen=True)
class ClassSymbol:
    """One searchable class map row.

    Attributes:
        path: Source path relative to the owning index directory.
        line: One-based declaration line used by the source link.
        name: Declared class name.
        inputs: Constructor parameters or annotated instance fields.
        bases: Direct base classes visible in the declaration.
        semantics: Concise class responsibility from its docstring.
    """

    path: Path
    line: int
    name: str
    inputs: str
    bases: str
    semantics: str


def _clean(value: str, fallback: str) -> str:
    """Normalize source text for a single Markdown table cell.

    Args:
        value: Raw annotation, comment, or docstring text.
        fallback: Text used when normalization removes all content.

    Returns:
        A one-line, pipe-safe Markdown cell value.
    """
    text = " ".join(value.strip().split())
    return (text or fallback).replace("|", "\\|")


def _summary(docstring: str | None, fallback: str) -> str:
    """Return the first documented semantic sentence for a symbol.

    Args:
        docstring: Parsed source docstring, when one exists.
        fallback: Conservative declaration-based description.

    Returns:
        A compact single-line semantic summary.
    """
    if not docstring:
        return fallback
    paragraph = docstring.strip().split("\n\n", 1)[0]
    return _clean(paragraph, fallback)


def _annotation(node: ast.expr | None, fallback: str = "Any") -> str:
    """Render a Python type annotation without evaluating it.

    Args:
        node: Annotation syntax node or ``None``.
        fallback: Type used for unannotated declarations.

    Returns:
        Source-like annotation text.
    """
    return ast.unparse(node) if node is not None else fallback


def _python_inputs(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render Python parameters and types for an index row.

    Args:
        node: Parsed function or method declaration.

    Returns:
        Comma-separated ``name: type`` declarations, excluding ``self`` and
        ``cls``; ``None`` denotes an empty input list.
    """
    positional = [*node.args.posonlyargs, *node.args.args]
    parts = [
        f"{argument.arg}: {_annotation(argument.annotation)}"
        for argument in positional
        if argument.arg not in {"self", "cls"}
    ]
    if node.args.vararg:
        parts.append(f"*{node.args.vararg.arg}: {_annotation(node.args.vararg.annotation)}")
    parts.extend(
        f"{argument.arg}: {_annotation(argument.annotation)}"
        for argument in node.args.kwonlyargs
    )
    if node.args.kwarg:
        parts.append(f"**{node.args.kwarg.arg}: {_annotation(node.args.kwarg.annotation)}")
    return ", ".join(parts) or "None"


def _python_symbols(path: Path, relative: Path) -> tuple[list[FunctionSymbol], list[ClassSymbol]]:
    """Extract documented Python functions, methods, and classes.

    Args:
        path: Python source file to parse.
        relative: Source path relative to its owning index.

    Returns:
        Function/method rows followed by class rows.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions: list[FunctionSymbol] = []
    classes: list[ClassSymbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(FunctionSymbol(
                relative, node.lineno, node.name, _python_inputs(node),
                _annotation(node.returns),
                _summary(ast.get_docstring(node), f"Implement `{node.name}`."),
            ))
            continue
        if not isinstance(node, ast.ClassDef):
            continue
        constructor = next(
            (item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__"),
            None,
        )
        fields = [
            f"{item.target.id}: {_annotation(item.annotation)}"
            for item in node.body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        ]
        inputs = _python_inputs(constructor) if constructor else ", ".join(fields) or "None"
        bases = ", ".join(ast.unparse(base) for base in node.bases) or "object"
        classes.append(ClassSymbol(
            relative, node.lineno, node.name, inputs, bases,
            _summary(ast.get_docstring(node), f"Provide `{node.name}` behavior."),
        ))
        for method in node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if method.name == "__init__":
                continue
            functions.append(FunctionSymbol(
                relative, method.lineno, f"{node.name}.{method.name}",
                _python_inputs(method), _annotation(method.returns),
                _summary(ast.get_docstring(method), f"Implement `{node.name}.{method.name}`."),
            ))
    return functions, classes


JS_FUNCTION = re.compile(
    r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)"
    r"|^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>"
)
JS_CLASS = re.compile(r"(?m)^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)(?:\s+extends\s+([^\s{]+))?")


def _javascript_symbols(path: Path, relative: Path) -> tuple[list[FunctionSymbol], list[ClassSymbol]]:
    """Extract JavaScript declarations with conservative unknown types.

    Args:
        path: JavaScript source file to inspect.
        relative: Source path relative to its owning index.

    Returns:
        Function rows and class rows found by declaration-level patterns.
    """
    source = path.read_text(encoding="utf-8")
    functions: list[FunctionSymbol] = []
    for match in JS_FUNCTION.finditer(source):
        name = match.group(1) or match.group(3)
        raw_inputs = match.group(2) if match.group(1) else match.group(4)
        if raw_inputs.strip().startswith(("{", "[")):
            inputs = "options: object"
        else:
            parameters = [
                part.strip().split("=", 1)[0].strip().removeprefix("...")
                for part in raw_inputs.split(",")
                if part.strip()
            ]
            inputs = ", ".join(f"{parameter}: unknown" for parameter in parameters) or "None"
        words = " ".join(
            part.casefold()
            for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", name)
        )
        output = "Promise<unknown>" if "async" in match.group(0).split("function", 1)[0] or "= async" in match.group(0) else "unknown"
        functions.append(FunctionSymbol(
            relative, source.count("\n", 0, match.start()) + 1, name, inputs,
            output, f"Perform the browser runtime operation: {words or name}.",
        ))
    classes = [
        ClassSymbol(
            relative, source.count("\n", 0, match.start()) + 1,
            match.group(1), "unknown", match.group(2) or "object",
            f"Provide `{match.group(1)}` browser-side state and behavior.",
        )
        for match in JS_CLASS.finditer(source)
    ]
    return functions, classes


RUST_FUNCTION = re.compile(r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:->\s*([^\n{]+))?")
RUST_CLASS = re.compile(r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?(struct|enum)\s+([A-Za-z_]\w*)")


def _rust_symbols(path: Path, relative: Path) -> tuple[list[FunctionSymbol], list[ClassSymbol]]:
    """Extract Rust functions and data types from source declarations.

    Args:
        path: Rust source file to inspect.
        relative: Source path relative to its owning index.

    Returns:
        Function rows and struct/enum rows.
    """
    source = path.read_text(encoding="utf-8")
    functions = [
        FunctionSymbol(
            relative, source.count("\n", 0, match.start()) + 1, match.group(1),
            _clean(match.group(2), "None"), _clean(match.group(3) or "()", "()"),
            f"Implement `{match.group(1)}` in the desktop shell.",
        )
        for match in RUST_FUNCTION.finditer(source)
    ]
    classes = [
        ClassSymbol(
            relative, source.count("\n", 0, match.start()) + 1, match.group(2),
            "See declaration", match.group(1),
            f"Represent `{match.group(2)}` desktop-shell state.",
        )
        for match in RUST_CLASS.finditer(source)
    ]
    return functions, classes


def _owned_sources(index: Path) -> Iterable[Path]:
    """Yield source files owned by one nearest-index boundary.

    Args:
        index: INDEX file whose parent directory defines the traversal root.

    Yields:
        Supported source files, excluding generated/build directories and any
        subtree with its own ``INDEX.md``.
    """
    root = index.parent
    for child in sorted(root.iterdir()):
        if child == index or child.name in SKIP_DIRECTORIES:
            continue
        if child.is_file() and child.suffix in SOURCE_SUFFIXES:
            yield child
            continue
        if not child.is_dir() or (child / "INDEX.md").is_file():
            continue
        for path in sorted(child.rglob("*")):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            relative_parts = path.relative_to(child).parts[:-1]
            if any(part in SKIP_DIRECTORIES for part in relative_parts):
                continue
            if any((parent / "INDEX.md").is_file() for parent in path.parents if parent != root and root in parent.parents):
                continue
            yield path


def _source_link(symbol: FunctionSymbol | ClassSymbol) -> str:
    """Build a relative source link for a symbol row.

    Args:
        symbol: Extracted function or class metadata.

    Returns:
        Markdown link with a GitHub-compatible line anchor.
    """
    path = symbol.path.as_posix()
    return f"[{path}]({path}#L{symbol.line})"


def _render_map(index: Path) -> str:
    """Render deterministic Function Map and Class Map tables.

    Args:
        index: INDEX whose owned sources are inspected.

    Returns:
        Complete generated section including stable replacement markers.
    """
    functions: list[FunctionSymbol] = []
    classes: list[ClassSymbol] = []
    for source in _owned_sources(index):
        relative = source.relative_to(index.parent)
        if source.suffix == ".py":
            source_functions, source_classes = _python_symbols(source, relative)
        elif source.suffix in {".js", ".mjs"}:
            source_functions, source_classes = _javascript_symbols(source, relative)
        else:
            source_functions, source_classes = _rust_symbols(source, relative)
        functions.extend(source_functions)
        classes.extend(source_classes)
    functions.sort(key=lambda item: (item.path.as_posix(), item.line, item.name))
    classes.sort(key=lambda item: (item.path.as_posix(), item.line, item.name))

    rows = [BEGIN, "", "## Function Map", "", "| Source | Function / method | Input types | Output type | Semantics |", "|---|---|---|---|---|"]
    if functions:
        rows.extend(
            f"| {_source_link(item)} | `{item.name}` | `{_clean(item.inputs, 'None')}` | `{_clean(item.output, 'Any')}` | {item.semantics} |"
            for item in functions
        )
    else:
        rows.append("| — | — | `None` | `None` | 本索引范围不直接拥有可执行函数；沿 Route Map 进入下级索引。 |")
    rows.extend(["", "## Class Map", "", "| Source | Class | Constructor / field input types | Base(s) | Semantics |", "|---|---|---|---|---|"])
    if classes:
        rows.extend(
            f"| {_source_link(item)} | `{item.name}` | `{_clean(item.inputs, 'None')}` | `{_clean(item.bases, 'object')}` | {item.semantics} |"
            for item in classes
        )
    else:
        rows.append("| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |")
    rows.extend(["", END, ""])
    return "\n".join(rows)


def _updated_index(index: Path) -> str:
    """Replace or append one generated symbol-map section.

    Args:
        index: INDEX file to update in memory.

    Returns:
        Full normalized file content with the current generated map.
    """
    current = index.read_text(encoding="utf-8")
    if BEGIN in current:
        prefix, remainder = current.split(BEGIN, 1)
        if END not in remainder:
            raise ValueError(f"missing {END!r} in {index}")
        _, suffix = remainder.split(END, 1)
        current = prefix.rstrip() + "\n\n" + suffix.lstrip()
    return current.rstrip() + "\n\n" + _render_map(index)


def sync_indexes(root: Path, *, check: bool) -> list[Path]:
    """Synchronize every repository INDEX while preserving prose sections.

    Args:
        root: Repository root to scan recursively.
        check: When true, report stale indexes without writing them.

    Returns:
        Sorted INDEX paths whose generated section differed.
    """
    changed: list[Path] = []
    indexes = [
        path for path in root.rglob("INDEX.md")
        if not any(part in SKIP_DIRECTORIES for part in path.relative_to(root).parts)
    ]
    for index in sorted(indexes):
        updated = _updated_index(index)
        if updated == index.read_text(encoding="utf-8"):
            continue
        changed.append(index)
        if not check:
            index.write_text(updated, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    """Run INDEX synchronization or its non-mutating drift check.

    Args:
        argv: Optional CLI arguments; defaults to the process argument vector.

    Returns:
        Zero on success, or one when ``--check`` finds stale indexes.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args(argv)
    changed = sync_indexes(arguments.root.resolve(), check=arguments.check)
    for path in changed:
        print(path.relative_to(arguments.root.resolve()))
    return int(arguments.check and bool(changed))


if __name__ == "__main__":
    raise SystemExit(main())
