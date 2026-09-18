"""The AI drafting step (Glossary: Propose) -- fills a harvested contract
skeleton's blank judgment fields with AI-proposed, human-reviewable suggestions.

`propose(contract, client)` reads every column still needing a proposal (a
harvested skeleton has `description is None` on all of them; see `harvest.py`),
pulls a small masked sample of real rows through `client.sample_rows(...)`, and
asks a small, cheap model (`claude-haiku-4-5`, spec: propose.py build verdict --
"small cheap model, structured output") for a description, a business-term link,
a personal-data flag and a sensitivity classification per column, plus one
dataset-level sensitivity roll-up. Every value that comes back is wrapped as
`models.Proposed(..., ai_proposed=True)` -- this module never marks anything
reviewed; only a human does that (Rules & Constraints: "the AI proposes; it
never publishes").

Two things happen at the boundary with the LLM, because its response is
untrusted input the same way an HTTP body or a file upload would be (CC Ch. 8):

- A proposed `business_term` is only ever trusted if it names a real key in the
  loaded glossary; an invented term is dropped, never written into the contract
  (Data section: "a proposed `business_term` link must resolve to a real
  entry").
- A proposed dataset-level sensitivity is floored to at least `confidential` if
  any column came back `pii=True`, regardless of what the model said (Behaviour:
  "a dataset with a PII column is at least confidential" is enforced here, not
  merely hoped for).

Sample values reaching the drafter are masked before they leave this module
(Rules & Constraints: "sensitive column values are never sent to the AI drafter
unmasked") -- conservatively, by column name for anything that looks like it
could hold an email, a person's name, or a similar direct identifier, and as a
backstop, by value shape for anything that looks like an email address even in
a column whose name gave no hint. Numeric surrogate keys (e.g. `customer_id`)
are deliberately not masked: they identify a row, not a real-world person, and
the drafter needs them intact to describe join/primary-key columns correctly.

Every call prints its model, token counts, dollar cost and wall-clock latency
(Non-functional Requirements: "its latency and cost are printed") and also
returns them as `ProposalMetrics`, so a future CLI caller can surface them
without re-parsing stdout.

Every call is also auditable on disk (Rules & Constraints: "every AI proposal
is auditable: model, version, prompt, inputs, timestamp ... are recorded and
survive as long as the contract"). When `propose()` is given `contract_path`
(the path the caller is about to write the updated contract to -- `cli.py`'s
`propose` verb always passes this), it writes a `.audit.json` file next to
that contract (`contracts/analytics/customers.yaml` ->
`contracts/analytics/customers.audit.json`), via `write_audit_record`. That
file records the model name/version, a timestamp, both prompts sent, and the
column-level inputs (names plus the same masked sample values that actually
left this module -- never a raw PII value, by construction, since it is the
same `samples_by_column` mapping the request itself was built from).

Deliberately not recorded in that file: per-field acceptance state (which
`ai_proposed` markers were later cleared by a reviewer). The design chosen
here is (b) from the two options a durable audit trail could take: an audit
file that only records what was *proposed*, with acceptance read live from
the contract itself at read time (`Contract.unreviewed_field_paths`), rather
than (a) a second write, on every review/save, that updates this file's own
copy of acceptance state. (a) would need a new integration point wherever a
contract gets reviewed and re-saved -- there is no single such place yet, only
a human editing YAML by hand -- and would leave this file able to drift out of
sync with the contract it describes, which is a second source of truth this
module has no way to keep honest. (b) costs one join at read time (which
fields in `columns_proposed` are still `ai_proposed=True` on the live
contract) and never drifts, because it never copies the answer anywhere.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import anthropic
from pydantic import BaseModel, Field

from uc_metadata.glossary import load_glossary
from uc_metadata.models import Column, Contract, Proposed, Sensitivity
from uc_metadata.uc_client import UCClient

# The small, cheap model this prototype standardizes on (spec: propose.py build
# verdict, Non-functional Requirements "Performance (prototype)").
MODEL = "claude-haiku-4-5"

# Claude Haiku 4.5 list pricing as published at https://www.anthropic.com/pricing
# on 2026-09-17, the day this module was written. Update both constants if
# Anthropic changes list pricing -- nothing else in this module hard-codes cost.
HAIKU_4_5_INPUT_COST_USD_PER_MTOK = 1.00
HAIKU_4_5_OUTPUT_COST_USD_PER_MTOK = 5.00

# Ordering used to enforce the "PII column floors dataset sensitivity" rule --
# see `_enforce_pii_sensitivity_floor`.
_SENSITIVITY_ORDER = [
    Sensitivity.PUBLIC,
    Sensitivity.INTERNAL,
    Sensitivity.CONFIDENTIAL,
    Sensitivity.STRICTLY_CONFIDENTIAL,
]

_MASKED_VALUE = "***MASKED***"

# Column-name substrings that conservatively suggest a column could hold a
# direct personal identifier (Data section: "Sample values shown to the AI
# drafter ... must be masked, hashed or excluded for sensitive columns").
# Deliberately does not include generic surrogate-key suffixes like "_id":
# a numeric primary/foreign key (e.g. `customer_id`, `order_id`) identifies a
# row, not a real-world person by itself, and the drafter needs it intact to
# describe join columns correctly.
_PII_NAME_KEYWORDS = (
    "email",
    "name",
    "phone",
    "ssn",
    "address",
    "dob",
    "birth",
    "passport",
    "ip_address",
    "credential",
    "password",
    "token",
    "account_number",
)

_EMAIL_VALUE_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---- structured-output wire schema (private: the drafter's response shape,
# deliberately distinct from models.Column/models.Proposed, the domain shape a
# human reviews) ---------------------------------------------------------------


class _ColumnProposalPayload(BaseModel):
    """One column's proposal, exactly as the drafter must return it."""

    column_name: str
    description: str
    business_term: Optional[str] = Field(
        default=None,
        description="A glossary term slug (verbatim key) this column matches, or null if none fits.",
    )
    pii: bool
    sensitivity: Sensitivity
    note: Optional[str] = Field(
        default=None,
        description="Set only when genuinely ambiguous between two plausible meanings for this column.",
    )


