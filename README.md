# Buyer Longlist Builder

Describe a target company, and this researches real potential acquirers — strategic buyers and financial buyers (PE funds) — using Claude with web search enabled, and writes a formatted Excel longlist with the grounding evidence next to each rationale.

Classic sell-side M&A grunt work: every analyst has built one of these by hand, pulling together a first-pass buyer list before a banker actually starts making calls. This is a first-pass aid to that process, not a replacement for a banker's own network and judgment.

Drop me a message on LinkedIn if you'd want something like this adapted for your firm's workflow.

## Where this actually stands

Built and tested in one pass. The trickiest technical piece — correctly parsing Claude's response when its hosted web search tool is enabled, which mixes narration text with search-tool blocks before the final answer — is tested directly against a realistic mixed-block response. What's *not* yet tested: an actual live web-search-augmented call, since that needs a real API key and real search results to validate properly.

The core grounding rule here is different from the other tools, and arguably the most important one: a buyer only belongs on the list if the search actually surfaced *real evidence* for the fit (a disclosed acquisition, a stated sector focus, an existing adjacent portfolio company) — not just "this is a big company in a related field," which is exactly the kind of plausible-sounding but unsupported claim an LLM will produce if you don't explicitly tell it not to. The model is instructed to return fewer candidates rather than pad the list to hit a count.

Other honest limitations:

- Research quality depends entirely on what's actually publicly searchable — a thesis-stage PE fund with no public portfolio page will be underrepresented, not because it's a bad fit but because there's nothing to find.
- No de-duplication across runs — rerunning for the same target overwrites the previous longlist rather than merging.
- This is a single-shot research call, not iterative — it doesn't follow up on ambiguous leads the way a human analyst would refine a second search.

## Structure

```
buyer_longlist_tool/
├── main.py              # runs the research + writes the longlist
├── target_profile.py     # edit this to describe your target company
├── config.py             # output paths, buyer count cap
├── requirements.txt
├── .env.example           # copy to .env, fill in your key
└── src/
    ├── research/         # the Claude + web search research step
    └── output/           # writes the Excel longlist
```

## Two ways to use this

**`python main.py`** — full longlist build. Discovers candidates across both
strategic and financial buyers. More thorough, more expensive (more searches).

**`python check_fit.py "Company Name"`** — cheaper, narrower check: is this
*one specific* company a plausible buyer for your target? One research
question instead of open-ended discovery, meaningfully fewer searches, and a
single API call instead of two. Good for testing the pipeline cheaply, or
for checking a specific name you already have in mind rather than discovering
a whole list. Prints straight to the console, no Excel file.

Both share the same grounding discipline and the same drift tripwire — if the
response doesn't actually mention both the target and the candidate by name,
that's treated as a failure rather than a plausible-looking wrong answer.

## Running it

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `ANTHROPIC_API_KEY` in `.env` — this one key covers both the model and the web search, no separate search API needed.

Edit `target_profile.py` with the company you're researching, then:
```bash
python main.py
```

Output lands at `output/buyer_longlist.xlsx` — a Summary sheet plus one sheet each for strategic and financial buyers.
