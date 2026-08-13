---
name: proof
description: Remote online notarization via Proof (proof.com) - send a document to be notarized over video by a commissioned online notary, poll until complete, fetch the notarized original into the matter. Use when a document needs a notarial act (acknowledgment or jurat) and the signer will not appear in person, or when a pending notarization needs checking.
---

# Remote online notarization (Proof)

Proof runs identity proofing, the video session, and the notarial
act (`specs/proof.md`, ADR-0030). You handle the matter's side.
Deliberately parallel to, not unified with, [docuseal](../docuseal/SKILL.md):
different service, different protocol.

## Before sending

1. The document must be built `--final` (the client refuses
   DRAFT-stamped PDFs without `--allow-draft`).
2. The document should end in a real notarial certificate block
   (`\acknowledgment{}` or `\jurat{}`) — the notary completes it.
3. RON must be lawful for this document and signer; a will is NEVER
   notarized into validity (witnesses, Prob. Code § 6110).

## The loop

```
<prosaic>/cli/sc proof send "out/trust/Trust.pdf" --to "Jane Roe <jane@example.com>"
<prosaic>/cli/sc proof status <transaction_id>    # exit 0 = complete
<prosaic>/cli/sc proof poll .                     # or let the connector do it
```

- `send` writes `<pdf>.proof.json` beside the document — commit it.
- With `connectors: {proof: {}}` in matter.yaml, every sync polls;
  completed notarizations land in `inbox/proof/<id>/` for triage,
  then attestation ([crypto-attest](../crypto-attest/SKILL.md)).
- Expired/canceled transactions go terminal in the receipt: report
  them, don't retry silently.

CAUTION: this client has not yet run against a live Proof account —
first real use targets the fairfax sandbox (`PROOF_URL`), with a
human watching.

References: `specs/proof.md`, ADR-0030, dev.proof.com.
