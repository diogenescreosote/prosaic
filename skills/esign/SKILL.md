---
name: esign
description: Send a document for e-signature via DocuSeal, poll until signed, and bring the signed PDF and audit log back into the matter. Use when a document needs real-world signatures from people who will not install anything, or when a pending submission needs checking or collecting.
---

# E-signature round trip

DocuSeal handles delivery and capture (`specs/esign.md`, ADR-0023);
you handle the matter's side of the record. The API key is already
configured (`DOCUSEAL_API_KEY` or the Keychain) — you never see or
handle it.

## Before sending — the two human decisions

1. **May this document leave the machine?** `send` transmits it to
   the configured DocuSeal deployment (`DOCUSEAL_URL`; the hosted
   service unless the user self-hosts). Privileged or sealed
   material: ask first, and suggest self-hosting if the answer is no.
2. **Is the document final?** A sent document is out in the world.
   `notreal:` sources must never be sent; the user clears the marker
   first (their call, never yours).

Signature placement: the source should carry DocuSeal text tags where
signatures go — literal `{{Signature;role=Signer 1}}` text in the
rendered PDF becomes a signature field. No tags = a warning and
manual placement by the signer.

## The loop

```
<prosaic>/cli/sc esign send out/<envelope>/document.pdf \
    --to "Jane Roe <jane@example.com>" --to "John Smith <john@example.com>"
<prosaic>/cli/sc esign status <submission_id>     # exit 0 = completed
<prosaic>/cli/sc esign fetch <submission_id> --out inbox/
```

- `send` writes `<pdf>.esign.json` beside the document — commit it
  (`config` or `docket` per the matter's conventions) so the
  submission survives the session.
- Signers sign in `--to` order (`Signer 1..N`).
- `fetch` refuses incomplete submissions; nothing half-signed can
  land looking like an original.

## After fetching

The signed PDF and audit log are received originals:

1. Route them through [triage-inbox](../triage-inbox/SKILL.md) —
   INDEX row, literate name, `docket` commit (the signing is a
   real-world event; `Received:` footer).
2. Attest them — [crypto-attest](../crypto-attest/SKILL.md) — and
   reissue the matter's manifest, so the signed document's integrity
   stops depending on DocuSeal's continued existence.

References: `specs/esign.md`, ADR-0023, ADR-0012 (credentials).
