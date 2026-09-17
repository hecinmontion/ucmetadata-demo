"""Happy-path syntactic-validity checks for the GitHub Actions workflow YAML
files under `.github/workflows/`.

This is deliberately narrow: it confirms each workflow file parses as YAML
and has the handful of top-level keys a GitHub Actions workflow must have
(`on`, `jobs`), and spot-checks the one design decision every workflow states
in its own header comment -- none of them passes `--live` to `ucmeta`, so none
of them can accidentally depend on a real Databricks credential. It cannot
confirm the workflow *runs* correctly on GitHub Actions; that needs a real
push to a real GitHub remote, which is a separate, human-coordinated step
(see each workflow's own header comment for the credential-free reasoning).

No spec scenario ID names workflow-YAML validity directly (the Dependencies ->
Build verdicts table is the source, not a Scenario), so these tests carry no
`@pytest.mark.scenario`, matching `test_change_routing.py`'s precedent for
ADR-derived, non-scenario-bound behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_WORKFLOW_FILES = ["validate.yml", "apply.yml", "coverage.yml"]


@pytest.mark.parametrize("filename", _WORKFLOW_FILES)
def test_workflow_file_is_valid_yaml_with_required_top_level_keys(filename):
    """Each workflow file parses as YAML and declares `on` and `jobs` -- the
    two top-level keys every GitHub Actions workflow requires."""
    contents = (_WORKFLOWS_DIR / filename).read_text()

    document = yaml.safe_load(contents)

    assert isinstance(document, dict)
    # PyYAML parses the unquoted `on:` key as the boolean `True`, not the
    # string `"on"` -- a well-known YAML 1.1 gotcha, not a bug in this test.
    assert True in document or "on" in document
    assert "jobs" in document and document["jobs"]


@pytest.mark.parametrize("filename", _WORKFLOW_FILES)
def test_workflow_never_passes_live_to_ucmeta(filename):
    """Every `ucmeta` invocation in these workflows omits `--live`, so none of
    them can depend on a real Databricks credential -- the credential-free
    design decision each workflow's header comment states. Each file's own
    header comment names `--live` in prose (explaining why it is *not* used),
    so this checks non-comment lines only, not the file as a whole."""
    lines = (_WORKFLOWS_DIR / filename).read_text().splitlines()
    code_lines = [line for line in lines if not line.strip().startswith("#")]

    assert not any("--live" in line for line in code_lines)


def test_validate_workflow_routes_through_change_classify():
    """`validate.yml` calls `change_routing.classify_change`, which is what
    turns ADR-006's two-track model from an assertion into an enforced check
    (Dependencies -> Build verdicts: "a workflow step reads the changed paths
    ... and selects the path")."""
    contents = (_WORKFLOWS_DIR / "validate.yml").read_text()

    assert "classify_change" in contents


def test_apply_workflow_triggers_on_push_to_main():
    """Apply runs only on merge to main (Rules & Constraints), never on a
    pull request."""
    document = yaml.safe_load((_WORKFLOWS_DIR / "apply.yml").read_text())

    on_section = document.get("on", document.get(True))
    assert "push" in on_section
    assert on_section["push"]["branches"] == ["main"]


def test_coverage_workflow_is_scheduled():
    """Coverage recomputes on a schedule, not only on demand (Dependencies ->
    Build verdicts: "proves coverage is a running process rather than a
    one-off screenshot")."""
    document = yaml.safe_load((_WORKFLOWS_DIR / "coverage.yml").read_text())

    on_section = document.get("on", document.get(True))
    assert "schedule" in on_section
    assert "workflow_dispatch" in on_section
