"""Happy-path tests for `change_routing.py`'s mechanical fast-path/slow-path
classification (ADR-006).

Adversarial and boundary cases (a malformed `change_classes.yaml`, an empty
pattern list, a path containing `..`, etc.) belong to the adversary persona,
not here. These tests confirm the classifier does what ADR-006 says it should:
an all-content change routes fast, any schema-touching path routes slow, a
change touching both classes in one call routes slow, and an unrecognized path
fails closed to the slow path.

No spec scenario ID names this behaviour directly (ADR-006/Rules & Constraints
are the source, not a Scenario), so these tests carry no `@pytest.mark.scenario`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from uc_metadata.change_routing import classify_change

REPO_CHANGE_CLASSES_PATH = Path(__file__).resolve().parents[2] / "change_classes.yaml"


def test_content_only_paths_classify_as_content():
    """Editing one or more contracts, and nothing else, is the fast path."""
    changed_paths = [
        "contracts/workspace.sales.orders.yaml",
        "contracts/workspace.analytics.customers.yaml",
    ]

    assert classify_change(changed_paths, REPO_CHANGE_CLASSES_PATH) == "content"


def test_schema_touching_paths_classify_as_schema():
    """Editing the contract model itself is the slow path."""
    changed_paths = ["src/uc_metadata/models.py"]

    assert classify_change(changed_paths, REPO_CHANGE_CLASSES_PATH) == "schema"


def test_contract_schema_json_and_template_classify_as_schema():
    """The JSON Schema and the starter template live under `contracts/`, but are
    platform-owned shape, not team-owned content -- carved out of the content
    glob and routed to schema."""
    assert classify_change(["contracts/_schema/contract.schema.json"], REPO_CHANGE_CLASSES_PATH) == "schema"
    assert classify_change(["contracts/_template.yaml"], REPO_CHANGE_CLASSES_PATH) == "schema"


def test_change_touching_both_classes_classifies_as_schema():
    """One change request editing a contract *and* the model together is the
    slow path -- the heavier path wins when the classification is ambiguous
    (Rules & Constraints: "a change touching both classes is treated as a
    schema change")."""
    changed_paths = [
        "contracts/workspace.sales.orders.yaml",
        "src/uc_metadata/models.py",
    ]

    assert classify_change(changed_paths, REPO_CHANGE_CLASSES_PATH) == "schema"


def test_unrecognized_path_fails_closed_to_schema():
    """A path matching neither declared class (e.g. a change under `dashboard/`)
    is not silently treated as safe content -- it routes to the slow, reviewed
    path, since `change_classes.yaml` has made no safety claim about it at all."""
    assert classify_change(["dashboard/app.py"], REPO_CHANGE_CLASSES_PATH) == "schema"


def test_change_classes_yaml_itself_classifies_as_schema():
    """The routing declaration is itself a schema/tooling artifact: changing it
    changes which path every other change gets routed through."""
    assert classify_change(["change_classes.yaml"], REPO_CHANGE_CLASSES_PATH) == "schema"


def test_classify_change_rejects_an_empty_path_list():
    """Precondition: there must be at least one changed path to classify."""
    with pytest.raises(ValueError):
        classify_change([], REPO_CHANGE_CLASSES_PATH)


def test_classify_change_defaults_to_the_repo_root_change_classes_yaml():
    """Calling without `change_classes_path` reads the checked-in file, not a
    fixture -- proves the default resolves to a real, loadable file."""
    assert classify_change(["contracts/workspace.sales.orders.yaml"]) == "content"
