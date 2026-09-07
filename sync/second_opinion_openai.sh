#!/bin/bash
# second_opinion_openai.sh --- a `second-opinion` role command (ADR-0045).
#
# Reads a prompt on stdin, posts it to an OpenAI-compatible chat endpoint,
# prints the assistant's reply. Configure through the matter's role:
#
#   agent:
#     roles:
#       second-opinion:
#         cmd: <prosaic>/sync/second_opinion_openai.sh
#         credential: prosaic.openai     # Keychain item; agent-run exports it as OPENAI_API_KEY
#         model: gpt-5                   # exported as AGENT_RUN_MODEL
#
# Environment: OPENAI_API_KEY (required), OPENAI_BASE_URL (default
# https://api.openai.com/v1; point it at any compatible server, local
# ones included), AGENT_RUN_MODEL or OPENAI_MODEL (default gpt-5).
# Nothing is stored; the prompt goes to the endpoint and the reply to
# stdout. Whether a given draft may leave the machine is the matter's
# decision, not this script's (see docs/review.md).
set -euo pipefail
: "${OPENAI_API_KEY:?OPENAI_API_KEY is not set (role credential: names a Keychain item)}"
BASE="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
MODEL="${AGENT_RUN_MODEL:-${OPENAI_MODEL:-gpt-5}}"
PROMPT_FILE="$(mktemp)"; trap 'rm -f "$PROMPT_FILE"' EXIT
cat > "$PROMPT_FILE"
python3 - "$BASE" "$MODEL" "$PROMPT_FILE" <<'PY'
import json, os, sys, urllib.request
base, model, prompt_file = sys.argv[1], sys.argv[2], sys.argv[3]
prompt = open(prompt_file, encoding="utf-8", errors="replace").read()
req = urllib.request.Request(
    f"{base.rstrip('/')}/chat/completions",
    data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode(),
    headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=600) as r:
    data = json.load(r)
print(data["choices"][0]["message"]["content"])
PY
