"""Central config for the buyer longlist builder."""

OUTPUT_DIR = "output"
LONGLIST_WORKBOOK = "output/buyer_longlist.xlsx"

# Upper bound on how many buyers to ask for per category (strategic /
# financial) — a cap, not a target; the model may return fewer if it
# can't find that many it's actually confident about.
MAX_BUYERS_PER_CATEGORY = 10
