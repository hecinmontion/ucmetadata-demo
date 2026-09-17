"""Loads the sample business glossary (`glossary/terms.yaml`) so `propose.py` (a
later phase) can retrieve relevant terms and pass them as context to the AI
drafter -- the RAG-lite retrieval the spec's `glossary/` build verdict describes.

Stands in for a real glossary system owned by the data office (Glossary: Business
term); Out of Scope names glossary curation itself as assumed to exist elsewhere.
The one thing a caller needs from this module is `load_glossary()`; where the file
lives and how it's parsed is this module's business, not the caller's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

import yaml

# glossary/terms.yaml, resolved relative to the repo root so it works regardless
# of the caller's working directory (same pattern as models.SCHEMA_PATH).
GLOSSARY_PATH = Path(__file__).resolve().parents[2] / "glossary" / "terms.yaml"


def load_glossary(path: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """Load the glossary as a `{term_slug: definition}` mapping.

    Precondition: `path` (or the default `glossary/terms.yaml`) is a YAML file
    containing a flat mapping of non-empty string keys to non-empty string
    definitions. Postcondition: returns a non-empty dict; raises `ValueError` if
    the file is missing that shape -- a caller passing this straight to an AI
    prompt as retrieval context should never silently get an empty or malformed
    glossary instead of a loud failure.
    """
    resolved_path = Path(path) if path is not None else GLOSSARY_PATH
    raw = yaml.safe_load(resolved_path.read_text())
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"{resolved_path}: expected a non-empty YAML mapping of term -> definition")
    for term, definition in raw.items():
        if not isinstance(term, str) or not term:
            raise ValueError(f"{resolved_path}: glossary term keys must be non-empty strings, got {term!r}")
        if not isinstance(definition, str) or not definition.strip():
            raise ValueError(f"{resolved_path}: glossary term {term!r} must have a non-empty string definition")
    return raw
