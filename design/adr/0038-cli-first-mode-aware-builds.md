# ADR-0038: CLI-first document builds with mode-aware freshness

**Status:** Accepted (August 29, 2026)

## Context

The pleading build interface grew organically around a matter-local
`Makefile`: `make <envelope>`, with `FORCE=1`, `FINAL=1`, and
`VARIANT=...` translated into renderer flags. That interface has two
failure modes that are not theoretical.

First, Make's variable syntax makes dangerous distinctions easy to
miss. `make envelope FINAL=1`, `make envelope --final`, and
`sc build envelope --final` look alike to a user in a hurry but mean
three different things. Second, the build driver's freshness check
considered only file timestamps. A document rendered as a draft could
therefore be reported "up to date" to a later final build, leaving a
red `DRAFT—NOT SENT` banner on the artifact the user intended to send.

The system already has one CLI, `sc`. A second build language layered
underneath it adds no capability and creates exactly the wrong kind of
ambiguity around finality, signatures, and sealed variants.

## Decision

1. **`sc` is the only supported build interface.** Matters do not
   provide a Makefile, and the shared `pleading/Makefile` is removed.
   Envelope builds are `sc build <envelope>` (with `--all` and
   `--check-stale` covering what the Makefile's `all` and
   `check-stale` targets did); single-source builds are
   `sc build-doc <source>`.

2. **Build freshness is mode-aware, not merely timestamp-aware.** The
   build manifest records the source, dependencies, output paths, and
   render options that change the artifact: final/draft mode, public or
   sealed variant, signer, and signature date. An output is current only
   when all inputs and all requested options match. A draft PDF is never
   "up to date" for a `--final` request.

3. **A single-document build derives its output location from the
   envelope that owns the source.** `sc build-doc src/foo.md` builds the
   PDF and, when the envelope entry says `docx: true`, the DOCX in the
   same `out/<envelope>/` location as an envelope build. A source that
   appears in no envelope, or in more than one, is an error rather than a
   guess.

4. **Final remains a per-invocation act.** ADR-0015 is unchanged: a
   source carrying `notreal:` cannot be finalized, and no manifest entry
   or remembered option can make it so. The manifest records what was
   requested; it never grants finality.

5. **No compatibility Make target.** The old interface is removed rather
   than aliased. A deprecated alias would preserve the ambiguous command
   language this decision exists to eliminate. Documentation and
   templates point directly at `sc`.

## Consequences

- Users can build exactly one document without rebuilding unrelated
  papers in its envelope: `sc build-doc src/foo.md --final`.
- Changing only render options correctly triggers a rebuild even when no
  source file's mtime changed.
- The manifest is build state, not evidence. It is disposable and lives
  under `out/`; deleting it causes a clean rebuild, not data loss.
- Existing envelope configuration remains authoritative. `build-doc`
  does not introduce a second way to specify outputs, variants, or DOCX
  production.
- ADR-0024 drew the line between judgment work (flows) and build work
  ("stays in Make"). The line stands; only the name on the build side
  changes: build work stays in the build driver, reached through
  `sc build`, and a flow's deterministic steps call `sc`, not `make`.
- Removal of Make is intentionally abrupt. The cost is updating muscle
  memory; the benefit is that there is one documented command surface.
