"""Original reports are immutable; ordered amendments form the current reading."""

from sqlalchemy import select
from .database import Event


def effective_report(db, event):
    result = dict(event.body)
    amendments = list(
        db.scalars(
            select(Event)
            .where(
                Event.workspace_id == event.workspace_id,
                Event.kind == "amendment",
                Event.body["original_event_id"].as_string() == event.id,
            )
            .order_by(Event.created_at, Event.id)
        )
    )
    for amendment in amendments:
        result.update(amendment.body.get("changes", {}))
    if amendments:
        result["amendments"] = [
            {
                "id": a.id,
                "actor": a.actor,
                "at": a.created_at.isoformat(),
                "reason": a.body["reason"],
                "changes": a.body["changes"],
            }
            for a in amendments
        ]
    return result
