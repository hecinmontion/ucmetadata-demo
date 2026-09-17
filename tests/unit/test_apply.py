"""Happy-path tests for `apply.py`: planning is pure, a fully-reviewed contract
applies and is idempotent and reversible, an unreviewed/placeholder contract is
refused whole, a mid-apply failure is reported as a named partial failure, and
the release log round-trips what `apply()` published.

Adversarial and boundary cases (a table that vanishes mid-apply, a malformed
release-log line, concurrent applies) belong to the adversary persona, not
here -- see `test_validate.py`'s module docstring for the same scoping note.

Runs against `fake_uc.FakeUCClient`'s default fixture (no network); a separate
`uc_live` smoke test at the bottom exercises the real path once, end to end.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from uc_metadata.apply import ApplyResult, apply, plan_apply
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.harvest import harvest
from uc_metadata.models import CertificationTier, Contract, Proposed, Refresh, Sensitivity
from uc_metadata.release_log import DeploymentStatus, ReleaseRecord, publish_release_record, read_release_log
from uc_metadata.uc_client import RealUCClient, UCClient, UCWriteError

TABLE = "workspace.analytics.customers"
KNOWN_BA_ID = "BA-10231"
APPROVER = "hector"
UC_LIVE_TESTS_ENABLED = os.environ.get("UC_LIVE_TESTS") == "1"


def _fully_reviewed_contract(client: UCClient, full_name: str = TABLE) -> Contract:
    """A harvested-then-fully-reviewed contract for `full_name`: every
    human-declared dataset field carries a real value, every judgment field is
    an accepted (`ai_proposed=False`) `Proposed` value, and one column
    (`customer_id`) carries a free-form tag -- exercising the `List[str]` ->
    `Mapping[str, str]` tag translation this phase adds. Mirrors
    `test_validate.py`'s helper of the same name and purpose."""
    contract = harvest(
        full_name,
        client,
        KNOWN_BA_ID,
        description="Customer master records for the direct-to-consumer storefront.",
        refresh=Refresh(cadence="daily", sla_minutes=120),
        retention_days=730,
        certification=CertificationTier.SILVER,
    )
    reviewed_columns = [
        column.model_copy(
            update={
                "description": Proposed.accepted(f"{column.name} column."),
                "pii": Proposed.accepted(False),
                "sensitivity": Proposed.accepted(Sensitivity.INTERNAL),
                "tags": ["primary_key"] if column.name == "customer_id" else [],
            }
        )
        for column in contract.columns
    ]
    dataset = contract.dataset.model_copy(update={"sensitivity": Proposed.accepted(Sensitivity.INTERNAL)})
    return contract.model_copy(update={"dataset": dataset, "columns": reviewed_columns})


class _FailOnColumnComment(FakeUCClient):
    """A `FakeUCClient` that fails one specific real (non-dry-run) column
    comment write, so `apply()`'s partial-failure path can be exercised without
    a live network. Planning (`dry_run=True`) is untouched, since a plan must
    still be able to name the write that will fail."""

    def __init__(self, *, fail_column: str) -> None:
        super().__init__()
        self._fail_column = fail_column

    def set_column_comment(self, full_name: str, column_name: str, comment: str, *, dry_run: bool = False) -> str:
        if not dry_run and column_name == self._fail_column:
            raise UCWriteError(f"synthetic contract-test failure writing {column_name}'s comment")
        return super().set_column_comment(full_name, column_name, comment, dry_run=dry_run)


# ---- plan_apply: pure, no side effects -------------------------------------------


def test_plan_apply_lists_the_expected_writes_with_no_side_effects():
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    before = client.get_table(TABLE)

    plan = plan_apply(contract, client)

    assert plan[0].startswith("COMMENT ON TABLE")
    column_comment_lines = [line for line in plan if "COMMENT ON COLUMN" in line]
    assert len(column_comment_lines) == len(contract.columns)
    assert any("SET TBLPROPERTIES" in line for line in plan)
    assert any("SET TAGS" in line and "ALTER COLUMN" not in line for line in plan)  # table tags
    assert any("ALTER COLUMN" in line and "SET TAGS" in line for line in plan)  # column tags
    # customer_id's free-form tag translates to a key-only/empty-value tag.
    assert any("`customer_id`" in line and "'primary_key' = ''" in line for line in plan)

    after = client.get_table(TABLE)
    assert after == before  # planning touched nothing


# ---- refusal (SC-001-03): defence in depth, apply() validates itself -------------


