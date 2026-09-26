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
#         effort: low                    # optional; exported as AGENT_RUN_EFFORT
#         timeout: 1800                  # optional read timeout, seconds
#
# Environment: OPENAI_API_KEY (required), OPENAI_BASE_URL (default
# https://api.openai.com/v1; point it at any compatible server, local
# ones included), AGENT_RUN_MODEL or OPENAI_MODEL (default gpt-5),
# AGENT_RUN_EFFORT (sent as reasoning_effort; omitted when unset, so the
# endpoint's default applies), AGENT_RUN_TIMEOUT (seconds between streamed
# chunks, default 1800). The reply is streamed; see the note below.
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
body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
effort = os.environ.get("AGENT_RUN_EFFORT", "").strip()
if effort:
    body["reasoning_effort"] = effort
timeout = float(os.environ.get("AGENT_RUN_TIMEOUT") or 1800)
# Stream the reply. A large prompt answered in one non-streaming response
# leaves the connection silent until the whole answer is ready, and
# something on the path drops it: reviews that stream in about thirty
# seconds died at the read timeout. Streaming keeps bytes moving, and the
# timeout then bounds the gap between chunks, not the whole answer.
body["stream"] = True
body["stream_options"] = {"include_usage": True}
req = urllib.request.Request(
    f"{base.rstrip('/')}/chat/completions",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
)
parts, usage, served_model = [], {}, model
with urllib.request.urlopen(req, timeout=timeout) as r:
    for raw in r:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        ev = json.loads(payload)
        served_model = ev.get("model") or served_model
        if ev.get("usage"):
            usage = ev["usage"]
        for ch in ev.get("choices") or []:
            piece = (ch.get("delta") or {}).get("content")
            if piece:
                parts.append(piece)
print("".join(parts))
# Usage travels on stderr as one tagged JSON line so the caller can price
# the call (ADR-0045: the human is told what an outside model cost).
print("@@USAGE " + json.dumps({"model": served_model,
                               "input_tokens": usage.get("prompt_tokens", 0),
                               "output_tokens": usage.get("completion_tokens", 0)}), file=sys.stderr)
PY
