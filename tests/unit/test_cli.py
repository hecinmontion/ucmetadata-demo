"""Happy-path tests for `cli.py`: the five verbs wired together, exercised both
as a real subprocess (proving `./cli/ucmeta` genuinely runs, not just that the
Python functions compose) and at the function level (`cli.main(argv=[...])`,
faster, for the rest of the coverage).

Adversarial and boundary cases (a table that vanishes mid-command, a
`--cadence` without `--sla-minutes`, a corrupt release log, concurrent
applies) belong to the adversary persona, not here -- see `test_validate.py`'s
module docstring for the same scoping note this codebase already uses.

Runs entirely against `fake_uc.FakeUCClient`'s default fixture (no network,
no `ANTHROPIC_API_KEY` needed): `propose` is exercised via `main`'s
`llm_client=` injection seam and `llm_fixture_transport`'s replay mechanism,
the same offline path `test_propose.py` uses.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from llm_fixture_transport import build_llm_client
from uc_metadata import cli
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.harvest import harvest
from uc_metadata.models import CertificationTier, Contract, Proposed, Refresh, Sensitivity
from uc_metadata.release_log import DeploymentStatus, read_release_log

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPO_ROOT / "cli" / "ucmeta"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

TABLE = "workspace.analytics.customers"
KNOWN_BA_ID = "BA-10231"
APPROVER = "hector"
CUSTOMERS_FIXTURE = "customers_propose__PLACEHOLDER_NOT_RECORDED"


def _fully_reviewed_contract(client, full_name: str = TABLE) -> Contract:
    """A harvested-then-fully-reviewed contract for `full_name`: every
    human-declared dataset field carries a real value, every judgment field is
    an accepted (`ai_proposed=False`) `Proposed` value. Mirrors
    `test_apply.py`/`test_validate.py`'s helper of the same name and purpose."""
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
            }
        )
        for column in contract.columns
    ]
    dataset = contract.dataset.model_copy(update={"sensitivity": Proposed.accepted(Sensitivity.INTERNAL)})
    return contract.model_copy(update={"dataset": dataset, "columns": reviewed_columns})


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


# ---- true end-to-end subprocess invocation: harvest -> validate -> apply --------


def test_ucmeta_executable_runs_harvest_then_validate_then_apply_against_the_fake(tmp_path: Path):
    """Proves `./cli/ucmeta` genuinely runs as a subprocess, not just that the
    underlying Python functions compose: a freshly harvested skeleton fails
    validate (still placeholders), a hand-reviewed version of the same
    contract passes validate and prints its planned writes, `apply --dry-run`
    changes nothing, and a real `apply` lands and is logged."""
    skeleton_path = tmp_path / "customers_skeleton.yaml"
    reviewed_path = tmp_path / "customers_reviewed.yaml"
    log_path = tmp_path / "release_log.jsonl"

    harvest_result = _run_cli("harvest", TABLE, "--ba-id", KNOWN_BA_ID, "-o", str(skeleton_path))
    assert harvest_result.returncode == 0
    assert "Wrote a harvested skeleton contract" in harvest_result.stdout
    assert skeleton_path.exists()

    validate_skeleton = _run_cli("validate", str(skeleton_path))
    assert validate_skeleton.returncode == 1
    assert "FAIL" in validate_skeleton.stdout
    assert "placeholder" in validate_skeleton.stdout
    assert "Planned catalogue writes" in validate_skeleton.stdout  # printed regardless of pass/fail

    _fully_reviewed_contract(FakeUCClient()).to_yaml(reviewed_path)

    validate_reviewed = _run_cli("validate", str(reviewed_path))
    assert validate_reviewed.returncode == 0
    assert f"PASS: {reviewed_path} has no problems." in validate_reviewed.stdout
    assert "Planned catalogue writes" in validate_reviewed.stdout

    dry_run = _run_cli(
        "apply", str(reviewed_path), "--approved-by", APPROVER, "--dry-run", "--log-path", str(log_path)
    )
    assert dry_run.returncode == 0
    assert "Dry run" in dry_run.stdout
    assert "nothing written" in dry_run.stdout
    assert not log_path.exists()  # a dry run publishes nothing to the release log

    real_apply = _run_cli("apply", str(reviewed_path), "--approved-by", APPROVER, "--log-path", str(log_path))
    assert real_apply.returncode == 0
    assert f"apply {TABLE}: success" in real_apply.stdout

    records = read_release_log(log_path)
    assert len(records) == 1
    assert records[0].deployment_status == DeploymentStatus.SUCCESS
    assert records[0].approved_by == APPROVER


# ---- harvest -----------------------------------------------------------------


def test_harvest_writes_a_valid_skeleton_contract_yaml(tmp_path: Path):
    output_path = tmp_path / "customers.yaml"

    exit_code = cli.main(["harvest", TABLE, "--ba-id", KNOWN_BA_ID, "-o", str(output_path)])

    assert exit_code == 0
    contract = Contract.from_yaml(output_path)  # round-trips through Pydantic validation
    assert contract.dataset.qualifier.full_name == TABLE
    assert contract.dataset.owner.business_application_id == KNOWN_BA_ID
    assert len(contract.columns) > 0
    assert all(column.description is None for column in contract.columns)  # judgment fields left blank


# ---- validate ------------------------------------------------------------------