@pytest.mark.scenario("SC-001-03")
def test_apply_refuses_contract_with_unreviewed_field(tmp_path: Path):
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    unreviewed_columns = [
        column.model_copy(update={"sensitivity": Proposed.proposed(Sensitivity.CONFIDENTIAL)})
        if column.name == "email"
        else column
        for column in contract.columns
    ]
    contract = contract.model_copy(update={"columns": unreviewed_columns})
    log_path = tmp_path / "release_log.jsonl"
    before = client.get_table(TABLE)

    result = apply(contract, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.REFUSED
    assert result.writes_succeeded == []
    assert result.writes_failed == []
    assert any("unreviewed" in problem for problem in result.problems)
    assert client.get_table(TABLE) == before  # nothing written

    records = read_release_log(log_path)
    assert len(records) == 1
    assert records[0].deployment_status == DeploymentStatus.REFUSED
    assert [r for r in records if r.deployment_status == DeploymentStatus.SUCCESS] == []


@pytest.mark.scenario("SC-001-03")
def test_apply_refuses_contract_with_placeholder_sentinel(tmp_path: Path):
    client = FakeUCClient()
    contract = harvest(TABLE, client, KNOWN_BA_ID)  # skeleton: all four dataset placeholders still present
    log_path = tmp_path / "release_log.jsonl"
    before = client.get_table(TABLE)

    result = apply(contract, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.REFUSED
    assert result.writes_succeeded == []
    assert result.writes_failed == []
    assert any("placeholder" in problem for problem in result.problems)
    assert client.get_table(TABLE) == before  # nothing written

    records = read_release_log(log_path)
    assert len(records) == 1
    assert records[0].deployment_status == DeploymentStatus.REFUSED
    assert [r for r in records if r.deployment_status == DeploymentStatus.SUCCESS] == []


# ---- happy path (SC-001-01): apply writes everything, refuses nothing later -----


@pytest.mark.scenario("SC-001-01")
def test_apply_writes_every_planned_statement_and_logs_success(tmp_path: Path):
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    log_path = tmp_path / "release_log.jsonl"
    plan = plan_apply(contract, client)

    result = apply(contract, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.SUCCESS
    assert result.ok is True
    assert result.writes_failed == []
    assert [attempt.sql for attempt in result.writes_succeeded] == plan  # same SQL plan and apply agreed on

    table = client.get_table(TABLE)
    assert table.comment == contract.dataset.description
    email = next(c for c in table.columns if c.name == "email")
    assert email.comment == "email column."
    assert table.tags["sensitivity"] == "internal"
    assert table.properties["uc_metadata.certification"] == "silver"

    records = read_release_log(log_path)
    assert len(records) == 1
    assert records[0].deployment_status == DeploymentStatus.SUCCESS
    assert records[0].approved_by == APPROVER
    assert records[0].full_name == TABLE


# ---- idempotency ------------------------------------------------------------------


def test_apply_twice_on_an_unchanged_contract_produces_no_further_change(tmp_path: Path):
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    log_path = tmp_path / "release_log.jsonl"

    first = apply(contract, client, approved_by=APPROVER, log_path=log_path)
    state_after_first = client.get_table(TABLE)

    second = apply(contract, client, approved_by=APPROVER, log_path=log_path)
    state_after_second = client.get_table(TABLE)

    assert first.status == DeploymentStatus.SUCCESS
    assert second.status == DeploymentStatus.SUCCESS
    assert state_after_second == state_after_first  # identical end state, not just "didn't error"
    assert len(read_release_log(log_path)) == 2  # both attempts are on the record, even though inert


# ---- reversibility: apply is a pure function of contract -> desired state -------


def test_apply_is_a_pure_function_of_contract_not_incrementally_stateful(tmp_path: Path):
    client_a_then_a_prime = FakeUCClient()
    contract_a = _fully_reviewed_contract(client_a_then_a_prime)
    apply(contract_a, client_a_then_a_prime, approved_by=APPROVER, log_path=tmp_path / "log_a.jsonl")

    edited_columns = [
        column.model_copy(update={"description": Proposed.accepted("The customer's edited description.")})
        if column.name == "email"
        else column
        for column in contract_a.columns
    ]
    contract_a_prime = contract_a.model_copy(
        update={
            "dataset": contract_a.dataset.model_copy(update={"description": "Edited dataset description."}),
            "columns": edited_columns,
        }
    )
    apply(contract_a_prime, client_a_then_a_prime, approved_by=APPROVER, log_path=tmp_path / "log_a.jsonl")

    client_a_prime_fresh = FakeUCClient()
    apply(contract_a_prime, client_a_prime_fresh, approved_by=APPROVER, log_path=tmp_path / "log_fresh.jsonl")

    assert client_a_then_a_prime.get_table(TABLE) == client_a_prime_fresh.get_table(TABLE)


# ---- partial failure: named, not opaque -------------------------------------------


def test_apply_names_exactly_which_writes_succeeded_and_which_failed(tmp_path: Path):
    client = _FailOnColumnComment(fail_column="email")
    contract = _fully_reviewed_contract(client)
    log_path = tmp_path / "release_log.jsonl"

    result = apply(contract, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.PARTIAL_FAILURE
    assert result.ok is False
    failed_labels = {attempt.label for attempt in result.writes_failed}
    assert failed_labels == {"column comment: email"}
    assert "synthetic contract-test failure" in result.writes_failed[0].error
    succeeded_labels = {attempt.label for attempt in result.writes_succeeded}
    assert "table comment" in succeeded_labels
    assert "column comment: customer_id" in succeeded_labels  # other writes still landed

    records = read_release_log(log_path)
    assert len(records) == 1
    assert records[0].deployment_status == DeploymentStatus.PARTIAL_FAILURE
    assert any(entry.startswith("column comment: email:") for entry in records[0].writes_failed)
    assert "table comment" in records[0].writes_succeeded


# ---- release log round-trip --------------------------------------------------------


def test_publish_and_read_release_log_round_trips_append_only(tmp_path: Path):
    log_path = tmp_path / "release_log.jsonl"
    first = ReleaseRecord.now(
        full_name=TABLE,
        contract_version=1,
        summary="applied 5 write(s)",
        approved_by="alice",
        deployment_status=DeploymentStatus.SUCCESS,
        writes_succeeded=["table comment"],
    )
    second = ReleaseRecord.now(
        full_name="workspace.marketing.campaigns",
        contract_version=1,
        summary="refused: 1 validation problem(s), no writes attempted",
        approved_by="bob",
        deployment_status=DeploymentStatus.REFUSED,
        problems=["unreviewed: dataset.sensitivity is still AI-proposed"],
    )

    publish_release_record(first, log_path=log_path)
    publish_release_record(second, log_path=log_path)

    records = read_release_log(log_path)
    assert len(records) == 2
    assert records[0].approved_by == "alice"
    assert records[0].deployment_status == DeploymentStatus.SUCCESS
    assert records[1].approved_by == "bob"
    assert records[1].deployment_status == DeploymentStatus.REFUSED
    assert records[1].problems == ["unreviewed: dataset.sensitivity is still AI-proposed"]


def test_read_release_log_returns_empty_list_when_no_log_exists_yet(tmp_path: Path):
    assert read_release_log(tmp_path / "does_not_exist.jsonl") == []


# ---- tag translation convention: List[str] -> Mapping[str, str] round-trips -----


def test_column_free_form_tags_translate_to_key_only_empty_value_tags(tmp_path: Path):
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)  # customer_id carries tags=["primary_key"]

    apply(contract, client, approved_by=APPROVER, log_path=tmp_path / "release_log.jsonl")

    customer_id = next(c for c in client.get_table(TABLE).columns if c.name == "customer_id")
    assert customer_id.tags["primary_key"] == ""  # key-only/flag convention, not a synthesized value
    # Governance classifications land as real key/value tags alongside it.
    assert customer_id.tags["pii"] == "false"
    assert customer_id.tags["sensitivity"] == "internal"


# ---- live smoke test: the real path, once, end to end ----------------------------


@pytest.mark.uc_live
@pytest.mark.skipif(
    not UC_LIVE_TESTS_ENABLED,
    reason="set UC_LIVE_TESTS=1 to run this against the live Free Edition workspace",
)
def test_apply_against_the_live_workspace_lands_and_is_idempotent(tmp_path: Path):
    """Apply a real, fully-reviewed contract against the live Free Edition
    workspace, confirm the writes landed via a fresh `get_table`, apply again
    and confirm idempotency for real, and confirm a real release-log entry was
    written -- the same three claims the fake-backed tests above make, proven
    here against `RealUCClient` rather than assumed to transfer."""
    client = RealUCClient()
    contract = _fully_reviewed_contract(client)
    log_path = tmp_path / "live_release_log.jsonl"

    first = apply(contract, client, approved_by=APPROVER, log_path=log_path)
    assert first.status == DeploymentStatus.SUCCESS

    landed = RealUCClient().get_table(TABLE)
    assert landed.comment == contract.dataset.description
    email = next(c for c in landed.columns if c.name == "email")
    assert email.comment == "email column."
    assert landed.tags.get("sensitivity") == "internal"
    assert landed.properties.get("uc_metadata.certification") == "silver"

    second = apply(contract, client, approved_by=APPROVER, log_path=log_path)
    assert second.status == DeploymentStatus.SUCCESS
    landed_again = RealUCClient().get_table(TABLE)
    assert landed_again.comment == landed.comment
    assert landed_again.properties == landed.properties

    records = read_release_log(log_path)
    assert len(records) == 2
    assert all(r.deployment_status == DeploymentStatus.SUCCESS for r in records)
