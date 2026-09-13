# Spec: listening sessions

## Purpose

Let a person work through a document set out loud, with a reviewer
beside them, and come away with organized notes: the questions to put
to a witness, filed under the record they concern; the warnings that
were raised before a question was asked; the answers to what the
speaker asked along the way; and the realizations that cut across
records. Speech is the input because the work is paging and thinking,
not typing, and because the alternative is an hour of thought that
nobody wrote down. Deposition preparation is the first role; a client
interview and a plain document review are the others.

## Promises

- **Transcription is local.** `whisper-stream` (whisper.cpp) on the
  machine's microphone, in voice-activity mode: a pause ends an
  utterance. No audio leaves the machine; the model file is on disk.
  The capture device defaults to a real microphone over a virtual
  loopback device. *(tested: tests/test_listen.py, device choice and
  line parsing; the device itself is exercised by hand)*
- **The pointer follows the speaker.** An explicit cue ("page three",
  "Acme seventeen", "next page", "the psychiatrist call") moves it without a
  model call. Otherwise a substantive utterance whose distinctive words
  a different page clearly owns moves it there. The reviewer may move
  it from context the heuristics cannot see. Every move is announced
  on the terminal with the page's Bates token and title and recorded
  as an event; the speaker can always say the page. *(tested)*
- **One reviewer call per utterance, through the agent seam.** The
  prompt carries the role, the matter's session brief, the docset
  index, the current page's text, the questions already logged on it,
  and the last few exchanges; the reply is one JSON object (`kind`,
  `page`, `question`, `warning`, `reply`, `note`, `realization`). The
  reviewer never reads the matter directory and never runs tools. A
  reply that is not JSON is shown as prose and nothing is logged.
  *(tested)*
- **The notes file is always organized.** Rewritten after every event:
  NOTREAL header, one section per record in Bates order (questions
  with their warnings, then notes), realizations, the advice given,
  and the closing synthesis. `/undo` removes the most recently logged
  question wherever it is. The transcript (timestamped, page-tagged)
  and the event stream (JSON lines) sit beside the notes so nothing
  said is lost to reorganization. *(tested)*
- **The session never drives an interactive harness.** Speech goes to
  this process and nowhere else; an interactive Claude Code session
  running beside it is untouched. *(by construction: the only
  subprocesses are whisper-stream and agent-run)*
- **Typed input is a first-class path.** Lines on stdin are
  utterances; `/page N`, `/undo`, `/save`, `/where`, `/index`, `/quit`
  are commands. `--stdin-only` runs without a microphone, which is how
  the end-to-end test drives it and how a reviewer can be used over a
  transcript. *(tested)*

## Non-obvious constraints

- The docset should be the OCR'd copy of the production: the pointer
  and the reviewer read the PDF's text layer, and an image-only page is
  invisible to both.
- Latency is the reviewer's model. The `listen` role in `matter.yaml`
  (ADR-0044) should name a fast model; the closing synthesis can be
  slower.
- The title index is parsed heuristically from Markdown tables with a
  Bates column; a wrong title costs nothing but a terminal label.
- A question is logged from the reviewer's cleaned-up wording, not the
  raw transcript; the raw words are in the transcript sidecar.
