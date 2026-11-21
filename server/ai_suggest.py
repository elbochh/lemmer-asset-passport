"""AI-suggested wording for a vehicle rust visit (findings, treatment, verification).

Always a *suggestion*: stored apart from the technician's own record, labelled as
AI-generated, and never published to the passport. Uses the Gemini model when a
key is configured; otherwise a deterministic template built from the scan.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Suggestion(BaseModel):
    findings: str = Field(max_length=900)
    treatment: str = Field(max_length=900)
    verification: str = Field(max_length=900)


def template(scan: dict) -> dict:
    n = len(scan["findings"])
    pct = scan["area_pct"]
    sev = scan["severity"]
    if n:
        findings = (
            f"Automated scan found {n} possible rust region{'s' if n > 1 else ''} "
            f"covering about {pct:.1f}% of the inspected image (indicative severity: {sev}). "
            "Confirm each region on the vehicle and note its location, depth and whether "
            "it is surface rust, scale or perforation."
        )
        treatment = (
            "Suggested: clean the affected areas, remove loose scale, treat the bare metal "
            "and re-protect with the rustproofing product used for this vehicle type. "
            + (
                "Heavy coverage: assess structural parts before treating."
                if sev == "High"
                else "Record the product and areas treated."
            )
        )
    else:
        findings = (
            "Automated scan found no rust regions in the inspected image. A visual check of "
            "the whole undercarriage is still needed, since one image may not cover it."
        )
        treatment = "No treatment suggested by the scan. Treat only if the technician sees rust."
    verification = (
        "Re-inspect the treated areas after the product has cured, take an 'after' photo and "
        "note any area to follow up at the next visit."
    )
    return {"findings": findings, "treatment": treatment, "verification": verification}


def _gemini(scan: dict, base: dict) -> dict:
    from .ai import model_json, GENERATOR

    system = (
        "You help a vehicle rustproofing technician write short inspection notes. "
        "Use only the scan data given. Do not invent measurements, products or standards. "
        "Plain, cautious wording; each field under 600 characters."
    )
    prompt = (
        f"Rust scan: {len(scan['findings'])} regions, about {scan['area_pct']}% of the image, "
        f"indicative severity {scan['severity']}, model {scan['model'].get('name')}.\n"
        f"Baseline wording to improve:\n{base}"
    )
    result = asyncio.run(model_json(GENERATOR, system, prompt, Suggestion))
    return Suggestion.model_validate(result).model_dump()


def suggest(scan: dict) -> dict:
    base = template(scan)
    source = "template"
    try:
        import os

        if os.getenv("GEMINI_API_KEY"):
            base = _gemini(scan, base)
            source = "gemini"
    except Exception:
        pass  # keep the template wording
    return {
        **base,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
