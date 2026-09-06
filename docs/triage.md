# AI triage

After each sync, one headless agent
session folds everything new into the matter: catalog rows for email
threads, knowledge updates from message reports, routing for staged
portal documents. This page explains the design and its guardrails.

## How it runs

`sync/matter_sync.sh` collects the `NEW <path>` lines from every
connector, then runs:

```bash
cd <matter_dir> && cli/agent-run --yolo < prompt.txt
```

- The prompt is `triage/prompts/sync_triage.md` plus the file list.
  Edit the template to tune behavior; it's plain Markdown.
- Running *inside the matter directory* means the agent picks up the
  matter's `AGENTS.md` automatically — the agent contract (index
  discipline, originals-are-sacred, em-dash rules, NOTREAL, "you are a
  clerk, not a lawyer") applies to every triage session without being
  repeated in the prompt.
- `--dangerously-skip-permissions` is what makes unattended operation
  possible: there is no human present to approve each edit. The risk
  is bounded by the prompt's scope rules, the matter contract, and the
  fact that the matter is (ideally) a git repository — every triage
  session's changes are diffable and revertable.

## Design principles

**Complete by instruction.** Reading is mechanical, not discretionary.
`triage/read_coverage.py` classifies every page of a PDF, exits
non-zero when any page is not covered by its text layer, and with
`--text` emits the whole document page-marked so the agent has every
page in context and the markers prove which ones. This exists because
the expensive triage failure is not a mis-route — it is a confident
catalog row written after a partial read, which is indistinguishable
from a good one and which every later draft inherits. The page classes,
and what each asks of the reader, are in "Reading every page" below.

**Conservative by instruction.** The prompt's standing order: when
significance or routing is unclear, *leave the file where it is*, mark
it "needs human review" in the catalog/index, and move on. A triage
pass that does less is recoverable; one that guesses wrong and moves
records around confidently is expensive.

**Small increments.** The 12-hour cadence means a typical triage sees
a handful of files. Initial bulk imports (hundreds of historical
threads/documents) should NOT go through the headless pass — do those
interactively, with mechanically generated backfill indexes and a
human (or supervised agent) deciding cataloging depth.

**Everything it does is legible.** Catalog rows, index rows, and
KNOWLEDGE.md diffs are ordinary text changes in git. The sync log
(`~/Library/Logs/prosaic/sync-<matter>.log`) records what ran and
what it was given.

**Privilege awareness.** The prompt requires marking attorney-client
threads PRIVILEGED in catalogs. This is a labeling convention for the
humans working the file — it is not access control, and nothing in
prosaic transmits matter content anywhere except to the AI harness
you configured.

**Hard limits.** The triage agent never files, serves, sends, or
signs anything; never edits pleading sources during triage; and never
deletes anything except a staged duplicate whose content-identical
twin is already in place.

## Reading every page

`python3 triage/read_coverage.py <pdf...>` prints one line per file and
names every page that needs OCR or eyes; `--text <pdf>` emits the whole
document with `[[[ page k of N ]]]` markers and a closing page count.
The classes, and the failure each one names:

| class | meaning | what to do |
|---|---|---|
| `text` | enough extractable text, no large embedded raster | read it |
| `sparse` | a little text — a caption band on a scan, a form's filled overlay | OCR or look |
| `image-only` | no text, drawn content present: a scan | OCR (`ocr_supplement.py`) or rasterize and look |
| `blank` | nothing extractable and nothing drawn | genuinely empty |
| `image-bodied` | text present, but a raster covers much of the page: an email export carrying a screenshot, a declaration with a photographed exhibit | extract the image and look at it; the header alone is not the read |
| `garbled` | plenty of text and no common English word in it: the embedded font's encoding is nonstandard, so the page renders perfectly and extracts as nonsense | rasterize and read, or `ocrmypdf --force-ocr` into a new file |

`image-bodied` is the quietest miss: extraction succeeds, nothing looks
wrong, and the content is never read. `garbled` is the one a careful
reader still misses, and it over-flags on purpose — a page of pure
labels and numbers (a tax form's summary page, a statement's
transaction grid, an ID card) trips it and is fine — so it means "look
at this page," not "this page is broken." An `_ocr.pdf` is image-bodied
by construction; there the OCR text is the read.

The rules that follow from the classes, and the extraction checklist a
catalog row must satisfy, are the `triage-inbox` skill. The prompt
template (`triage/prompts/sync_triage.md`) requires the same read of
every headless session.

## Tuning

- Per-connector handling lives in `triage/prompts/sync_triage.md`.
- Matter-wide behavior lives in the matter's `AGENTS.md`.
- If you add a connector whose output needs special handling, add a
  section to the prompt template; otherwise the generic
  "treat as inbox material" clause covers it.

## Using other harnesses

The seam is narrow by design: the orchestrator shells out to one CLI
with one prompt and a working directory. Any agent harness that can
(a) run headless with file-editing tools scoped to a directory and
(b) honor an instruction file in that directory could be substituted
by editing the `TRIAGE` block of `sync/matter_sync.sh`. An agent CLI is
what this system is tested with.

## Text coverage: every document searchable, provably

```
sc text audit .              # what is and is not searchable, and why
sc text ensure .             # OCR what lacks text; write page-marked .txt sidecars
sc text ensure . --dry-run   # show what would be repaired
sc find "<term>" --ensure    # search; exit 2 if anything is still unsearchable
```

`sc text audit` classifies every PDF, image, DOCX and audio file under
the matter. A PDF counts as searchable only when a sidecar written by
the tool covers every page; an `_ocr.pdf` sibling alone does not, since
ripgrep cannot read a PDF. `ensure` repairs mechanically: `ocrmypdf
--skip-text` for pages with no text layer, `--force-ocr --pages` for
pages whose text is useless (a screenshot with a header, a garbled
font), then a `.txt` dump of the best source with a header

```
[[[ prosaic text sidecar ]]]
original: scan.pdf
source: scan_ocr.pdf
pages: 4
tool: pymupdf 1.27; ocr: ocrmypdf --skip-text
generated: 2026-09-06T21:40:12
MACHINE TEXT --- VERIFY AGAINST THE DOCUMENT BEFORE CITING IN ANY FILING
```

and `[[[ page k of N ]]]` markers so a hit names its page. Images get
`<stem>.ocr.txt` through tesseract; a human transcription is a `.txt`
beside the image and is never overwritten. Audio is only reported:
transcription is the local pipeline in `stt.md`.

The sync runs `ensure` on every pass, so the agent's triage prompt can
assume sidecars exist. `sc brief` prints the coverage line at every
session start. Handwriting is the remaining weak spot; a review
interface for correcting handwritten regions is planned.
