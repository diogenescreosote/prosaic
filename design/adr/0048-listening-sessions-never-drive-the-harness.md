# 0048 — Listening sessions: speech goes to a reviewer, never to the harness

**Status:** accepted (2026-09)

## Context
The person preparing a deposition pages through a production and
thinks out loud: questions for the witness, doubts about privilege,
whether a question turns a percipient witness into an expert, what a
page reveals. An hour of that is worth keeping and nobody types while
doing it. Live local transcription exists (whisper.cpp), and the first
instinct is to pipe it into the interactive agent session.

That is the wrong shape. An interactive harness takes a prompt and
answers it; continuous speech would be chopped into prompts at every
pause, half-thoughts would be answered, and the microphone would be
driving a tool that can edit files, run builds and commit. The person
asked for the opposite: a companion that listens, keeps notes and
answers on the terminal, with the interactive session left alone.

## Decision
A listening session (`sc listen`) is its own process. Speech is
transcribed locally and handled here; the only subprocesses are
`whisper-stream` and one headless `agent-run` call per utterance under
the `listen` role, whose sole output is a JSON reply the session
applies. The reviewer never reads the matter directory and never runs
tools. The session's product is a notes file organized by record, with
the transcript and event stream beside it.

Roles are prompt files under `listen/roles/`: what the reviewer is for
and how it judges. Matter specifics (the privilege map, who holds what,
the fee-exposure rule, the tone the transcript must keep) are a session
brief the matter supplies, so a role stays generic and a brief can say
anything.

The page pointer is heuristics first, model second: explicit cues cost
nothing and are right; word overlap with a page's text catches a
quotation; the reviewer moves it only when the words make the page
plain. A wrong move is one spoken correction.

## Consequences
- Speech input to the interactive harness is not provided and should
  not be added; a session that wants the harness's powers is a
  different tool with a different safety case.
- The reviewer's quality is the model's and the brief's. A thin brief
  gives generic warnings; the brief is where the matter's landmines go.
- Latency per utterance is one model round trip; the `listen` role
  should be routed to a fast model (ADR-0044).
- The transcript is machine text under the matter's rule: verify
  against the recording before citing it anywhere.
