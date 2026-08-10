# Security, privacy, and professional-responsibility notes

prosaic handles the most sensitive material most people will ever
own: their litigation file. These are the commitments the design makes
and the ones only you can make.

## Where things live

- **Matter content stays on your disk.** No prosaic component
  transmits matter content anywhere, with one exception you configure
  deliberately: the AI triage harness (e.g. Claude Code), which
  processes matter text under whatever terms you have with that
  provider. If that's unacceptable for some material, keep it out of
  the triage path (triage only sees files connectors list as new) or
  disable triage entirely (it degrades gracefully to pull-and-index).
- **Audio never leaves the machine.** Transcription is local
  (whisper-cpp / WhisperX); see [stt.md](stt.md). Treat this rule as
  absolute — recordings are routinely privileged, statutorily
  protected, or both.
- **Credentials live in the OS keychain** (`security` generic
  passwords), read at runtime, never written to config files or logs.
  Gmail uses OAuth with a locally stored token
  (`~/.config/prosaic/gmail/`), scoped read-only.
- **Browser sessions** (portal cookies) persist in
  `~/.local/share/prosaic/portal-profiles/` — local disk,
  deliberately outside any cloud-synced folder.

## Things to keep out of git remotes

A matter directory as a *local* git repo is pure upside (history,
provenance, revertability). Pushing one to a remote is a decision:
you'd be putting privileged material on someone's server. If you do,
use a private repo, know your threat model, and mind court sealing
orders — a sealed exhibit in a pushed repo is a violation waiting to
be discovered. The repo/matter separation exists so the *code* can be
public while the *matters* never are.

## Privilege hygiene

- Catalogs mark attorney-client threads PRIVILEGED — a working label
  for you, not a technical control.
- **Be careful with third parties in the loop.** Forwarding privileged
  correspondence into other channels can waive privilege. prosaic
  won't do this on its own; the risk is what *you* wire together.
- Redactions produced by `pleading/redact_pdf.py` remove content
  rather than covering it, but you are responsible for verifying every
  redacted output before filing (the redaction log convention exists
  for this).

## Terms-of-service posture

Portal connectors automate *your own authenticated account* to
retrieve *your own case data*, at human-ish rates, for personal
noncommercial use. That is the intended and defensible use. Don't
point them at accounts that aren't yours, don't hammer servers, and
understand that a platform can still object; the graceful-failure
design means a blocked connector degrades to "do the export by hand
into inbox/", not data loss.

## The unauthorized-practice-of-law line

prosaic organizes facts and renders documents. It does not — and
its AI triage layer is explicitly instructed not to — decide what to
file, when, or against whom. If you are represented, this tool makes
you a better client, not a shadow lawyer; if you are pro se, treat
every AI-generated word as a draft you personally verify against
primary sources. Nothing in this repository is legal advice.

## Reporting

Security issues: open a private report to the maintainer (see
repository metadata) rather than a public issue, especially anything
touching credential handling or the triage prompt-injection surface
(a hostile document could try to steer the triage agent — the matter
CLAUDE.md's conservative-clerk rules and git review are the current
mitigations; treat triage diffs on adversarial material with extra
care).
