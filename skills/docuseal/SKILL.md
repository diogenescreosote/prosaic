---
name: docuseal
description: Send a document for e-signature via DocuSeal, poll until signed, and bring the signed PDF and audit log back into the matter. Use when a document needs real-world signatures from people who will not install anything, or when a pending submission needs checking or collecting.
---

# E-signature round trip

DocuSeal handles delivery and capture (`specs/docuseal.md`, ADR-0023);
you handle the matter's side of the record. The API key is already
configured (`DOCUSEAL_API_KEY`, or the Keychain item named by
matter.yaml's `connectors.docuseal.credential`) — you never see or
handle it.

## Before sending — the two human decisions

1. **May this document leave the machine?** `send` transmits it to
   the configured DocuSeal deployment (`DOCUSEAL_URL`; the hosted
   service unless the user self-hosts). Privileged or sealed
   material: ask first, and suggest self-hosting if the answer is no.
2. **Is the document final?** A sent document is out in the world.
   `notreal:` sources must never be sent; the user clears the marker
   first (their call, never yours).

Signature placement is automatic: prosaic builds write the field
geometry to `<pdf>.fields.json` (sent as API field areas; the PDF's
text layer stays clean), or embed classic `{{...}}` text tags when
the source says `esign: tags` — the mode the free web UI needs
(ADR-0027). Both `\signblock` bodies AND a `cover_sheet:` form's
signature/date lines flow into the sidecar, so a filled JC/local form
(FL-300, MC-040, FL-014, …) signs through DocuSeal with no
hand-placement. `--to` order is the document's signature order; field
roles are reconciled onto the roster at send, so a single-signer
roster attaches every field to the one signer without fuss. A PDF with
neither sidecar nor tags sends with a warning and the signer places
fields by hand. `esign: false` sources (wills, negotiable notes) are
wet-ink instruments — never send them at all.

For flows beyond send/status/fetch (templates, bulk sends, webhooks,
embedded signing), DocuSeal publishes official agent skills at
github.com/docusealco/docuseal-agent-skills — install them into your
harness with `npx skills add docusealco/docuseal-agent-skills`, or
read them there. The API contract prosaic depends on is pinned by
the `docuseal` SDK version in the lockfile, not by a vendored copy.
`DOCUSEAL_SERVER` and `DOCUSEAL_URL` both select the deployment.

## The loop

Declare the roster once in envelopes.yaml (signing order = the
document's signature-block order), then send by envelope name:

```
envelopes:
  note:
    sources: [Promissory Note.md]
    signers:
      - {name: Jane Roe, email: jane@example.com, note: Borrower}
      - {name: Sue Smith, email: sue@example.com, note: Lender}
```

```
<prosaic>/cli/sc docuseal send "out/note/Promissory Note.pdf" --envelope note
<prosaic>/cli/sc docuseal status <submission_id>     # exit 0 = completed
<prosaic>/cli/sc docuseal fetch <submission_id> --out inbox/
```

`--to "Name <email>"` (repeatable) covers ad-hoc sends. Either way
the send validates the roster size against the document's declared
fields (sidecar or tags) and refuses a mismatch. Judicial signature lines
(\signblock{judge}) are wet-ink spaces: never tagged, never part of
a roster, never e-signed.

**Several documents, one ceremony.** `send` takes MORE THAN ONE PDF:
they become one submission of several documents, signed in a single
session and fetched back as SEPARATE signed files — the case where a
clerk wants each document filed on its own. Build each `--final`, then:

```
<prosaic>/cli/sc docuseal send \
  "out/rfo/fl300.pdf" "out/rfo/declaration.pdf" "out/rfo/mpa.pdf" \
  --to "Andrew Cone <andrew@example.com>"
```

Roles are unified across all the documents (distinct field roles in
first-appearance order map onto the roster in order), so a bundle
signed by one person just works, and a two-signer bundle attaches each
party's fields correctly.

**The signed files name themselves.** `fetch` prints one
`SIGNED: <path>` line per document (path relative to the working
directory) and `AUDIT: <path>` for the certificate. Read those lines
to know exactly what to hand back, route, or re-file — never re-derive
the paths. Choose `--out` (e.g. `--out staging/<date>_signed`) so the
`SIGNED:` paths point where you want the files; a bare `fetch` writes
into the current directory.

- `send` writes `<pdf>.docuseal.json` beside the document — commit it
  (`config` or `docket` per the matter's conventions) so the
  submission survives the session.
- Signers sign in `--to` order (`Signer 1..N`).
- `fetch` refuses incomplete submissions; nothing half-signed can
  land looking like an original.
- **Fetching is automatic once the connector is on**: with
  `connectors: {docuseal: {}}` in matter.yaml, every sync polls the
  matter's receipts and pulls completed submissions into
  `inbox/docuseal/<id>/` for triage. Manual check anytime:
  `<prosaic>/cli/sc docuseal poll .` or `sc sync .`.

## After fetching

The signed PDF and audit log are received originals:

1. Route them through [triage-inbox](../triage-inbox/SKILL.md) —
   INDEX row, literate name, `docket` commit (the signing is a
   real-world event; `Received:` footer).
2. Attest them — [crypto-attest](../crypto-attest/SKILL.md) — and
   reissue the matter's manifest, so the signed document's integrity
   stops depending on DocuSeal's continued existence.

References: `specs/docuseal.md`, ADR-0023, ADR-0012/0031 (credentials).
