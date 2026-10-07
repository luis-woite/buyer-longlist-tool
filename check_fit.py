"""
Quick single-pair buyer fit check — cheaper alternative to main.py's
full longlist build.

Usage:
    python check_fit.py "Siemens"

Uses the same TARGET_COMPANY from target_profile.py as the target side
of the check. No Excel output — this is meant to be a quick, cheap
yes/no-style check, so a console print is enough.
"""

import sys

from target_profile import TARGET_COMPANY
from src.research.check_fit import check_buyer_fit


def run(candidate_buyer: str) -> None:
    print(f"\n--- Checking fit: {candidate_buyer} -> {TARGET_COMPANY.get('name')} ---")
    result = check_buyer_fit(TARGET_COMPANY, candidate_buyer)

    if "error" in result:
        print(f"Failed: {result['error']}")
        return

    print(f"Fit: {result['fit']}")
    print(f"Rationale: {result['rationale']}")
    print(f"Evidence: {result['evidence_source']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python check_fit.py "Candidate Buyer Name"')
        sys.exit(1)

    run(sys.argv[1])