class _DatasetProposalPayload(BaseModel):
    """The drafter's full response for one dataset: every requested column's
    proposal, plus a dataset-level sensitivity roll-up reasoned over them."""

    columns: List[_ColumnProposalPayload]
    dataset_sensitivity: Sensitivity
    dataset_sensitivity_note: Optional[str] = None


# ---- results returned to the caller -------------------------------------------


@dataclass(frozen=True)
class ProposalMetrics:
    """Cost and latency for one drafter call. Printed by `propose()` and also
    returned, so a caller that captures the return value (a future CLI) sees
    the same numbers without scraping stdout."""

    model: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float

    @property
    def cost_usd(self) -> float:
        input_cost = (self.input_tokens / 1_000_000) * HAIKU_4_5_INPUT_COST_USD_PER_MTOK
        output_cost = (self.output_tokens / 1_000_000) * HAIKU_4_5_OUTPUT_COST_USD_PER_MTOK
        return input_cost + output_cost

    def __str__(self) -> str:
        return (
            f"[propose] model={self.model} input_tokens={self.input_tokens} "
            f"output_tokens={self.output_tokens} cost_usd=${self.cost_usd:.6f} "
            f"latency_seconds={self.latency_seconds:.2f}"
        )


@dataclass(frozen=True)
class ProposeResult:
    """`propose()`'s return value: the updated contract plus the call's metrics."""

    contract: Contract
    metrics: ProposalMetrics


# ---- the durable audit record (Rules & Constraints: "every AI proposal is
# auditable") -- see this module's docstring for the acceptance-state design
# choice (b) this record deliberately does not implement. -----------------------


class ColumnProposalAudit(BaseModel):
    """One column's inputs, exactly as sent to the drafter for one `propose()`
    call. `masked_sample_values` is the same list `_masked_sample_values`
    already produced for the request itself -- never a second, independently
    computed copy that could mask differently -- so this record can never show
    a value the request did not already show."""

    column_name: str
    samples_masked: bool = Field(
        description="Whether at least one sample value sent for this column was masked before it left this module."
    )
    masked_sample_values: List[Any] = Field(
        default_factory=list,
        description="The (already-masked) sample values sent to the drafter for this column -- never raw.",
    )


class ProposalAuditRecord(BaseModel):
    """The on-disk audit record for one `propose()` call that actually asked
    the drafter something (Rules & Constraints: "model, version, prompt,
    inputs, timestamp ... recorded and survive as long as the contract").

    Deliberately excludes per-field acceptance state -- see this module's
    docstring for why: acceptance lives on the contract itself
    (`Proposed.ai_proposed`), and is read from there, live, whenever it is
    needed, rather than duplicated and re-synced here.
    """

    dataset_full_name: str
    model: str
    generated_at: datetime
    system_prompt: str
    user_prompt: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_seconds: float
    dataset_sensitivity_proposed: bool = Field(
        description="Whether this call also proposed a dataset-level sensitivity roll-up."
    )
    columns_proposed: List[ColumnProposalAudit]


