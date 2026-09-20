"""Happy-path syntactic-validity checks for the GitHub Actions workflow YAML
files under `.github/workflows/`.

This is deliberately narrow: it confirms each workflow file parses as YAML
and has the handful of top-level keys a GitHub Actions workflow must have
(`on`, `jobs`), and spot-checks each workflow's own credential-free-or-not
design decision. `validate.yml` and `coverage.yml` never pass `--live` at
all, so neither can accidentally depend on a real Databricks credential.
`apply.yml` is different as of F-PLATFORM-003 / ADR-009 (Layer 1): it *does*
apply live, as the `ucmeta-ci-apply` service principal, but only when a CI
apply credential is actually configured -- SC-003-04 requires the live path
to be conditional on that credential and fork-safe otherwise, and Rules &
Constraints requires that no step ever echoes a secret's value. Those two
properties, not "never passes --live", are what the `apply.yml`-specific
tests below check for that file now. It cannot confirm any workflow *runs*
correctly on GitHub Actions; that needs a real push to a real GitHub remote,
which is a separate, human-coordinated step (see each workflow's own header
comment for its credential reasoning).

`provision-catalog.yml` used to be credential-free by construction rather
than by a conditional branch, because F-PLATFORM-004 shipped it with no live
path at all. F-PLATFORM-005 gives it exactly the same conditional shape
`apply.yml` already has, as a second, disjoint identity
(`ucmeta-ci-provision`, not `ucmeta-ci-apply`) -- SC-005-03 requires the same
credential-gate and fork-safety properties SC-003-04 requires of `apply.yml`,
and the three former no-live-path assertions this module used to carry for
this file are narrowed below into the conditional-gate and
no-secret-echoed assertions, the same move F-PLATFORM-003 made for
`apply.yml` when its own no-`--live` assertion first stopped being true.

No spec scenario ID names workflow-YAML validity directly for `validate.yml`/
`coverage.yml` (the Dependencies -> Build verdicts table is the source, not a
Scenario), so those tests carry no `@pytest.mark.scenario`, matching
`test_change_routing.py`'s precedent for ADR-derived, non-scenario-bound
behaviour. The `apply.yml` fork-safety tests below bind to SC-003-04
explicitly, since that scenario is exactly what they check; the
`provision-catalog.yml` tests bind to SC-005-02/SC-005-03 for the same
reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_WORKFLOW_FILES = ["validate.yml", "apply.yml", "coverage.yml", "provision-catalog.yml"]


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


_CREDENTIAL_FREE_WORKFLOW_FILES = ["validate.yml", "coverage.yml"]


@pytest.mark.parametrize("filename", _CREDENTIAL_FREE_WORKFLOW_FILES)
def test_workflow_never_passes_live_to_ucmeta(filename):
    """Every `ucmeta` invocation in these workflows omits `--live`, so neither
    can depend on a real Databricks credential -- the credential-free design
    decision each workflow's header comment states. `apply.yml` and
    `provision-catalog.yml` are both deliberately excluded from this
    assertion: `apply.yml` since F-PLATFORM-003 / ADR-009 (Layer 1), and
    `provision-catalog.yml` since F-PLATFORM-005 (ADR-011), each passes
    `--live` conditionally, as its own credential-gated service principal --
    see the tests specific to each file below for what replaces this
    property. Each remaining file's own header comment names `--live` in
    prose (explaining why it is *not* used), so this checks non-comment
    lines only, not the file as a whole."""
    lines = (_WORKFLOWS_DIR / filename).read_text().splitlines()
    code_lines = [line for line in lines if not line.strip().startswith("#")]

    assert not any("--live" in line for line in code_lines)


def test_apply_workflow_live_path_is_conditional_on_credential_sc_003_04():
    """SC-003-04: a fork or clone with no CI apply credential configured must
    not attempt a live apply -- the live-apply step must be gated by an `if:`
    condition derived from whether the credential secrets are present, not
    run unconditionally."""
    document = yaml.safe_load((_WORKFLOWS_DIR / "apply.yml").read_text())
    steps = document["jobs"]["apply"]["steps"]

    live_steps = [s for s in steps if "--live" in s.get("run", "")]
    assert live_steps, "expected at least one step in apply.yml to pass --live"
    for step in live_steps:
        condition = step.get("if", "")
        assert "credential" in condition and "configured" in condition, (
            f"live step {step['name']!r} must be gated on the credential-configured "
            "check, not run unconditionally"
        )


def test_apply_workflow_has_fake_fallback_when_no_credential_sc_003_04():
    """SC-003-04: when no CI apply credential is configured, apply.yml must
    still run the apply-on-merge mechanism against the in-repository fake,
    rather than simply skipping the job -- the fallback step must exist and
    be gated on the credential check finding nothing configured."""
    document = yaml.safe_load((_WORKFLOWS_DIR / "apply.yml").read_text())
    steps = document["jobs"]["apply"]["steps"]

    fallback_steps = [
        s
        for s in steps
        if "--live" not in s.get("run", "")
        and "credential" in s.get("if", "")
        and "configured" in s.get("if", "")
    ]
    assert fallback_steps, "expected a fake-catalogue fallback step gated on the credential check"


def test_apply_workflow_never_echoes_a_secret_value_sc_003_04():
    """Rules & Constraints: credentials never enter a job's printed output.
    No `run:` block may interpolate a `secrets.*` GitHub Actions expression
    directly into an `echo`/print -- secrets must only ever be consumed via
    `env:`, and only ever compared or written to a file, never echoed."""
    contents = (_WORKFLOWS_DIR / "apply.yml").read_text()
    lines = contents.splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "echo" in stripped and "secrets." in stripped:
            pytest.fail(f"a line echoes what looks like a secret value directly: {line!r}")


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


# ---- provision-catalog.yml (F-PLATFORM-005): a credential-gated live path -------
#
# F-PLATFORM-004's three no-live-path assertions ("never passes --live",
# "states plainly it has no live path") became false the moment
# F-PLATFORM-005 gave this workflow a live branch, and Rules & Constraints is
# explicit that they must be *narrowed*, not deleted -- exactly the move
# F-PLATFORM-003 made when `apply.yml`'s own no-`--live` assertion first
# stopped being true. The three tests below are that narrowing: they mirror
# `test_apply_workflow_live_path_is_conditional_on_credential_sc_003_04`,
# `test_apply_workflow_has_fake_fallback_when_no_credential_sc_003_04` and
# `test_apply_workflow_never_echoes_a_secret_value_sc_003_04` line for line,
# against `ucmeta-ci-provision`'s credential names instead of
# `ucmeta-ci-apply`'s.


@pytest.mark.scenario("SC-005-01")
def test_provision_catalog_workflow_triggers_on_push_to_main():
    """Same trigger shape apply.yml uses: a push to main, not a pull request
    (F-PLATFORM-004 Rules & Constraints, inherited unchanged: "the trigger is
    a push to the main branch whose changed paths include a request file")."""
    document = yaml.safe_load((_WORKFLOWS_DIR / "provision-catalog.yml").read_text())

    on_section = document.get("on", document.get(True))
    assert "push" in on_section
    assert on_section["push"]["branches"] == ["main"]


@pytest.mark.scenario("SC-005-01")
def test_provision_catalog_workflow_excludes_its_own_template():
    """`catalog-requests/_template.yaml` is a platform artifact, not an
    authored request, and must never be processed as one -- the same
    carve-out apply.yml/validate.yml already apply to the contracts
    template, inherited unchanged from F-PLATFORM-004."""
    contents = (_WORKFLOWS_DIR / "provision-catalog.yml").read_text()

    assert "catalog-requests/_template" in contents


@pytest.mark.scenario("SC-005-03")
def test_provision_catalog_workflow_live_path_is_conditional_on_credential_sc_005_03():
    """SC-005-03: a fork or clone with no CI provision credential configured
    must not attempt a live provisioning -- the live step must be gated by an
    `if:` condition derived from whether the credential secrets are present,
    not run unconditionally."""
    document = yaml.safe_load((_WORKFLOWS_DIR / "provision-catalog.yml").read_text())
    steps = document["jobs"]["provision-catalog"]["steps"]

    live_steps = [s for s in steps if "--live" in s.get("run", "")]
    assert live_steps, "expected at least one step in provision-catalog.yml to pass --live"
    for step in live_steps:
        condition = step.get("if", "")
        assert "credential" in condition and "configured" in condition, (
            f"live step {step['name']!r} must be gated on the credential-configured "
            "check, not run unconditionally"
        )


@pytest.mark.scenario("SC-005-03")
def test_provision_catalog_workflow_has_fake_fallback_when_no_credential_sc_005_03():
    """SC-005-03: when no CI provision credential is configured, the
    provisioning-on-merge mechanism must still run against the
    in-repository fake, rather than simply skipping the job -- the fallback
    step must exist and be gated on the credential check finding nothing
    configured."""
    document = yaml.safe_load((_WORKFLOWS_DIR / "provision-catalog.yml").read_text())
    steps = document["jobs"]["provision-catalog"]["steps"]

    fallback_steps = [
        s
        for s in steps
        if "--live" not in s.get("run", "")
        and "credential" in s.get("if", "")
        and "configured" in s.get("if", "")
    ]
    assert fallback_steps, "expected a fake-catalogue fallback step gated on the credential check"


@pytest.mark.scenario("SC-005-03")
def test_provision_catalog_workflow_never_echoes_a_secret_value_sc_005_03():
    """Rules & Constraints: credentials never enter a job's printed output.
    No `run:` block may interpolate a `secrets.*` GitHub Actions expression
    directly into an `echo`/print -- secrets must only ever be consumed via
    `env:`, and only ever compared or written to a file, never echoed."""
    contents = (_WORKFLOWS_DIR / "provision-catalog.yml").read_text()
    lines = contents.splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "echo" in stripped and "secrets." in stripped:
            pytest.fail(f"a line echoes what looks like a secret value directly: {line!r}")
