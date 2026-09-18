"""SC-001-01, executed as code: harvest -> hand-author -> validate -> apply ->
apply again, printed as a clear pass/fail summary a reviewer can run with zero
setup (spec: `tests/e2e/demo_scenario.py` build verdict -- "This is SC-001-01
executed as code").

Two modes, one scenario file -- the same steps below drive both, which is
itself the demonstration that the `UCClient` seam works (spec: "The same
scenario file serves both, which is itself the demonstration that the seam
works"):

- Default (`python tests/e2e/demo_scenario.py`, or `pytest tests/e2e/`): runs
  entirely against `FakeUCClient` -- no Databricks account, no API key, no
  network. This is the path any reviewer can run straight after cloning.
- `--live` (`python tests/e2e/demo_scenario.py --live`): the same steps
  against `RealUCClient(profile="ucmeta")` and the real
  `workspace.analytics.customers` table. That table already carries the
  content this scenario declares (`contracts/analytics/customers.yaml`,
  applied for real in a prior phase), so a successful `--live` run also
  confirms that state is still correct, not just that this run's own writes
  landed. Mirrors the `--live` convention `cli.py`, `test_apply.py` and
  `test_validate.py` already use, and needs the same opt-in gate for
  automated collection (`UC_LIVE_TESTS=1`) every other live test in this
  repository uses.

The judgment-field values every column is hand-authored with below are
transcribed verbatim from `contracts/analytics/customers.yaml` -- no AI
drafter is involved here, the same way every contract actually shipped under
`contracts/` was hand-authored (see that file's own header comment: this build
session had no `ANTHROPIC_API_KEY` available). `propose.py` is exercised
separately, in `tests/unit/test_propose.py`.

Runnable two ways: directly as a script (`main()` returns an exit code, the
`if __name__ == "__main__"` guard at the bottom wires it to `sys.exit`), and
under pytest (the two `test_demo_scenario_*` functions at the bottom are thin
wrappers around `main()` -- see `pyproject.toml`'s `python_files` setting,
which adds this exact filename to pytest's default collection glob so it is
picked up without renaming it to `test_demo_scenario.py`).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import pytest

from uc_metadata.apply import ApplyResult, apply, plan_apply
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.harvest import harvest
from uc_metadata.models import CertificationTier, Contract, Proposed, Refresh, Sensitivity
from uc_metadata.uc_client import RealUCClient, UCClient
from uc_metadata.validate import validate

TABLE = "workspace.analytics.customers"
BUSINESS_APPLICATION_ID = "BA-10231"
APPROVED_BY = "e2e-demo-reviewer"

UC_LIVE_TESTS_ENABLED = os.environ.get("UC_LIVE_TESTS") == "1"

# Per-column judgment-field values, transcribed verbatim from
# contracts/analytics/customers.yaml -- see this module's docstring for why
# this content, not freshly invented text, is what gets hand-authored here.
_COLUMN_REVIEWS = {
    "customer_id": dict(
        description="Surrogate primary key identifying one customer.",
        business_term=None,
        pii=False,
        sensitivity=Sensitivity.INTERNAL,
        tags=["primary_key"],
    ),
    "email": dict(
        description="Customer's primary electronic contact address.",
        business_term="email",
        pii=True,
        sensitivity=Sensitivity.CONFIDENTIAL,
        tags=[],
    ),
    "first_name": dict(
        description="Customer's given name, as provided at signup.",
        business_term=None,
        pii=True,
        sensitivity=Sensitivity.CONFIDENTIAL,
        tags=[],
    ),
    "last_name": dict(
        description="Customer's family name, as provided at signup.",
        business_term=None,
        pii=True,
        sensitivity=Sensitivity.CONFIDENTIAL,
        tags=[],
    ),
    "region": dict(
        description="Coarse geographic market this customer is associated with.",
        business_term="region",
        pii=False,
        sensitivity=Sensitivity.INTERNAL,
        tags=[],
    ),
    "signup_date": dict(
        description="Calendar date this customer's account was created.",
        business_term="signup_date",
        pii=False,
        sensitivity=Sensitivity.INTERNAL,
        tags=[],
    ),
    "lifetime_value": dict(
        description=(
            "Total historical revenue attributed to this customer across all "
            "orders to date, in USD."
        ),
        business_term="lifetime_value",
        pii=False,
        sensitivity=Sensitivity.INTERNAL,
        tags=[],
    ),
}


def _step(label: str) -> None:
    print(f"\n=== {label} ===")


def _harvest_and_hand_author(client: UCClient) -> Contract:
    """SC-001-01's first two beats: harvest the dataset's facts, then
    hand-author every judgment field as an already-reviewed value -- no AI
    drafter involved (see module docstring)."""
    _step("1. harvest -- read workspace.analytics.customers back from the catalogue")
    contract = harvest(
        TABLE,
        client,
        BUSINESS_APPLICATION_ID,
        description="Customer master records for the direct-to-consumer storefront.",
        refresh=Refresh(cadence="daily", sla_minutes=120),
        retention_days=730,
        certification=CertificationTier.SILVER,
    )
    print(f"  harvested {len(contract.columns)} column(s); every judgment field is still blank")

    _step("2. hand-author -- a human declares every judgment field; no AI drafter used")
    reviewed_columns = []
    for column in contract.columns:
        review = _COLUMN_REVIEWS[column.name]
        reviewed_columns.append(
            column.model_copy(
                update={
                    "description": Proposed.accepted(review["description"]),
                    "business_term": (
                        Proposed.accepted(review["business_term"]) if review["business_term"] else None
                    ),
                    "pii": Proposed.accepted(review["pii"]),
                    "sensitivity": Proposed.accepted(review["sensitivity"]),
                    "tags": review["tags"],
                }
            )
        )
    dataset = contract.dataset.model_copy(update={"sensitivity": Proposed.accepted(Sensitivity.CONFIDENTIAL)})
    contract = contract.model_copy(update={"dataset": dataset, "columns": reviewed_columns})
    print(f"  reviewed {len(reviewed_columns)} column(s) plus dataset sensitivity -- no unreviewed markers left")
    return contract


def _validate_and_print_plan(contract: Contract, client: UCClient) -> bool:
    """SC-001-01: "the automated checks pass and print the exact set of
    catalogue writes before merge"."""
    _step("3. validate -- run the automated checks, then print the planned writes")
    result = validate(contract, client)
    if result.ok:
        print(f"  PASS: {TABLE} has no problems.")
    else:
        print(f"  FAIL: {TABLE} -- {len(result.problems)} problem(s):")
        for problem in result.problems:
            print(f"    - {problem}")

    plan = plan_apply(contract, client)
    print(f"  planned catalogue writes ({len(plan)} statement(s)), nothing written yet:")
    for statement in plan:
        print(f"    {statement}")
    return result.ok