def test_validate_on_unreviewed_skeleton_fails_and_names_problems_and_still_prints_plan(
    tmp_path: Path, capsys
):
    contract_path = tmp_path / "customers.yaml"
    harvest(TABLE, FakeUCClient(), KNOWN_BA_ID).to_yaml(contract_path)  # skeleton: all placeholders

    exit_code = cli.main(["validate", str(contract_path)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "placeholder: dataset.description" in out
    assert "Planned catalogue writes" in out  # printed even on failure


def test_validate_on_fully_reviewed_contract_passes(tmp_path: Path, capsys):
    contract_path = tmp_path / "customers.yaml"
    _fully_reviewed_contract(FakeUCClient()).to_yaml(contract_path)

    exit_code = cli.main(["validate", str(contract_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS" in out


# ---- apply -----------------------------------------------------------------------


def test_apply_dry_run_prints_plan_and_performs_zero_writes(tmp_path: Path, capsys):
    """Uses `_cmd_apply` directly (rather than `main`) so the test can hold a
    reference to the exact `FakeUCClient` instance the CLI writes through and
    assert catalogue state is untouched -- `main` intentionally builds a fresh,
    unobservable client per invocation (`_build_client`), so this is the seam
    available for a state assertion at the CLI layer."""
    client = FakeUCClient()
    contract_path = tmp_path / "customers.yaml"
    _fully_reviewed_contract(client).to_yaml(contract_path)
    before = client.get_table(TABLE)
    args = cli._build_parser().parse_args(
        ["apply", str(contract_path), "--approved-by", APPROVER, "--dry-run"]
    )

    exit_code = cli._cmd_apply(args, client)

    assert exit_code == 0
    assert client.get_table(TABLE) == before  # nothing written
    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "nothing written" in out


def test_apply_for_real_succeeds_and_a_second_run_is_idempotent(tmp_path: Path, capsys):
    client = FakeUCClient()
    contract_path = tmp_path / "customers.yaml"
    _fully_reviewed_contract(client).to_yaml(contract_path)
    log_path = tmp_path / "release_log.jsonl"
    args = cli._build_parser().parse_args(
        ["apply", str(contract_path), "--approved-by", APPROVER, "--log-path", str(log_path)]
    )

    first_exit = cli._cmd_apply(args, client)
    state_after_first = client.get_table(TABLE)
    first_out = capsys.readouterr().out

    second_exit = cli._cmd_apply(args, client)
    state_after_second = client.get_table(TABLE)
    second_out = capsys.readouterr().out

    assert first_exit == 0
    assert second_exit == 0
    assert f"apply {TABLE}: success" in first_out
    assert f"apply {TABLE}: success" in second_out
    assert state_after_second == state_after_first  # same end state, not just "didn't error"

    records = read_release_log(log_path)
    assert len(records) == 2
    assert all(record.deployment_status == DeploymentStatus.SUCCESS for record in records)


# ---- coverage --------------------------------------------------------------------


def test_coverage_reports_over_a_small_set_of_fixture_contracts(tmp_path: Path, capsys):
    output_path = tmp_path / "coverage_report.json"

    exit_code = cli.main(["coverage", str(FIXTURES_DIR), "-o", str(output_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dataset(s), overall fill rate" in out
    assert "Wrote JSON coverage report" in out
    assert output_path.exists()
    assert '"dataset_count": 3' in output_path.read_text()


# ---- propose: the CLI wires its arguments through to propose.py -----------------


def test_propose_cli_wires_arguments_through_using_the_fixture_replay_client(tmp_path: Path):
    contract_path = tmp_path / "customers.yaml"
    harvest(TABLE, FakeUCClient(), KNOWN_BA_ID).to_yaml(contract_path)
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)

    exit_code = cli.main(["propose", str(contract_path), "--in-place"], llm_client=llm_client)

    assert exit_code == 0
    updated = Contract.from_yaml(contract_path)
    assert updated.columns[0].description is not None
    assert updated.columns[0].description.ai_proposed is True  # drafted, not yet reviewed


def test_propose_cli_writes_an_audit_record_next_to_the_output_contract(tmp_path: Path):
    """`_cmd_propose` always supplies `contract_path` (see its docstring), so
    the CLI's own propose verb -- not just calling `propose()` directly -- is
    what actually produces the `.audit.json` sibling a reviewer would find."""
    contract_path = tmp_path / "customers.yaml"
    harvest(TABLE, FakeUCClient(), KNOWN_BA_ID).to_yaml(contract_path)
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)

    exit_code = cli.main(["propose", str(contract_path), "--in-place"], llm_client=llm_client)

    assert exit_code == 0
    assert (tmp_path / "customers.audit.json").exists()


# ---- malformed input: a clean one-line error, not a raw traceback ----------------


def test_apply_on_a_nonexistent_contract_file_errors_cleanly(tmp_path: Path, capsys):
    """Unlike `validate` (which routes a missing file through `validate_yaml`'s
    own well-formedness check and reports it as an ordinary failed check, exit
    1), `apply` loads the contract directly via `Contract.from_yaml` -- the
    `FileNotFoundError` it raises is exactly what `_EXPECTED_ERRORS` exists to
    turn into a clean one-line error rather than a raw traceback."""
    missing_path = tmp_path / "does_not_exist.yaml"

    exit_code = cli.main(["apply", str(missing_path), "--approved-by", APPROVER])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert err.startswith("Error:")
    assert len(err.strip().splitlines()) == 1  # one line, not a traceback
    assert "Traceback" not in err


def test_harvest_with_an_unknown_business_application_id_errors_cleanly(tmp_path: Path, capsys):
    output_path = tmp_path / "customers.yaml"

    exit_code = cli.main(["harvest", TABLE, "--ba-id", "BA-99999", "-o", str(output_path)])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert err.startswith("Error:")
    assert "BA-99999" in err
    assert len(err.strip().splitlines()) == 1
    assert not output_path.exists()  # nothing written on a refused harvest
