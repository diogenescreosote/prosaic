# 0013 — System dependencies declared in a manifest; the image is built from it

**Status:** accepted (2026-08)

## Context
`pleading/requirements.txt` and `connectors/package.json` declare the
language dependencies. The programs the pipeline actually shells out
to — ocrmypdf, tesseract, poppler's `pdftotext`, a browser — existed
only as a sentence in `docs/technical-overview.md`, and that sentence
was already wrong: it never mentioned `pdftotext`, which a portal
connector needs for every sidecar it writes. A dependency you discover
from a stack trace is a dependency nobody declared. The polyglot split
(ADR-0002) makes it worse, since a system binary belongs to neither
package file.

## Decision
`system-dependencies.yaml` names every binary the code invokes: what
breaks without it, its call sites, whether it is required, which
platforms it applies to, its package under apt and Homebrew, and
whether the container installs it. `sc deps` probes the list and
reports what is missing with the right install command for the host;
`sc deps --format apt` emits the package list the Dockerfile installs,
so the image is the manifest resolved rather than a second copy of it.
`tests/test_system_dependencies.py` checks both directions — a
subprocess call naming a program not in the manifest fails, and so
does a manifest entry no longer referenced anywhere — and refuses a
hardcoded `apt-get install` line in the Dockerfile outside the
bootstrap layer that reads the manifest at all.

## Consequences
The container is where the dependency set is proven rather than
asserted, and it paid immediately. The first build failed at `npm ci`,
because Debian packages `npm` separately from `nodejs` while every
other channel bundles them. Then the suite failed inside the image
with "cryptography>=3.1 is required for AES algorithm": the Judicial
Council form PDFs are encrypted, pypdf needs its `crypto` extra to
read them, and nothing declared it — on a developer's machine
`cryptography` arrives transitively through ocrmypdf's pdfminer, so
form filling had always appeared to work. Both are the class of error
prose cannot catch and a clean build can. With them fixed, the
component tests pass in the container exactly as on macOS and an
envelope built inside it is byte-identical to the same envelope built
on the host. Adding a subprocess call now means adding a manifest
entry — enforced, not requested.

What the image deliberately omits is as declared as what it contains:
`in_container: false` on the transcription tools, because a Linux
container on macOS runs in a VM with no access to Metal, and shipping
the speech stack there would produce a silently worse transcript of
privileged audio; and on the macOS Keychain, since ADR-0012's `env`
backend is what a container uses. On Linux the image is the deployment
artifact; on macOS it is for development and CI, which is a real limit
and is stated in the Dockerfile rather than discovered.

Costs: a third dependency file to keep current, and a manifest that
sees only literal program names — a call assembled from a variable is
invisible to the check. The realistic mistake is a hardcoded name, so
the hole is accepted and written down. Docker also remains a
prerequisite, which ROADMAP Phase 8 treats as temporary; this ADR does
not make it permanent.
Alternatives: a plain Dockerfile with the packages written into it
(rejected — it declares them for the container and leaves the macOS
user on prose, and there would be two lists); a `brew bundle` Brewfile
plus an apt list (rejected — two copies to keep in agreement, which is
the arrangement ADR-0011 refused); probing at run time only, with no
manifest (rejected — it tells you what is missing without telling
anyone what should be there).