def _apply_and_report(contract: Contract, client: UCClient, log_path: Path, *, step_label: str) -> ApplyResult:
    _step(step_label)
    result = apply(contract, client, approved_by=APPROVED_BY, log_path=log_path)
    print(f"  apply {TABLE}: {result.status.value}")
    for attempt in result.writes_succeeded:
        print(f"    OK   {attempt.label}")
    for attempt in result.writes_failed:
        print(f"    FAIL {attempt.label}: {attempt.error}")
    return result


def run_scenario(client: UCClient, *, log_path: Path) -> bool:
    """Run the full SC-001-01 happy path against `client` and return whether
    every step succeeded. Shared by both the default (fake) and `--live`
    modes -- the same steps, only the client and log path differ.
    """
    contract = _harvest_and_hand_author(client)

    if not _validate_and_print_plan(contract, client):
        return False

    first_apply = _apply_and_report(
        contract, client, log_path, step_label="4. apply -- merge and write to the catalogue"
    )
    if not first_apply.ok:
        return False

    second_apply = _apply_and_report(
        contract,
        client,
        log_path,
        step_label="5. apply again -- confirm idempotency: re-applying an unchanged contract writes nothing further",
    )
    return second_apply.ok


def main(argv: Optional[List[str]] = None) -> int:
    """Parse `argv` (defaults to `sys.argv[1:]`), run the SC-001-01 scenario,
    and return an exit code -- 0 if every step passed, 1 otherwise. This is
    the one function both the script entry point and the pytest wrappers
    below call.
    """
    parser = argparse.ArgumentParser(
        description="Run SC-001-01 (harvest -> hand-author -> validate -> apply -> apply again) end to end.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run against the real Unity Catalog workspace (RealUCClient(profile='ucmeta')) instead of the fake.",
    )
    args = parser.parse_args(argv)

    if args.live:
        client: UCClient = RealUCClient(profile="ucmeta")
        mode = "live (RealUCClient, profile='ucmeta')"
    else:
        client = FakeUCClient()
        mode = "fake (FakeUCClient -- no network, no credentials)"

    print(f"tests/e2e/demo_scenario.py -- SC-001-01, mode: {mode}")
    with tempfile.TemporaryDirectory() as tmp_dir:
        # A scratch release log, not release_log.jsonl at the repo root -- a
        # demo run (fake or live) is not itself a real change request, and
        # should not add noise to the repository's real release history.
        log_path = Path(tmp_dir) / "demo_release_log.jsonl"
        ok = run_scenario(client, log_path=log_path)

    print()
    if ok:
        print(f"PASS: SC-001-01 happy path completed end to end ({mode}).")
        return 0
    print(f"FAIL: SC-001-01 happy path did not complete ({mode}); see problems above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())


# ---- pytest wrappers -------------------------------------------------------------
#
# `pyproject.toml`'s `python_files` setting adds this exact filename to pytest's
# collection glob (alongside the default `test_*.py`), so these are discovered
# without renaming the file away from the name the spec/task names explicitly.


@pytest.mark.scenario("SC-001-01")
def test_demo_scenario_default_mode_sc_001_01():
    """Default mode: entirely against `FakeUCClient`. No credentials, no
    network -- runnable by any reviewer immediately after cloning."""
    assert main([]) == 0


@pytest.mark.uc_live
@pytest.mark.scenario("SC-001-01")
@pytest.mark.skipif(
    not UC_LIVE_TESTS_ENABLED,
    reason="set UC_LIVE_TESTS=1 to run this against the live Free Edition workspace",
)
def test_demo_scenario_live_mode_sc_001_01():
    """`--live` mode: against the real Free Edition workspace, profile
    `ucmeta`. Same opt-in gate every other live test in this repo uses."""
    assert main(["--live"]) == 0
