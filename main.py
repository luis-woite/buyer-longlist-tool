"""
Entry point for the buyer longlist builder.

Edit target_profile.py to describe the target company, then run:
    python main.py
"""

from config import LONGLIST_WORKBOOK, MAX_BUYERS_PER_CATEGORY
from target_profile import TARGET_COMPANY
from src.research.find_buyers import find_buyers
from src.output.longlist_sheet import write_longlist


def run() -> None:
    print(f"\n--- Researching buyers for: {TARGET_COMPANY.get('name')} ---")

    print("[1/2] Researching strategic and financial buyers (web search)...")
    result = find_buyers(TARGET_COMPANY, max_per_category=MAX_BUYERS_PER_CATEGORY)
    if "error" in result:
        print(f"   Research failed: {result['error']}")
        print("--- Aborted ---\n")
        return

    print(f"   Strategic buyers found: {len(result.get('strategic_buyers', []))}")
    print(f"   Financial buyers found: {len(result.get('financial_buyers', []))}")
    if result.get("research_notes"):
        print(f"   Research notes: {result['research_notes']}")

    print("[2/2] Writing longlist workbook...")
    try:
        path = write_longlist(result, output_path=LONGLIST_WORKBOOK)
        print(f"   Longlist saved to: {path}")
    except Exception as e:
        print(f"   Writing longlist failed: {e}")

    print("--- Done ---\n")


if __name__ == "__main__":
    run()
