"""`ucmeta`: one entry point, five verbs (spec: `cli/ucmeta` build verdict) --
`harvest`, `propose`, `validate`, `apply`, `coverage`. This module is pure
wiring: every verb is a thin composition of the module that already does the
real work (`harvest.py`, `propose.py`, `validate.py`, `apply.py`,
`coverage.py`) plus argument parsing, a human-readable print, and an exit code
a CI gate can branch on. No business logic lives here that isn't already
proven elsewhere.

Standard-library `argparse` is used rather than `click`/`typer`: five verbs
with a handful of flags each is squarely within what `argparse` handles
cleanly, and every dependency this codebase adds is itself a discipline
signal the spec calls out ("scattered scripts read as weaker") -- the same
reasoning cuts against reaching for a CLI framework the project doesn't
otherwise need.

Default backend, stated once here rather than left to be rediscovered per
verb: every verb defaults to `fake_uc.FakeUCClient`, the in-repo fake
catalogue, so a reviewer can clone this repository and run the whole
harvest -> propose -> validate -> apply loop with zero Databricks credentials
(spec Users & Roles: "the interview panel ... must be able to clone the repo
and run the full loop on a laptop with no Databricks account of their own;
the default run uses the in-repo fake catalogue"). Passing `--live` to any
verb switches that one call to `uc_client.RealUCClient` against the real
workspace, using the Databricks CLI profile named by `--profile` (default:
`uc_client.DEFAULT_UC_PROFILE`, `"ucmeta"`) -- the same `--live` convention
`tests/unit/test_uc_client_contract.py` and `tests/unit/test_apply.py` already
use for their own live smoke tests, and the same shape `tests/e2e` planning
describes for the demo scenario.

`validate` is the one verb that composes two modules that deliberately don't
call each other: `validate.py` runs the automated checks and stops there by
design ("this module deliberately does not ... print the exact catalogue
writes a merge would perform"); `apply.py`'s `plan_apply` builds that exact
write list but has no opinion on whether the contract is fit to merge. Gluing
them here -- run the checks, then print the plan regardless of whether the
checks passed -- is what actually satisfies the deferred Rules & Constraints
requirement, "every change request prints the full set of catalogue writes it
would perform before it can be merged": a reviewer sees both what's wrong and
exactly what would land if it were merged as-is.

`coverage`'s `-o`/`--output` writes JSON only -- rendering that JSON into the
static HTML dashboard (spec: `dashboard/app.py` build verdict) is deliberately
`dashboard/app.py`, a separate script run afterwards, not a `--html` flag added
here. Six-verb wiring plus HTML templating in one module would cost this file the
thing its own docstring calls out ("pure wiring ... no business logic lives
here"); see `dashboard/app.py`'s module docstring for the full reasoning.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import anthropic
import yaml
from pydantic import ValidationError

from uc_metadata import harvest as harvest_module
from uc_metadata.apply import ApplyResult, apply as apply_contract, plan_apply
from uc_metadata.coverage import CoverageReport, compute_coverage_for_directory
from uc_metadata.coverage_history import (
    DEFAULT_COVERAGE_HISTORY_TABLE,
    generate_run_id,
    publish_coverage_history,
)
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.harvest import harvest as harvest_contract
from uc_metadata.models import CertificationTier, Contract, Refresh
from uc_metadata.owner_registry import UnknownBusinessApplicationError
from uc_metadata.propose import propose as propose_contract
from uc_metadata.uc_client import DEFAULT_UC_PROFILE, RealUCClient, UCClient, UCClientError
from uc_metadata.validate import validate_yaml

# Repo root, resolved the same way models.SCHEMA_PATH / release_log.DEFAULT_LOG_PATH
# are: relative to this file, so it works regardless of the caller's cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONTRACTS_DIR = _REPO_ROOT / "contracts"

# Exceptions a caller can trigger by passing bad-but-plausible input (an unknown
# table, an unknown business-application id, a malformed YAML file, a contract
# that fails schema validation) -- reported as a clean one-line CLI error rather
# than a raw traceback. Anything not in this tuple is a bug, not a user mistake,
# and is left to surface as a real traceback rather than being silently masked.
_EXPECTED_ERRORS = (
    UCClientError,  # CoverageHistoryPublishError is a UCClientError subclass, already covered here
    UnknownBusinessApplicationError,
    FileNotFoundError,
    ValueError,
    yaml.YAMLError,
    ValidationError,
)


# ---- client construction: the one place --live is interpreted --------------------


def _build_client(args: argparse.Namespace) -> UCClient:
    """The default/`--live` switch every verb shares: `FakeUCClient` unless
    `--live` was passed, in which case `RealUCClient(profile=args.profile)`."""
    if args.live:
        return RealUCClient(profile=args.profile)
    return FakeUCClient()


def _add_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Use the real Unity Catalog workspace (RealUCClient) instead of the default "
            "in-repo fake catalogue (FakeUCClient). Needs the Databricks CLI profile named "
            "by --profile to already be authenticated (`databricks auth login`)."
        ),
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_UC_PROFILE,
        help=f"Databricks CLI profile to use with --live (default: {DEFAULT_UC_PROFILE!r}).",
    )


# ---- harvest -----------------------------------------------------------------


def _parse_refresh(cadence: Optional[str], sla_minutes: Optional[int]) -> Optional[Refresh]:
    """Precondition: both `--cadence` and `--sla-minutes` are given together, or
    neither is -- harvest.py's `Refresh` has no meaningful "half declared" state.
    Raises `ValueError` naming the mismatch otherwise."""
    if cadence is None and sla_minutes is None:
        return None
    if cadence is None or sla_minutes is None:
        raise ValueError("--cadence and --sla-minutes must be given together, or not at all")
    return Refresh(cadence=cadence, sla_minutes=sla_minutes)


def _cmd_harvest(args: argparse.Namespace, client: UCClient) -> int:
    refresh = _parse_refresh(args.cadence, args.sla_minutes)
    certification = CertificationTier(args.certification) if args.certification else None

    contract = harvest_contract(
        args.full_name,
        client,
        args.ba_id,
        description=args.description,
        refresh=refresh,
        retention_days=args.retention_days,
        certification=certification,
    )
    contract.to_yaml(args.output)

    print(f"Wrote a harvested skeleton contract for {args.full_name!r} to {args.output}")
    if contract.unreviewed_field_paths or _has_placeholder_fields(contract):
        print(
            "This is a skeleton: judgment fields are blank and/or carry a harvest "
            "placeholder. Run `ucmeta propose` and review before `ucmeta apply`."
        )
    return 0


def _has_placeholder_fields(contract: Contract) -> bool:
    """Cheap best-effort hint for the harvest summary print, not a substitute for
    `validate.py`'s real placeholder check -- reuses `harvest_module`'s own
    constants to avoid a second hand-maintained list of harvest's placeholder
    values."""
    dataset = contract.dataset
    return (
        dataset.description == harvest_module.PLACEHOLDER_DESCRIPTION
        or dataset.retention_days == harvest_module.PLACEHOLDER_RETENTION_DAYS
        or dataset.certification == harvest_module.PLACEHOLDER_CERTIFICATION
    )


# ---- propose -------------------------------------------------------------------


def _cmd_propose(
    args: argparse.Namespace,
    client: UCClient,
    *,
    llm_client: Optional[anthropic.Anthropic] = None,
) -> int:
    """`llm_client` is not a CLI flag -- there is no fake/real switch for the LLM
    call itself the way `--live` switches `UCClient` (propose.py always calls
    the real Anthropic API, gated only by `ANTHROPIC_API_KEY`). It is a
    keyword-only seam on this function (and threaded through `main`) so a test
    can inject `llm_fixture_transport`'s replay client and exercise the CLI's
    own argument-wiring offline, without ever needing a real API key.

    Always passes `contract_path=output_path` to `propose_contract` (this is
    the one layer that decides where the updated contract is about to be
    written -- `--in-place` or `-o`/`--output` -- so it is the one layer that
    can hand `propose.py` the path its `.audit.json` sibling belongs next to;
    see `propose.py`'s module docstring for the audit record's shape).
    """
    contract = Contract.from_yaml(args.contract)
    output_path = args.contract if args.in_place else args.output
    result = propose_contract(contract, client, llm_client=llm_client, contract_path=output_path)

    result.contract.to_yaml(output_path)
    print(f"Wrote updated contract to {output_path}")
    return 0


# ---- validate --------------------------------------------------------------------


def _cmd_validate(args: argparse.Namespace, client: UCClient) -> int:
    result = validate_yaml(args.contract, client)
    if result.ok:
        print(f"PASS: {args.contract} has no problems.")
    else:
        print(f"FAIL: {args.contract} -- {len(result.problems)} problem(s):")
        for problem in result.problems:
            print(f"  - {problem}")
    _print_planned_writes(args.contract, client)
    return 0 if result.ok else 1


def _print_planned_writes(contract_path, client: UCClient) -> None:
    """Print the full set of catalogue writes applying this contract would
    perform, regardless of whether it currently passes -- see this module's
    docstring for why this composition, not a change to `validate.py` itself,
    is what satisfies the deferred "print every write before merge" rule."""
    try:
        contract = Contract.from_yaml(contract_path)
    except Exception:
        return  # not a well-formed contract; validate_yaml already reported that above
    plan = plan_apply(contract, client)
    print()
    print(f"Planned catalogue writes for {contract.dataset.qualifier.full_name} ({len(plan)} statement(s)):")
    if not plan:
        print("  (none)")
    for statement in plan:
        print(f"  {statement}")


# ---- apply -------------------------------------------------------------------


def _cmd_apply(args: argparse.Namespace, client: UCClient) -> int:
    contract = Contract.from_yaml(args.contract)

    if args.dry_run:
        plan = plan_apply(contract, client)
        print(
            f"Dry run: {len(plan)} statement(s) would be applied for "
            f"{contract.dataset.qualifier.full_name} (nothing written):"
        )
        for statement in plan:
            print(f"  {statement}")
        return 0

    result = apply_contract(contract, client, approved_by=args.approved_by, log_path=args.log_path)
    _print_apply_result(contract, result)
    return 0 if result.ok else 1


def _print_apply_result(contract: Contract, result: ApplyResult) -> None:
    full_name = contract.dataset.qualifier.full_name
    print(f"apply {full_name}: {result.status.value}")
    if result.problems:
        print(f"  refused -- {len(result.problems)} validation problem(s):")
        for problem in result.problems:
            print(f"    - {problem}")
    for attempt in result.writes_succeeded:
        print(f"  OK   {attempt.label}")
    for attempt in result.writes_failed:
        print(f"  FAIL {attempt.label}: {attempt.error}")
    if result.release_log_error:
        print(f"  {result.release_log_error}")


# ---- coverage ------------------------------------------------------------------


def _cmd_coverage(args: argparse.Namespace, client: UCClient) -> int:
    report = compute_coverage_for_directory(args.contracts_dir, client=client)
    _print_coverage_summary(report)
    if args.output:
        Path(args.output).write_text(report.model_dump_json(indent=2) + "\n")
        print(f"\nWrote JSON coverage report to {args.output}")
    if args.publish_history:
        _publish_history(report, client)
    return 0


def _publish_history(report: CoverageReport, client: UCClient) -> None:
    """`--publish-history`'s one call site. Deliberately after the report is
    already computed and (if requested) already written to disk -- spec Rules
    & Constraints: "coverage is still computed and the point-in-time report
    is still written, because publishing history is a step after the
    measurement, not a precondition of it." A `CoverageHistoryPublishError`
    here propagates out of `_cmd_coverage` to `main`'s `_EXPECTED_ERRORS`
    handling, which prints it and exits non-zero -- loud, not swallowed, and
    the report file on disk already reflects a successful measurement
    regardless of how this step ends."""
    run_id = generate_run_id()
    publish_coverage_history(report, client, run_id)
    print(
        f"\nPublished coverage history for run {run_id!r}: {report.dataset_count} row(s) "
        f"appended to {DEFAULT_COVERAGE_HISTORY_TABLE}"
    )


def _print_coverage_summary(report: CoverageReport) -> None:
    print(f"Coverage report generated at {report.generated_at.isoformat()}")
    print(f"{report.dataset_count} dataset(s), overall fill rate {report.overall_fill_rate:.0%}")
    print("By dimension:")
    for dimension, rate in report.fill_rate_by_dimension.items():
        print(f"  {dimension}: {rate:.0%}")
    print("By team:")
    for team in report.by_team:
        print(f"  {team.team}: {team.dataset_count} dataset(s), fill rate {team.fill_rate:.0%}")
    print("Outcome measures:")
    for measure in report.outcome_measures:
        note = " (simulated)" if measure.simulated else ""
        print(f"  {measure.name}: {measure.value} {measure.unit} (n={measure.sample_size}){note}")


# ---- argument parsing -----------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ucmeta",
        description=(
            "Contract-driven metadata for Unity Catalog datasets: harvest a table's schema, "
            "have an AI drafter propose descriptions and classifications, validate a contract "
            "before merge, apply it to the catalogue, and measure coverage across datasets.\n\n"
            "Every verb defaults to the in-repo fake catalogue (no Databricks account needed). "
            "Pass --live to run that verb against the real workspace instead."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="{harvest,propose,validate,apply,coverage}")
    subparsers.required = True

    _add_harvest_parser(subparsers)
    _add_propose_parser(subparsers)
    _add_validate_parser(subparsers)
    _add_apply_parser(subparsers)
    _add_coverage_parser(subparsers)
    return parser


def _add_harvest_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "harvest",
        help="Read a table's schema from the catalogue and write a skeleton contract.",
        description="Build a skeleton Contract from a table's harvested facts and write it to YAML.",
        epilog="Example: ucmeta harvest workspace.analytics.customers --ba-id BA-10231 -o contracts/customers.yaml",
    )
    parser.add_argument("full_name", metavar="catalog.schema.table", help="The table to harvest.")
    parser.add_argument("--ba-id", required=True, help="Business-application id naming this dataset's owner.")
    parser.add_argument("--description", help="Dataset description. Omit to leave a TODO placeholder.")
    parser.add_argument("--cadence", help="Refresh cadence, e.g. 'daily'. Requires --sla-minutes.")
    parser.add_argument("--sla-minutes", type=int, help="Refresh SLA in minutes. Requires --cadence.")
    parser.add_argument("--retention-days", type=int, help="Retention commitment in days.")
    parser.add_argument(
        "--certification",
        choices=[tier.value for tier in CertificationTier],
        help="Certification tier claim. Omit to leave the bronze placeholder.",
    )
    parser.add_argument("-o", "--output", required=True, help="Path to write the harvested contract YAML.")
    _add_client_args(parser)
    parser.set_defaults(handler=_cmd_harvest)


def _add_propose_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "propose",
        help="Ask the AI drafter to fill in a harvested contract's blank judgment fields.",
        description="Load a contract, draft descriptions/classifications for its blank fields, write it back.",
        epilog="Example: ucmeta propose contracts/customers.yaml --in-place",
    )
    parser.add_argument("contract", help="Path to the contract YAML to propose against.")
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument("--in-place", action="store_true", help="Overwrite the input contract file.")
    output_group.add_argument("-o", "--output", help="Path to write the updated contract to.")
    _add_client_args(parser)
    parser.set_defaults(handler=_cmd_propose)


def _add_validate_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "validate",
        help="Run the automated checks against a contract and print the writes it would perform.",
        description=(
            "Run drift, unreviewed-marker and placeholder-sentinel checks against a contract, "
            "then print the full set of catalogue writes applying it would perform. Exit code 0 "
            "on pass, non-zero on any failure -- suitable as a CI gate."
        ),
        epilog="Example: ucmeta validate contracts/customers.yaml",
    )
    parser.add_argument("contract", help="Path to the contract YAML to validate.")
    _add_client_args(parser)
    parser.set_defaults(handler=_cmd_validate)


def _add_apply_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "apply",
        help="Apply an approved contract's content to the catalogue.",
        description=(
            "Apply a contract to the catalogue. Refuses the whole contract, writing nothing, if "
            "it does not pass validate.py's checks. --dry-run prints the plan and writes nothing."
        ),
        epilog='Example: ucmeta apply contracts/customers.yaml --approved-by "jane"',
    )
    parser.add_argument("contract", help="Path to the contract YAML to apply.")
    parser.add_argument("--approved-by", required=True, help="Name of the human who approved this change.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the planned writes and exit without writing anything."
    )
    parser.add_argument(
        "--log-path",
        default=None,
        help="Release log path to append to (default: release_log.jsonl at the repository root).",
    )
    _add_client_args(parser)
    parser.set_defaults(handler=_cmd_apply)


def _add_coverage_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "coverage",
        help="Compute fill-rate coverage across a directory of contracts.",
        description="Compute owner/description/sensitivity/DQ-rule fill rate across a directory of contracts.",
        epilog="Example: ucmeta coverage contracts/ -o coverage_report.json",
    )
    parser.add_argument(
        "contracts_dir",
        nargs="?",
        default=str(_DEFAULT_CONTRACTS_DIR),
        help=f"Directory of contract YAML files to scan (default: {_DEFAULT_CONTRACTS_DIR}).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help=(
            "Path to write the coverage report as JSON. Feed this file to "
            "`python dashboard/app.py <this-path>` to render the static HTML dashboard -- "
            "rendering deliberately stays a separate script, not a flag here; see dashboard/app.py's "
            "module docstring for why."
        ),
    )
    parser.add_argument(
        "--publish-history",
        action="store_true",
        help=(
            "After computing coverage, append one row per dataset to the coverage-history table "
            f"({DEFAULT_COVERAGE_HISTORY_TABLE}) via this same run's client (fake or --live), "
            "through uc_metadata.coverage_history.publish_coverage_history. Off by default: the "
            "offline default never even calls this, so it never attempts a warehouse or history-table "
            "write (spec SC-002-03). On in the scheduled and live paths, per .github/workflows/coverage.yml."
        ),
    )
    _add_client_args(parser)
    parser.set_defaults(handler=_cmd_coverage)


# ---- entry point ---------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None, *, llm_client: Optional[anthropic.Anthropic] = None) -> int:
    """Parse `argv` (defaults to `sys.argv[1:]`) and run the selected verb.

    Postcondition: returns an exit code -- 0 on success, non-zero on any
    expected failure (`_EXPECTED_ERRORS`) or a verb's own non-zero result (e.g.
    `validate` failing its checks, `apply` not fully succeeding). Never lets an
    expected, user-triggerable error surface as a raw traceback; an
    unanticipated exception is a bug and is left to propagate.

    `llm_client` is forwarded only to `propose` (see `_cmd_propose`'s
    docstring); every other verb ignores it.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    client = _build_client(args)
    try:
        if args.command == "propose":
            return _cmd_propose(args, client, llm_client=llm_client)
        return args.handler(args, client)
    except _EXPECTED_ERRORS as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
