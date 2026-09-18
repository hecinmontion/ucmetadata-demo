"""Mechanical change-class routing (ADR-006): decides whether one change
request's changed file paths take the *content* fast path (pre-approved by
class, that contract's code owners only) or the *schema* slow path (the
platform team's own release review), by reading `change_classes.yaml` --
never by a human arguing the class of a specific change request (Rules &
Constraints: "which path a change takes is decided mechanically, not argued
per change request").

`classify_change(changed_paths)` is the whole surface: pure classification
logic over a list of paths, with no CI system, git plumbing or workflow
runner wired in here. A future workflow step calls this (via the CLI, once
that exists) against `git diff --name-only`'s output; this module does not
know or care that the caller will eventually be a workflow.

Policy, stated once rather than left to be inferred from the code: a change
touching *both* classes in one change request is routed as `schema` --
the heavier path wins whenever the classification is ambiguous. This is a
deliberate design decision already made in the spec (Rules & Constraints:
"a change touching both classes is treated as a schema change"), not a
default this module chose on its own, and it is not this module's to
relitigate. The same "heavier path wins" reasoning extends to one case the
spec does not name explicitly: a changed path that matches *neither*
declared class in `change_classes.yaml` also routes to `schema`. That is a
choice this module does make (documented on `classify_change` itself) --
fail closed, since an unrecognized path is precisely the case the
declaration has not yet made a safety claim about.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Union

import yaml

ChangeClass = Literal["content", "schema"]

# change_classes.yaml, resolved relative to the repo root so it works regardless
# of the caller's working directory (same pattern as models.SCHEMA_PATH /
# glossary.GLOSSARY_PATH).
DEFAULT_CHANGE_CLASSES_PATH = Path(__file__).resolve().parents[2] / "change_classes.yaml"


@dataclass(frozen=True)
class _ChangeClassGlobs:
    """`change_classes.yaml`'s three glob lists, compiled once."""

    content: List[re.Pattern]
    content_exclude: List[re.Pattern]
    schema: List[re.Pattern]


def classify_change(
    changed_paths: List[str],
    change_classes_path: Optional[Union[str, Path]] = None,
) -> ChangeClass:
    """Classify one change request's changed file paths as `"content"` (fast
    path) or `"schema"` (slow path), per `change_classes.yaml`.

    Precondition: `changed_paths` is a non-empty list of repo-root-relative,
    forward-slash-separated paths -- what `git diff --name-only` reports.
    `change_classes_path` defaults to the checked-in `change_classes.yaml` at
    the repository root; a caller may point at another file (e.g. a fixture
    in a test).

    Postcondition: returns `"content"` if and only if every changed path
    matches `change_classes.yaml`'s `content` glob set and none matches
    `schema` or `content_exclude`. Returns `"schema"` in every other case:
    any path matching `schema` or `content_exclude`, any path matching
    neither declared class, or a mix of `content` and `schema` paths in the
    same call -- the heavier path always wins when the classification is
    anything other than unanimous `content` (see this module's docstring for
    why that is a deliberate, already-settled policy, not a default chosen
    here).
    """
    if not changed_paths:
        raise ValueError("changed_paths must be a non-empty list of changed file paths")

    globs = _load_change_classes(change_classes_path)
    classifications = {_classify_path(path, globs) for path in changed_paths}
    return "content" if classifications == {"content"} else "schema"


def _load_change_classes(change_classes_path: Optional[Union[str, Path]]) -> _ChangeClassGlobs:
    resolved_path = Path(change_classes_path) if change_classes_path is not None else DEFAULT_CHANGE_CLASSES_PATH
    raw = yaml.safe_load(resolved_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{resolved_path}: expected a YAML mapping at the document root")
    return _ChangeClassGlobs(
        content=_compile_globs(raw.get("content", [])),
        content_exclude=_compile_globs(raw.get("content_exclude", [])),
        schema=_compile_globs(raw.get("schema", [])),
    )


def _classify_path(path: str, globs: _ChangeClassGlobs) -> ChangeClass:
    """One path's own classification, before the "any schema path forces the
    whole change to schema" rule is applied across the full changed-paths list.
    `content_exclude` is checked ahead of `content` so a path carved out of the
    content glob set (e.g. `contracts/_schema/...`) never classifies as content
    even if `change_classes.yaml`'s `schema` list were ever to fall out of sync
    with it.

    Normalizes `path` (collapsing `..`/`.` segments, `posixpath`-style, since
    `changed_paths` is documented as forward-slash-separated) before matching
    against any glob -- `_glob_to_regex` matches the literal string, so a `..`
    component left un-normalized could textually satisfy a `content` glob while
    also textually containing a schema-owned path segment (a real gap, not a
    theoretical one; see this module's adversarial test coverage). A path whose
    normalized form still starts with `../` (i.e. it claims to reach outside the
    repository root `changed_paths` is documented to be relative to) is treated
    as unrecognized/out-of-policy and fails closed to `schema`, the same policy
    this function already applies to a path matching neither declared class.
    """
    normalized = posixpath.normpath(path)
    if normalized == ".." or normalized.startswith("../"):
        return "schema"  # claims to escape the repo root: fail closed
    if any(pattern.match(normalized) for pattern in globs.content_exclude):
        return "schema"
    if any(pattern.match(normalized) for pattern in globs.schema):
        return "schema"
    if any(pattern.match(normalized) for pattern in globs.content):
        return "content"
    return "schema"  # matches neither declared class: fail closed


def _compile_globs(patterns: List[str]) -> List[re.Pattern]:
    return [_glob_to_regex(pattern) for pattern in patterns]


def _glob_to_regex(pattern: str) -> re.Pattern:
    """Translate one glob pattern to an anchored regex, supporting `**` (match
    any sequence of characters, including `/`, so it spans directories) and `*`
    (match any sequence of characters except `/`, so it stays within one path
    segment) -- the two wildcard forms `change_classes.yaml` actually uses.
    `pathlib.PurePath.match` was deliberately not used here: on the Python
    versions this project supports (>=3.11), it treats `**` as an ordinary
    single-segment wildcard rather than a recursive one, which would silently
    fail to match `contracts/*.yaml`-shaped flat filenames against a
    `contracts/**/*.yaml`-shaped pattern.
    """
    regex_parts = ["^"]
    i, length = 0, len(pattern)
    while i < length:
        char = pattern[i]
        if char == "*" and pattern[i : i + 2] == "**":
            regex_parts.append(".*")
            i += 2
            if i < length and pattern[i] == "/":
                i += 1  # "**/" also matches zero directories, not just one-or-more
        elif char == "*":
            regex_parts.append("[^/]*")
            i += 1
        elif char == "?":
            regex_parts.append("[^/]")
            i += 1
        else:
            regex_parts.append(re.escape(char))
            i += 1
    regex_parts.append("$")
    return re.compile("".join(regex_parts))
