"""
Interpreter compatibility — the scripts must run on the Python macOS ships.

Two failure modes, both invisible when developing on a newer interpreter:

  Syntax newer than the floor (match statements, walrus in comprehensions...),
  caught by parsing with feature_version pinned to the floor.

  PEP 604 unions in annotations (`list[str] | None`), which parse everywhere but
  raise TypeError when the annotation is evaluated at def time before 3.10.
  `from __future__ import annotations` defers that evaluation and makes them safe.
"""

import ast
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent
MIN_VERSION = (3, 9)

SOURCES = sorted(
    list(SCRIPT_DIR.glob("*.py"))
    + list((SCRIPT_DIR / "lib").glob("*.py"))
    + list((SCRIPT_DIR / "tests").glob("*.py"))
)


def _defers_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )


def _annotations(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.AnnAssign, ast.arg)) and node.annotation:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            yield node.returns


def _union_lineno(annotation) -> int:
    for node in ast.walk(annotation):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return node.lineno
    return 0


@pytest.mark.parametrize("source", SOURCES, ids=lambda p: p.name)
def test_syntax_parses_on_floor_version(source):
    """Module uses no syntax newer than the oldest supported interpreter."""
    try:
        ast.parse(source.read_text(), filename=str(source), feature_version=MIN_VERSION)
    except SyntaxError as error:
        pytest.fail(
            f"{source.name}:{error.lineno} uses syntax newer than "
            f"Python {MIN_VERSION[0]}.{MIN_VERSION[1]}: {error.msg}"
        )


@pytest.mark.parametrize("source", SOURCES, ids=lambda p: p.name)
def test_union_annotations_are_deferred(source):
    """`X | None` annotations require `from __future__ import annotations` below 3.10."""
    tree = ast.parse(source.read_text(), filename=str(source))
    if _defers_annotations(tree):
        return

    for annotation in _annotations(tree):
        lineno = _union_lineno(annotation)
        assert not lineno, (
            f"{source.name}:{lineno} evaluates a `X | Y` annotation at import time, "
            f"which raises TypeError before Python 3.10. "
            f"Add `from __future__ import annotations` to this module."
        )
