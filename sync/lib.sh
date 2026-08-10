# lib.sh — shared shell helpers. Source, don't execute.
#
# Directory policy lives in exactly one place: `sc paths <kind>`. This
# asks rather than reimplements, so there is nothing here that can
# drift out of step with the Node connectors. The answer is exported,
# so children (the connectors, and anything they spawn) inherit it and
# never spawn a resolver of their own.
#
# Requires PROSAIC_ROOT to be set by the sourcing script.

# Resolve one application directory via the single implementation.
sc_path() {
  "$PROSAIC_ROOT/cli/sc" paths "$1"
}

# Logs: human-readable, disposable, safe to delete.
sc_log_root() {
  sc_path log-dir
}
