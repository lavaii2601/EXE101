"""Small shared helper for parsing a strict-JSON LLM response.

Factored out of intent_orchestrator.py's own _parse_ai_json (which stays
as-is, unchanged) so services/ai_service.py doesn't need to import from
intent_orchestrator.py -- the wrong dependency direction, since
intent_orchestrator.py already depends on an ai_service instance passed
into it, not the other way around.
"""
import json


def parse_json_object(raw):
    """Strip ```json fences (if any) and parse. Returns a dict, or None on
    any failure -- never raises, and never accepts a non-dict result."""
    if not raw:
        return None
    cleaned = str(raw).strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None
