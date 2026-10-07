"""
Buyer longlist research.

Given a target company profile, researches real potential strategic and
financial acquirers using Claude's hosted web search tool, then returns
a structured, grounded longlist.

ARCHITECTURE NOTE — why this is two separate API calls, not one:

The first version of this asked for web-search-grounded research AND a
strict JSON schema in a single call. In practice, the model reliably
wanted to narrate a "summary of evidence gathered" before producing the
JSON, no matter how explicitly the prompt forbade it — this looks like
an inherent pull toward narrating when the web search tool is active,
not a one-off prompting miss, since it reproduced across multiple
independent runs even after the instruction was strengthened.

So this is split into two calls with one job each:
  1. Research (web search ON, no schema) — the model can narrate as much
     as it wants; nothing here needs to be machine-parsed.
  2. Format (no tools) — a pure "convert this text into this JSON schema"
     task, which has no competing pull toward narration since there's no
     research to wrap up. This is the same shape of task every other
     tool's extraction step already does reliably.

Same grounding discipline as the other tools either way: a buyer only
belongs on the list if there's actual evidence behind the rationale — not
just "this is a big company in a related field" speculation.
"""

import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"

RESEARCH_SYSTEM_PROMPT = """You are an M&A analyst assistant researching potential \
acquirers for a sell-side screening exercise.

You will be given a target company's profile. Use web search to research real \
potential acquirers — both strategic buyers (companies that would acquire for \
synergies, market access, or portfolio expansion) and financial buyers (private \
equity funds with a relevant thesis or existing portfolio fit).

CRITICAL GROUNDING RULES:
- Only include a buyer if your search actually surfaced real evidence for the \
fit — a stated sector focus, a disclosed past acquisition in the space, an \
existing adjacent portfolio company, a public statement about expansion plans, \
etc. A buyer that merely "seems like it could fit" based on general industry \
knowledge, with nothing specific found, should not be included.
- Each rationale must reference the specific evidence found, not a generic \
statement of plausibility.
- If you cannot find enough real candidates to fill a category, list fewer — \
do not pad the list with speculative entries to hit a target count.
- Note anything that limited your research (e.g. limited public information on \
mid-market financial buyers' current thesis).

Write up your findings clearly, organized by Strategic Buyers and Financial \
Buyers, with the specific evidence for each. Prose, bullet points, however you \
like — this is a research write-up, not a final structured output, so there's \
no format constraint here."""

FORMATTING_SYSTEM_PROMPT = """Convert the research write-up you're given into \
a JSON object. Do not add, remove, or editorialize on any findings — this is a \
reformatting task, not a research task.

Respond with ONLY a JSON object (no markdown fences, no preamble, no text after \
it), matching exactly this schema:
{
  "target_company": "string",
  "strategic_buyers": [
    {"name": "string", "rationale": "string", "evidence_source": "string"}
  ],
  "financial_buyers": [
    {"name": "string", "rationale": "string", "evidence_source": "string"}
  ],
  "research_notes": "string or null"
}

If the write-up notes a candidate was considered but excluded for lacking \
evidence, do not include it in either list."""


def _build_research_message(target_company: dict, max_per_category: int) -> str:
    return f"""Target company profile:
Name: {target_company.get('name')}
Description: {target_company.get('description')}
Sector: {target_company.get('sector')}
Approximate revenue: {target_company.get('approx_revenue')}
Geography: {target_company.get('geography')}

Research up to {max_per_category} strategic buyers and up to {max_per_category} \
financial buyers, per the grounding rules in your instructions."""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _extract_json(text: str) -> str:
    """
    Returns the JSON object within text, tolerating narration before or
    after it. Finds the first '{' and scans forward tracking brace depth
    (respecting quoted strings) to find the matching close — kept as a
    safety net even in the formatting step, which shouldn't need it but
    costs nothing to have.
    """
    text = _strip_code_fences(text)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        return text

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

    return text[start:]


REQUIRED_KEYS = ("target_company", "strategic_buyers", "financial_buyers", "research_notes")


def _get_last_text_block(response) -> str:
    text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return text_blocks[-1] if text_blocks else ""


def find_buyers(target_company: dict, max_per_category: int = 10) -> dict:
    """
    Returns the researched longlist as a dict matching the schema above,
    or {"error": str} on failure. Never raises. Two API calls: research
    (with web search), then format (without) — see module docstring for why.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"error": "ANTHROPIC_API_KEY not set — check your .env file."}

    client = Anthropic()

    # --- Call 1: research, with web search, no format constraint ---
    try:
        research_response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=RESEARCH_SYSTEM_PROMPT,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": _build_research_message(target_company, max_per_category)}],
        )
        research_text = _get_last_text_block(research_response)
        if not research_text:
            return {"error": "No text content in the research call's response."}
    except Exception as e:
        return {"error": f"Research call failed: {e}"}

    # --- Call 2: format into JSON, no tools, nothing pulling toward narration ---
    try:
        format_response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=FORMATTING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": research_text}],
        )
        raw_text = _get_last_text_block(format_response)
        if not raw_text:
            return {"error": "No text content in the formatting call's response."}

        cleaned = _extract_json(raw_text)
        if "{" not in cleaned:
            return {
                "error": (
                    f"No JSON object found in the formatting response. Response ended with: "
                    f"...{raw_text[-500:]}"
                )
            }

        parsed = json.loads(cleaned)

        missing = [k for k in REQUIRED_KEYS if k not in parsed]
        if missing:
            return {"error": f"Response missing expected field(s) {missing}. Raw (first 500 chars): {raw_text[:500]}"}

        return parsed

    except json.JSONDecodeError as e:
        return {
            "error": (
                f"Found a '{{' but couldn't parse valid JSON from it ({e}). "
                f"Response ended with: ...{raw_text[-500:]}"
            )
        }
    except Exception as e:
        return {"error": f"Formatting call failed: {e}"}