def _audit_path_for_contract(contract_path: Union[str, Path]) -> Path:
    """`contracts/analytics/customers.yaml` -> `contracts/analytics/customers.audit.json`
    -- the sibling-file convention this module's docstring and the spec's Data
    table both name ("stored as ... a `.audit.json` next to the contract")."""
    path = Path(contract_path)
    return path.with_name(f"{path.stem}.audit.json")


def write_audit_record(record: ProposalAuditRecord, contract_path: Union[str, Path]) -> Path:
    """Serialize `record` to `.audit.json` next to `contract_path`, overwriting
    any previous audit record for this contract file (each `propose()` call
    that reaches this function describes a fresh drafting pass, not an
    append-only log the way `release_log.py` is -- the contract's own version
    history is what preserves earlier drafts, the same way it preserves
    earlier reviewed values). Returns the path written.
    """
    audit_path = _audit_path_for_contract(contract_path)
    audit_path.write_text(record.model_dump_json(indent=2) + "\n")
    return audit_path


def _build_audit_record(
    full_name: str,
    columns_to_propose: List[Column],
    samples_by_column: Dict[str, List[Any]],
    metrics: ProposalMetrics,
    *,
    system_prompt: str,
    user_prompt: str,
) -> ProposalAuditRecord:
    columns_proposed = [
        ColumnProposalAudit(
            column_name=column.name,
            samples_masked=any(value == _MASKED_VALUE for value in samples_by_column.get(column.name, [])),
            masked_sample_values=samples_by_column.get(column.name, []),
        )
        for column in columns_to_propose
    ]
    return ProposalAuditRecord(
        dataset_full_name=full_name,
        model=metrics.model,
        generated_at=datetime.now(timezone.utc),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        input_tokens=metrics.input_tokens,
        output_tokens=metrics.output_tokens,
        cost_usd=metrics.cost_usd,
        latency_seconds=metrics.latency_seconds,
        dataset_sensitivity_proposed=True,
        columns_proposed=columns_proposed,
    )


# ---- the public entry point ----------------------------------------------------


