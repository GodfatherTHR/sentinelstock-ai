"""Local tool routing with Cactus Needle (a 14 MB tool-calling model, no API cost).

The model never answers from its own knowledge and never writes: it maps an operator
question onto one of the read-only tools below, and deterministic repository code
executes it under the caller's JWT so row level security still applies. That keeps the
documented trust boundary ("typed tools only, no arbitrary SQL") while removing the paid
LLM call from this path.

Needle is imported lazily: the engine and weights download once on first use, and the
API keeps working when the package is not installed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger("sentinelstock.agent")

# Keep this list at five or fewer tools so Needle renders every schema directly.
# "triggers" are request regexes the model uses alongside the description; they make
# routing deterministic for the phrasing operators actually type.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "inventory_risk",
        "description": "Warehouse and SKU inventory coverage, stockout probability and risk level. Use for questions about stock levels, coverage days, or stockout risk.",
        "triggers": [r"\b(stock|stockout|stock-out|coverage|inventory|sku|reorder|risk)\b"],
        "parameters": {
            "type": "object",
            "properties": {
                "warehouse": {"type": "string", "description": "warehouse name to filter by"},
                "min_probability": {"type": "number", "description": "only rows at or above this stockout probability, 0 to 1"},
            },
            "required": [],
        },
    },
    {
        "name": "recommendation_queue",
        "description": "Replenishment recommendations and their approval state. Use when the question asks what is waiting for approval, what still needs a decision, or what is in the approval queue. Waiting, outstanding and needs-approval wording means the pending status.",
        "triggers": [r"\b(approv\w*|pending|waiting|outstanding|queue|recommendation\w*|decision\w*|reject\w*)\b"],
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved", "rejected"],
                    "description": "approval state to filter by: pending means still waiting for a decision and is the default for waiting or outstanding wording; approved means already signed off; rejected means declined",
                },
            },
            "required": [],
        },
    },
    {
        "name": "demand_forecast",
        "description": "Stored demand forecast rows per product and horizon. Use only for questions about forecast or predicted demand.",
        "triggers": [r"\b(forecast\w*|predict\w*|demand)\b"],
        "parameters": {
            "type": "object",
            "properties": {
                "horizon": {"type": "string", "enum": ["7d", "14d", "30d"], "description": "forecast horizon"},
                "product": {"type": "string", "description": "product name to filter by"},
            },
            "required": [],
        },
    },
    {
        "name": "maritime_watch",
        "description": "Live AIS vessel traffic with speed, navigation status and destination. Use for questions about ships, vessels, or maritime traffic.",
        "triggers": [r"\b(vessel\w*|ship\w*|maritime|ais|traffic|port\w*|cargo)\b"],
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "port code or destination text to filter by"},
            },
            "required": [],
        },
    },
    {
        "name": "crop_health",
        "description": "Sentinel-2 NDVI crop health per area of interest. Use for questions about crops, vegetation, NDVI, or satellite indices.",
        "triggers": [r"\b(crop\w*|ndvi|vegetation|satellite|field\w*|harvest\w*)\b"],
        "parameters": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "crop to filter by, for example wheat, maize, rice, soybean"},
            },
            "required": [],
        },
    },
]

# Below this routing confidence the question is treated as out of scope rather than
# answered from the wrong tool.
MIN_CONFIDENCE = 0.45

_agent: Any | None = None
_lock = threading.Lock()


def _load_agent():
    """Build (once) the Needle agent bound to the tool schemas above."""
    global _agent
    if _agent is not None:
        return _agent
    with _lock:
        if _agent is None:
            import needle  # imported lazily so the API runs without the package

            _agent = needle.Needle(tools=TOOLS, system="locale: en-US; device: server")
            log.info("loaded local Needle tool router")
    return _agent


def route_query(query: str) -> dict[str, Any]:
    """Ask the local model which tool (if any) serves this question."""
    try:
        agent = _load_agent()
    except ImportError:
        return {"tool": None, "arguments": {}, "confidence": None, "reasoning": "", "error": "cactus-needle is not installed"}
    turn = agent.complete(query)
    calls = turn.get("function_calls") or []
    confidence = turn.get("confidence")
    if not calls:
        return {
            "tool": None,
            "arguments": {},
            "confidence": confidence,
            "reasoning": turn.get("reasoning") or "",
            "error": "no tool matches that question",
        }
    if confidence is not None and confidence < MIN_CONFIDENCE:
        return {
            "tool": None,
            "arguments": {},
            "confidence": confidence,
            "reasoning": turn.get("reasoning") or "",
            "error": "the local router was not confident enough to pick a tool",
        }
    call = calls[0]
    return {
        "tool": call.get("name"),
        "arguments": call.get("arguments") or {},
        "confidence": confidence,
        "reasoning": turn.get("reasoning") or "",
        "error": None,
    }


def _status_from_query(query: str) -> str | None:
    """Resolve the approval-status filter from the question text.

    The local model routes reliably but picks the wrong enum member for wording like
    "waiting for approval", so this one argument is resolved deterministically instead.
    """
    text = (query or "").lower()
    if any(word in text for word in ("rejected", "declined", "denied")):
        return "rejected"
    if "approv" in text and any(word in text for word in ("already", "signed off", "did we", "have been")):
        return "approved"
    if any(word in text for word in ("waiting", "pending", "outstanding", "needs", "need a decision", "not approved", "to review", "unapproved", "queue")):
        return "pending"
    if "approv" in text:
        return "approved"
    return None


def execute_tool(name: str, arguments: dict[str, Any], repository, query: str = "") -> dict[str, Any]:
    """Run a routed tool against the repository (reads only, RLS enforced)."""
    if name == "inventory_risk":
        rows = repository.inventory()
        warehouse = str(arguments.get("warehouse") or "").lower()
        minimum = float(arguments.get("min_probability") or 0)
        selected = [
            row
            for row in rows
            if (not warehouse or warehouse in row.warehouse_name.lower()) and row.stockout_probability >= minimum
        ]
        selected.sort(key=lambda row: row.stockout_probability, reverse=True)
        return {
            "rows": [row.model_dump(mode="json") for row in selected[:10]],
            "summary": f"{len(selected)} of {len(rows)} warehouse × SKU rows match; highest stockout probability {selected[0].stockout_probability:.0%} ({selected[0].product_name} at {selected[0].warehouse_name})." if selected else "No inventory row matches that filter.",
        }

    if name == "recommendation_queue":
        status = _status_from_query(query) or arguments.get("status")
        rows = repository.recommendations()
        selected = [row for row in rows if not status or row.approval_status == status]
        pending = sum(1 for row in selected if row.approval_status == "pending")
        return {
            "rows": [row.model_dump(mode="json") for row in selected[:10]],
            "summary": f"{len(selected)} of {len(rows)} recommendations match (filter: {status or 'all'}); {pending} still need approval."
            if selected
            else f"No recommendation matches {status or 'that filter'}.",
        }

    if name == "demand_forecast":
        horizon = arguments.get("horizon")
        product = str(arguments.get("product") or "").lower()
        rows = repository.forecasts()
        selected = [
            row
            for row in rows
            if (not horizon or row.horizon == horizon) and (not product or product in row.product_name.lower())
        ]
        return {
            "rows": [row.model_dump(mode="json") for row in selected[:12]],
            "summary": f"{len(selected)} forecast rows match; run the baseline forecast if this is empty."
            if selected
            else "No stored forecast matches; run the baseline forecast first.",
        }

    if name == "maritime_watch":
        destination = str(arguments.get("destination") or "").strip().lower()
        if destination in {"port", "ports", "the port", "a port", "any port", "any", "harbour", "harbor"}:
            destination = ""  # generic wording is not a real destination filter
        rows = repository.vessels()
        selected = [row for row in rows if not destination or destination in (row.destination or "").lower()]
        moving = sum(1 for row in selected if (row.speed_knots or 0) > 0.5)
        return {
            "rows": [row.model_dump(mode="json") for row in selected[:10]],
            "summary": f"{len(selected)} vessels match, {moving} under way."
            if selected
            else "No vessel matches that destination.",
        }

    if name == "crop_health":
        crop = str(arguments.get("crop") or "").lower()
        rows = repository.crop_indices()
        selected = [row for row in rows if not crop or crop in (row.crop or "").lower()]
        if not selected:
            return {"rows": [], "summary": "No NDVI observation matches that crop."}
        weakest = min(selected, key=lambda row: row.health_score)
        return {
            "rows": [row.model_dump(mode="json") for row in selected[:10]],
            "summary": f"{len(selected)} NDVI observations match; weakest is {weakest.aoi_name} ({weakest.crop or 'unknown crop'}) at {weakest.health_score:.0%} health, NDVI {weakest.ndvi_mean:.2f}.",
        }

    return {"rows": [], "summary": f"Unknown tool {name!r}."}


def ask(repository, query: str) -> dict[str, Any]:
    """Route a question and execute the matched read-only tool."""
    routing = route_query(query)
    if routing["tool"] is None:
        return {
            "query": query,
            "tool": None,
            "arguments": {},
            "summary": routing.get("error") or "The local router did not match a tool for that question.",
            "rows": [],
            "confidence": routing.get("confidence"),
            "reasoning": routing.get("reasoning"),
            "model": "cactus-needle (local)",
        }
    result = execute_tool(routing["tool"], routing["arguments"], repository, query)
    return {
        "query": query,
        "tool": routing["tool"],
        "arguments": routing["arguments"],
        "summary": result["summary"],
        "rows": result["rows"],
        "confidence": routing.get("confidence"),
        "reasoning": routing.get("reasoning"),
        "model": "cactus-needle (local)",
    }
