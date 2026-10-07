"""
Single buyer-fit check — a cheaper, narrower alternative to the full
longlist builder. Given a target company and ONE named candidate buyer,
checks whether that specific pairing is grounded in real evidence,
rather than open-endedly discovering many candidates.

Cheaper because:
- One research question ("is X a plausible buyer for Y"), not "find up
  to 10 buyers in each of 2 categories" — meaningfully fewer searches.
- A single API call. The task is small and closed-ended enough that the
  longlist builder's narration-before-JSON problem is much less likely,
  and the same robust JSON extraction is kept as a safety net regardless.

Same grounding discipline, and the same drift tripwire: before trusting
the verdict, the response is checked for actually mentioning BOTH the
target and the candidate by name — catches it drifting onto a different
pairing entirely, the same real failure mode the longlist builder hit.
"""

import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an M&A analyst assistant checking a single, specific \
buyer-fit hypothesis.

You will be given a target company's profile and ONE named candidate buyer. \
Use web search to check whether that specific candidate is a plausible \
acquirer of that specific target. Do not research or suggest any other \
buyers — evaluate only the one named.

CRITICAL GROUNDING RULES:
- Base your verdict only on real evidence your search actually surfaces — a \
stated sector focus, a disclosed past acquisition, an existing adjacent \
portfolio company, a public statement, etc.
- "Yes" requires solid, specific evidence. "Possible" means some plausible \
signal but nothing conclusive. "No" means either contrary evidence or \
genuinely nothing found connecting the two.
- Do not pad or embellish the rationale — if you find little or nothing, say so.
- Do not write a prose summary before your answer — go directly from research \
to the final JSON object below.

Respond with ONLY a JSON object (no markdown fences, no text after it),
matching exactly this schema:
{
  "target_company": "string",
  "candidate_buyer": "string",
  "fit": "Yes, Possible, or No",
  "rationale": "string — grounded in specific evidence found, or explaining why not",
  "evidence_source": "string or null — the specific source if one was found"
}"""


def _build_user_message(target_company: dict, candidate_buyer: str) -> str:
    return f"""Target company profile:
Name: {target_company.get('name')}
Description: {target_company.get('description')}
Sector: {target_company.get('sector')}
Approximate revenue: {target_company.get('approx_revenue')}
Geography: {target_company.get('geography')}

Candidate buyer to evaluate: {candidate_buyer}

Research whether this specific candidate is a plausible acquirer of this specific target."""


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
    """Same brace-depth JSON extraction used in find_buyers.py — see that
    module for the full rationale. Duplicated here rather than imported
    so this file can be copied around standalone if useful."""
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


REQUIRED_KEYS = ("target_company", "candidate_buyer", "fit", "rationale", "evidence_source")


def check_buyer_fit(target_company: dict, candidate_buyer: str) -> dict:
    """
    Returns {"target_company", "candidate_buyer", "fit", "rationale",
    "evidence_source"} or {"error": str}. Never raises.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"error": "ANTHROPIC_API_KEY not set — check your .env file."}
    if not candidate_buyer or not candidate_buyer.strip():
        return {"error": "No candidate buyer name provided."}

    try:
        client = Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": _build_user_message(target_company, candidate_buyer)}],
        )
        text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        if not text_blocks:
            return {"error": "No text content in the model's response."}

        full_text = "\n\n".join(text_blocks)  # for the name-mention tripwire below
        raw_text = text_blocks[-1]
        cleaned = _extract_json(raw_text)

        if "{" not in cleaned:
            return {"error": f"No JSON object found in the response. Response ended with: ...{raw_text[-400:]}"}

        parsed = json.loads(cleaned)
        missing = [k for k in REQUIRED_KEYS if k not in parsed]
        if missing:
            return {"error": f"Response missing expected field(s) {missing}."}

        # Tripwire: both names should appear somewhere in the full response —
        # if not, this likely drifted onto a different pairing entirely, the
        # same real failure mode the longlist builder hit.
        target_name = (target_company.get("name") or "").lower()
        buyer_name = candidate_buyer.lower()
        if target_name and target_name not in full_text.lower():
            return {"error": f"Response never mentions '{target_company.get('name')}' — likely drifted off-topic."}
        if buyer_name not in full_text.lower():
            return {"error": f"Response never mentions '{candidate_buyer}' — likely drifted off-topic."}

        # Hardcode both names from input, never trust the model's own echo.
        parsed["target_company"] = target_company.get("name")
        parsed["candidate_buyer"] = candidate_buyer

        return parsed

    except json.JSONDecodeError as e:
        return {"error": f"Could not parse JSON ({e}). Response ended with: ...{raw_text[-400:]}"}
    except Exception as e:
        return {"error": f"Research call failed: {e}"}
