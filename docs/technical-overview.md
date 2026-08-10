# Technical overview

(The plain-language introduction lives in the repo README; this page
is the engineer's map.)

**Client-side litigation infrastructure.** prosaic helps a person in
a legal case organize their evidence, communications, work product, and
case knowledge — and turn it into court-ready documents — with AI doing
the clerical work under human control.

Think of it as **attorney–client middleware**: you (the client) keep a
complete, searchable, well-organized case file on your own machine, so
that your lawyer's time goes to judgment and advocacy instead of
document wrangling — and so that you're never dependent on anyone else
to know what's in your own case. Full pro se support is the long-term
star to steer by; today, the honest framing is that prosaic makes a
*represented* client radically more capable.

> ⚠️ **prosaic is not a lawyer and nothing here is legal advice.**
> It's plumbing. Decisions about what to file, say, or sign belong to
> you and, if you have one, your attorney.

## What it does

- **One layout for every matter.** A disciplined directory convention
  (`inbox/` → `assets/` with an authoritative `INDEX.md`, `pleadings/`,
  `KNOWLEDGE.md`, `TODO.md`, `QUESTIONS.md`, …) that both humans and AI
  agents can navigate. See [docs/matter-layout.md](docs/matter-layout.md).
- **Connectors pull your record in automatically.** Modular fetchers
  sync external sources into the matter on a schedule — currently
  **Gmail** (thread → court-usable PDF), **law-firm portals** (official
  Message Report PDFs), and **MyCase** (client-portal document sync).
  Each is a small module conforming to a documented contract; write
  your own for whatever your case runs on. See
  [docs/connectors.md](docs/connectors.md).
- **Everything becomes searchable and citable.** New material is
  triaged on arrival: literate snake_case names, OCR text layers added
  to scanned PDFs (never overwriting originals), extracted-text
  sidecars, speaker-attributed transcripts for audio (local-only STT),
  and an index row describing what each item is and why it matters.
  See [docs/conventions.md](docs/conventions.md).
- **AI folds new material into case knowledge.** A headless
  [Claude Code](https://claude.com/claude-code) triage pass catalogs
  each new document, routes it to its proper home, and updates the
  matter's knowledge base — conservatively, with "needs human review"
  as the default when unsure. See [docs/triage.md](docs/triage.md).
- **Markdown in, filing-ready pleadings out.** A pleading generator
  renders Markdown source (with YAML front matter) into
  California-style 28-line pleading PDFs and DOCX, assembles multi-
  document filing "envelopes," fills common Judicial Council forms, and
  produces redacted variants. See
  [pleading/pleading_markdown_spec.md](pleading/pleading_markdown_spec.md).
- **Set-and-forget scheduling.** A launchd-based sync (macOS) runs
  every 12 hours with catch-up-once semantics after downtime, and the
  docs cover the real-world traps (TCC/Full Disk Access, cloud-synced
  folders). See [docs/scheduling.md](docs/scheduling.md).

## What it deliberately is not

- **Not a cloud service.** Your case file lives on your disk. Audio is
  transcribed locally. Credentials live in the OS keychain. The only
  third-party AI dependency is the agent harness you already use.
- **Not autonomous.** The AI never files, sends, or signs anything. It
  proposes; the record of what it did is logged and reviewable; the
  conventions are designed so a wrong guess is visible and cheap to fix.
- **Not a document assembly wizard.** No interview flows or fill-in-
  the-blank complaints. It assumes you (or your lawyer) write; it makes
  the writing land on pleading paper correctly and keeps the factual
  record organized underneath you.

## Repository layout

```
cli/          sc — the command-line entry point
pleading/     Markdown → pleading PDF/DOCX generator, envelope builder,
              Judicial Council form fillers, PDF redactor, OCR helper
connectors/   Source connectors (core contract + gmail, mycase)
sync/         Per-matter sync orchestrator + scheduler installer
triage/       AI triage prompt templates
templates/    New-matter scaffold (incl. the matter CLAUDE.md)
examples/     A fictional demo matter
tests/        Scenario test harness (fixture matters + AI-judged checks)
specs/        What each component must accomplish (teleological specs)
design/       Architecture Decision Records — how it's built and why
docs/         The manual — start with docs/ARCHITECTURE.md
```

## Quickstart

```bash
git clone <this repo> && cd prosaic
uv sync                                    # reportlab, pypdf, pydantic, …
(cd connectors && npm install)             # puppeteer, googleapis, …
./cli/sc deps                              # what else you need, and how to get it

# Scaffold a matter
./cli/sc init ~/cases/smith-v-smith

# Configure connectors + envelopes
$EDITOR ~/cases/smith-v-smith/matter.yaml

# Pull sources + triage new material into the matter
./cli/sc sync ~/cases/smith-v-smith

# Build a filing envelope from Markdown sources
cd ~/cases/smith-v-smith && sc build responsive_declaration

# Install the every-12-hours background sync (macOS)
./cli/sc schedule install ~/cases/smith-v-smith
```

Requirements: macOS (Linux mostly works, scheduling docs are macOS-
first), Python 3.12+, and Node 18+. Everything else the pipeline
shells out to is declared in `system-dependencies.yaml` and reported
by `sc deps`, which prints the install command for your platform —
that list, not this paragraph, is the authority. Two things are
optional: `whisper-cpp` and `ffmpeg`, needed only for local
transcription, and Claude Code, needed only for the AI triage layer.

See [docs/install.md](install.md) for the container, which packages
the whole set.

## Design principles

1. **Plain files over databases.** A matter is a directory of ordinary
   files with Markdown metadata. Anything can read it; nothing can
   hold it hostage; git gives you history and provenance for free.
2. **The index never lies.** Every asset change updates the matter's
   `INDEX.md` in the same change. An asset that isn't described in the
   index doesn't exist.
3. **Originals are sacred.** Processing supplements — OCR layers go in
   `_ocr` siblings, transcripts in sidecars — and never modifies or
   replaces the bytes you received.
4. **AI is a clerk, not a lawyer.** Triage catalogs, routes, and
   summarizes under written conventions; anything uncertain is flagged
   for a human, and machine transcripts carry verify-before-citing
   banners.
5. **Modularity at the seams that actually vary.** Cases differ in
   *sources* (connectors) and *documents* (envelopes); those are
   config. The layout and conventions are deliberately opinionated.

## Status

Alpha. Extracted from a private system in daily use across several
live matters (civil and administrative) — the
components here are battle-tested, but the packaging, CLI, and docs
are young and macOS-centric. Expect sharp edges; file issues.

## License

[MIT](LICENSE).