def propose(
    contract: Contract,
    client: UCClient,
    *,
    llm_client: Optional[anthropic.Anthropic] = None,
    sample_limit: int = 5,
    contract_path: Optional[Union[str, Path]] = None,
) -> ProposeResult:
    """Fill in `contract`'s blank judgment fields by asking the AI drafter.

    Precondition: `contract` is a harvested skeleton or a partially-reviewed
    contract -- every column with `description is None` is treated as needing a
    proposal; a column that already carries a description is left untouched, so
    re-running this on a partially-reviewed contract is safe. `client` is used
    only to read sample rows for retrieval context (`client.sample_rows`),
    never to write anything.

    Postcondition: returns a `ProposeResult` whose `contract` has a `Proposed`
    value (`ai_proposed=True`) on every previously-blank judgment field; every
    `business_term` is either `None` or a real glossary key, never an invented
    one; the dataset-level `sensitivity` is floored to at least `confidential`
    if any column was proposed `pii=True`. Also returns and prints
    `ProposalMetrics` (model, token counts, cost, latency).

    `contract_path` is optional and defaults to `None`, which skips audit
    persistence entirely (this is why every existing call site and test that
    predates this parameter is unaffected). When given -- `cli.py`'s `propose`
    verb always gives it, as the path the updated contract is about to be
    written to -- a `ProposalAuditRecord` is written next to it as
    `<name>.audit.json` (see `write_audit_record`, and this module's docstring
    for what is and is not recorded there). No audit file is written when
    there was nothing left to draft (no drafter call was made, so there is
    nothing to audit).

    `llm_client` defaults to a zero-argument `anthropic.Anthropic()` (reads
    `ANTHROPIC_API_KEY` from the environment); tests inject a fixture-backed
    client instead (see `tests/unit/llm_fixture_transport.py`).
    """
    columns_to_propose = _columns_needing_proposal(contract)
    if not columns_to_propose:
        # Nothing left to draft. Still return a zero-cost metrics object rather
        # than making every caller special-case "no call was made".
        metrics = ProposalMetrics(model=MODEL, input_tokens=0, output_tokens=0, latency_seconds=0.0)
        print(metrics)
        return ProposeResult(contract=contract, metrics=metrics)

    glossary = load_glossary()
    full_name = contract.dataset.qualifier.full_name
    sample_rows = client.sample_rows(full_name, limit=sample_limit)
    samples_by_column = {
        column.name: _masked_sample_values(column.name, sample_rows) for column in columns_to_propose
    }

    system_prompt = _build_system_prompt(glossary)
    user_prompt = _build_user_prompt(full_name, columns_to_propose, samples_by_column)

    active_llm_client = llm_client if llm_client is not None else anthropic.Anthropic()
    payload, metrics = _call_drafter(active_llm_client, system=system_prompt, user=user_prompt)
    print(metrics)

    if contract_path is not None:
        audit_record = _build_audit_record(
            full_name,
            columns_to_propose,
            samples_by_column,
            metrics,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        write_audit_record(audit_record, contract_path)

    updated_contract = _apply_proposals(contract, payload, glossary)
    return ProposeResult(contract=updated_contract, metrics=metrics)


# ---- column selection and masking ----------------------------------------------


def _columns_needing_proposal(contract: Contract) -> List[Column]:
    """Harvest always leaves all four judgment fields on a column `None`
    together (harvest.py: "the human judgments left blank"), so `description`
    alone is a reliable signal for "this column has never been proposed"."""
    return [column for column in contract.columns if column.description is None]


def _column_name_suggests_pii(column_name: str) -> bool:
    """Conservative, name-only heuristic for "this column might hold a direct
    personal identifier", applied before anything has classified the column
    (Rules & Constraints: masking happens ahead of classification, not after)."""
    lowered = column_name.lower()
    return any(keyword in lowered for keyword in _PII_NAME_KEYWORDS)


def _mask_sample_value(value: Any, *, column_is_pii_suspect: bool) -> Any:
    if value is None:
        return value
    if column_is_pii_suspect:
        return _MASKED_VALUE
    if isinstance(value, str) and _EMAIL_VALUE_PATTERN.match(value.strip()):
        # Defence in depth: an email-shaped value in a column whose name gave
        # no hint (e.g. a generic "contact" column) is still masked.
        return _MASKED_VALUE
    return value


def _masked_sample_values(column_name: str, rows: List[Dict[str, Any]]) -> List[Any]:
    """The masked sample values for one column, across up to `len(rows)` sample
    rows -- what actually reaches the drafter's prompt."""
    column_is_pii_suspect = _column_name_suggests_pii(column_name)
    return [_mask_sample_value(row.get(column_name), column_is_pii_suspect=column_is_pii_suspect) for row in rows]


# ---- prompt construction --------------------------------------------------------


def _build_system_prompt(glossary: Dict[str, str]) -> str:
    glossary_lines = "\n".join(f"- {term}: {definition}" for term, definition in sorted(glossary.items()))
    return (
        "You are drafting Unity Catalog metadata for a data platform. For each "
        "column you are given, propose a short, precise business description, "
        "an optional link to one of the glossary terms below, whether the "
        "column holds personal data (pii), and a sensitivity classification "
        "(public, internal, confidential, or strictly_confidential).\n\n"
        "Only ever set business_term to one of the glossary term slugs listed "
        "below, verbatim -- if none of them fit, leave business_term null. "
        "Never invent a term that is not in this list.\n\n"
        "If a column's meaning is genuinely ambiguous between two plausible "
        "readings (for example, a column named 'state' could be an order "
        "status or a US state abbreviation), pick the more likely meaning "
        "given its sample values, but set `note` to name the ambiguity "
        "explicitly so a human reviewer's attention lands on it -- never guess "
        "silently.\n\n"
        "Also propose one dataset-level sensitivity classification, reasoning "
        "over your own column-level proposals -- for example, a dataset with "
        "at least one pii column is at least confidential.\n\n"
        f"Glossary:\n{glossary_lines}"
    )


def _build_user_prompt(
    qualifier_full_name: str,
    columns: List[Column],
    samples_by_column: Dict[str, List[Any]],
) -> str:
    lines = [f"Dataset: {qualifier_full_name}", "", "Columns:"]
    for column in columns:
        samples = samples_by_column.get(column.name, [])
        sample_text = ", ".join(repr(value) for value in samples) if samples else "(no sample values available)"
        nullability = "nullable" if column.nullable else "not nullable"
        partition_note = ", partition key" if column.partition_key else ""
        lines.append(f"- {column.name} ({column.data_type}, {nullability}{partition_note}): samples = [{sample_text}]")
    lines.append("")
    lines.append(
        "Propose a description, business_term, pii and sensitivity for every "
        "column listed above, plus one dataset-level sensitivity classification."
    )
    return "\n".join(lines)


# ---- the drafter call itself -----------------------------------------------------


def _call_drafter(
    llm_client: anthropic.Anthropic,
    *,
    system: str,
    user: str,
) -> Tuple[_DatasetProposalPayload, ProposalMetrics]:
    start = time.perf_counter()
    response = llm_client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=_DatasetProposalPayload,
    )
    latency_seconds = time.perf_counter() - start

    payload = response.parsed_output
    if payload is None:
        raise ValueError("drafter response did not contain a parseable structured payload")

    metrics = ProposalMetrics(
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_seconds=latency_seconds,
    )
    return payload, metrics


