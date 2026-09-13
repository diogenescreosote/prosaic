---
name: listen
description: Run a listening session - the user talks through a Bates-stamped document set (deposition prep, a client interview, a document review) while a local transcriber and a headless reviewer keep organized notes and answer on the terminal. Use when the user wants to think aloud over a production, prepare deposition questions by voice, or turn a recorded interview into notes; never to drive Claude Code by voice.
---

# Listening session

`sc listen` (ADR-0048; spec `specs/listen.md`) transcribes the
microphone locally with `whisper-stream`, follows the speaker through
a Bates-stamped PDF, and sends each utterance to a headless reviewer
(`cli/agent-run --role listen`) that logs witness questions under the
record they concern, warns before a risky question, answers what it is
asked, and keeps the realizations. The notes file is rewritten after
every event; the transcript and event stream sit beside it.

## Before starting

1. **The docset is the OCR'd copy** of the production (the reviewer
   reads the text layer). `--bates-first` is the token on its page 1.
   An index with a Bates column (`--index`) gives the terminal titles.
2. **Write the session brief** (`--brief`), matter-specific and short:
   who the witness is and what she was to the parties; the privilege
   map (who holds what, who is a patient, what is attorney-client);
   the expert-fee rule and what makes a question an opinion question;
   the tone the transcript must keep and why; the topics that matter;
   the dates that anchor the chronology. The role prompt is generic;
   the brief is where the matter's landmines go.
3. **Route the role to a fast model** in `matter.yaml`:
   `agent.roles.listen: {model: claude-sonnet-5, max_turns: 1}`.
4. **Check the microphone once**: `whisper-stream --help` lists
   capture devices; the session prefers one named "microphone" over a
   loopback device. macOS asks for permission the first time; the user
   grants it, not you.

## Running

```sh
sc listen --role depo-prep \
  --docset ../other-matter/production/records.ocr.pdf --bates-first ACME00001 \
  --index ../other-matter/production/records_split/INDEX.md \
  --brief src/depo/LISTEN_BRIEF.md --out src/depo/questions_YYYY-MM-DD.md
```

Roles: `depo-prep`, `client-interview`, `document-review`
(`listen/roles/`). `--stdin-only` runs on typed input (testing, or a
reviewer over a transcript). Typed commands during a session: `/page N`,
`/undo`, `/save`, `/where`, `/index`, `/quit`. Ctrl-C ends the session
and writes the closing synthesis.

## Afterwards

- The notes file carries a NOTREAL header and is machine-transcribed
  work product: keep it under `src/` or `memos/`, never `assets/`.
- The transcript is machine text; verify against the recording before
  quoting it in anything filed.
- Commit as `draft` (notes) with `Verified: machine --- unverified`.
