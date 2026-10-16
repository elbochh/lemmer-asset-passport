"""Reviewed, versioned troubleshooting. Running steps never calls a model."""

import re
from sqlalchemy import select
from .operations_models import Procedure
from .identity import reference_key


def applicable(p, asset):
    return (
        p.manufacturer.casefold() == asset.manufacturer.casefold()
        and p.model.casefold() == asset.model.casefold()
        and (not p.product_number or p.product_number == reference_key(asset))
    )


def approved(db, wid, asset, customer=False):
    return [
        p
        for p in db.scalars(
            select(Procedure).where(
                Procedure.workspace_id == wid, Procedure.status == "Approved"
            )
        )
        if applicable(p, asset) and (not customer or p.customer_visible)
    ]


def normalize(s):
    return " ".join(re.findall(r"[a-z0-9]+", s.casefold()))


def matches(db, wid, asset, query, customer=False):
    words = set(normalize(query).split()) - {
        "the",
        "a",
        "and",
        "is",
        "it",
        "of",
        "to",
        "after",
        "with",
        "when",
    }
    results = []
    for p in approved(db, wid, asset, customer):
        exact = any(normalize(query) == normalize(s) for s in p.symptoms)
        score = max(
            [
                len(words & set(normalize(s).split()))
                / max(1, len(words | set(normalize(s).split())))
                for s in p.symptoms
            ]
            or [0]
        )
        results.append((p, exact, score))
    return sorted(results, key=lambda x: (x[1], x[2]), reverse=True)


def evidence(db, wid, asset):
    return [
        {
            "id": "PROC-" + p.id,
            "kind": "procedure",
            "title": p.title,
            "model": p.model,
            "product_number": p.product_number,
            "revision": str(p.version),
            "source": ("Synthetic demonstration. " if p.synthetic else "")
            + "Human-approved by "
            + p.reviewer,
            "owner_visible": p.customer_visible,
            "content": __import__("json").dumps(
                {
                    "symptoms": p.symptoms,
                    "steps": p.steps,
                    "solution": p.solution,
                    "references": p.references,
                }
            ),
            "procedure_id": p.id,
        }
        for p in approved(db, wid, asset)
    ]