# ---- wiring the (untrusted) response back into the (trusted) domain model -------


def _resolve_business_term(candidate: Optional[str], glossary: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """Trust-boundary check: a proposed `business_term` is only kept if it
    names a real glossary key. Returns `(resolved_term, warning)` -- `warning`
    is set (and `resolved_term` is `None`) when the drafter invented a term
    that does not exist, so the drop is visible to a reviewer rather than
    silent (Rules & Constraints: the drafter proposes, it never gets to invent
    an authoritative link)."""
    if candidate is None:
        return None, None
    if candidate in glossary:
        return candidate, None
    return None, f"AI proposed business_term {candidate!r}, which is not a real glossary term; dropped."


def _enforce_pii_sensitivity_floor(
    proposed_dataset_sensitivity: Sensitivity,
    column_proposals: List[_ColumnProposalPayload],
) -> Sensitivity:
    """Defensive floor at the LLM trust boundary: if any column came back
    `pii=True`, the dataset-level sensitivity can never be weaker than
    `confidential`, regardless of what the drafter said. Enforces the
    Behaviour-section invariant ("a dataset with a PII column is at least
    confidential") rather than merely hoping the model followed the prompt."""
    has_pii_column = any(item.pii for item in column_proposals)
    floor = Sensitivity.CONFIDENTIAL if has_pii_column else Sensitivity.PUBLIC
    if _SENSITIVITY_ORDER.index(proposed_dataset_sensitivity) < _SENSITIVITY_ORDER.index(floor):
        return floor
    return proposed_dataset_sensitivity


def _dataset_sensitivity_proposal(payload: _DatasetProposalPayload) -> Proposed[Sensitivity]:
    floored = _enforce_pii_sensitivity_floor(payload.dataset_sensitivity, payload.columns)
    note_parts = [payload.dataset_sensitivity_note]
    if floored != payload.dataset_sensitivity:
        note_parts.append(
            f"Raised from {payload.dataset_sensitivity.value} to {floored.value}: at least one column "
            "was proposed pii=True, which floors dataset sensitivity to at least confidential."
        )
    note = " ".join(part for part in note_parts if part) or None
    return Proposed.proposed(floored, note=note)


def _column_proposal(proposal: _ColumnProposalPayload, glossary: Dict[str, str]) -> Dict[str, Any]:
    """Build the `models.Column` field updates for one column's proposal.

    The drafter's per-column `note` (set only on genuine ambiguity, e.g.
    `orders.state`) and any business-term drop warning both land on the
    `description` field's `Proposed.note` -- description is the field a
    reviewer reads first, and it is the field the ambiguity is actually about
    (what this column means), so that is where the reviewer's attention should
    land regardless of which other field they check next.
    """
    resolved_term, term_warning = _resolve_business_term(proposal.business_term, glossary)
    note_parts = [proposal.note, term_warning]
    note = " ".join(part for part in note_parts if part) or None

    return {
        "description": Proposed.proposed(proposal.description, note=note),
        "business_term": Proposed.proposed(resolved_term) if resolved_term is not None else None,
        "pii": Proposed.proposed(proposal.pii),
        "sensitivity": Proposed.proposed(proposal.sensitivity),
    }


def _apply_proposals(contract: Contract, payload: _DatasetProposalPayload, glossary: Dict[str, str]) -> Contract:
    proposals_by_column_name = {item.column_name: item for item in payload.columns}

    updated_columns = []
    for column in contract.columns:
        proposal = proposals_by_column_name.get(column.name)
        if proposal is None:
            updated_columns.append(column)
            continue
        updated_columns.append(column.model_copy(update=_column_proposal(proposal, glossary)))

    updated_dataset = contract.dataset.model_copy(
        update={"sensitivity": _dataset_sensitivity_proposal(payload)}
    )
    return contract.model_copy(update={"dataset": updated_dataset, "columns": updated_columns})
