"""Resolves a business-application id to the team, solution owner and contact
channel that own it.

Stands in for a production identity/service registry — the kind of system a real
Unity Catalog platform would already have (a ServiceNow-equivalent business-app
CMDB, or an internal service-ownership directory keyed by business-application id)
that `harvest.py`/`apply.py` would call instead of the hard-coded table below
(spec: F-PLATFORM-001, Data section — "Ownership ... Upstream identity/service
registry, referenced by business-application id" — and the `owner_registry.py`
build verdict, "mock behind a seam").

`models.Dataset.owner` stores only the `business_application_id` pointer, never
the resolved fields below, so a caller must call `resolve_owner(...)` again each
time it needs the current team/solution-owner/contact-channel rather than trusting
a copy that could silently rot (Glossary: Owner pointer). The one thing a caller
ever imports from this module is `resolve_owner`; `_OWNER_REGISTRY` is a private
implementation detail so that swapping it for a real registry client later needs
no caller-side change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


class UnknownBusinessApplicationError(KeyError):
    """No owner is registered for the given business-application id."""


@dataclass(frozen=True)
class Owner:
    """One business application's resolved ownership, as the upstream identity/
    service registry would report it: which team owns it, who the accountable
    solution owner is, and where to reach them."""

    team: str
    solution_owner: str
    contact_channel: str


# A small, realistic-looking stand-in for the upstream registry. Four entries is
# enough to demonstrate resolution (and its failure) without pretending to be a
# real directory -- see this module's docstring for what production would call
# instead.
_OWNER_REGISTRY: Dict[str, Owner] = {
    "BA-10231": Owner(
        team="Customer Analytics",
        solution_owner="Priya Natarajan <priya.natarajan@example.com>",
        contact_channel="#customer-analytics-support",
    ),
    "BA-20144": Owner(
        team="Marketing Growth",
        solution_owner="Marco Silva <marco.silva@example.com>",
        contact_channel="#marketing-growth-oncall",
    ),
    "BA-30587": Owner(
        team="Commerce Platform",
        solution_owner="Grace Okafor <grace.okafor@example.com>",
        contact_channel="#commerce-platform-support",
    ),
    "BA-40092": Owner(
        team="Data Platform",
        solution_owner="Devon Lee <devon.lee@example.com>",
        contact_channel="#data-platform-help",
    ),
}


def resolve_owner(business_application_id: str) -> Owner:
    """Resolve `business_application_id` to its team, solution owner and contact
    channel.

    Precondition: `business_application_id` is a non-empty string. Postcondition:
    returns the matching `Owner`, or raises `UnknownBusinessApplicationError`
    naming the id that had no match -- never a partial or best-guess `Owner`.
    """
    if not business_application_id:
        raise ValueError("business_application_id must be a non-empty string")
    try:
        return _OWNER_REGISTRY[business_application_id]
    except KeyError:
        raise UnknownBusinessApplicationError(
            f"no owner registered for business_application_id={business_application_id!r}"
        ) from None
