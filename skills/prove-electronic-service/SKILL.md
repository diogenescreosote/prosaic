---
name: prove-electronic-service
description: Paper an electronic service with a POS-050/EFS-050 Proof of Electronic Service, using the canonical source name and path beside the served document. Use whenever a party or agent reports having e-served a document (by email or e-service platform) and the service needs a signable proof.
---

# Prove an electronic service (POS-050/EFS-050)

When someone e-serves a document — emails it to opposing counsel,
sends it through an e-service platform — the service gets papered on
Judicial Council form POS-050/EFS-050, registered here as form id
`efs050`. This skill is the process; the form's field semantics are in
`sc form info efs050`.

## What the law lets you assume

- **A party may electronically serve and declare.** The form's
  declaration is "I am at least 18 years old" — no not-a-party
  recital (contrast every mail-service form). CCP § 1010.6; CRC 2.251.
- A party represented by counsel who has appeared must generally
  accept electronic service where the court requires e-filing
  (CRC 2.251(c)(3)) — but whether THIS recipient must accept it is a
  question for the human, not this skill.

## Canonical name and path

The proof source lives **beside the served document's source, in the
same `src/` subdirectory**, named after it:

```
src/<dir>/<served_stem>.efs050.md          # one service of that document
src/<dir>/<served_stem>.efs050.<YYYY-MM-DD>.md   # re-service of the same document
```

Example: service of `src/change_of_address/mc040_berkeley_po_box.md`
is proven by `src/change_of_address/mc040_berkeley_po_box.efs050.md`.
Add the proof to the **same envelope** as the served document, right
after it, so the packet and its proof travel together and render to
`out/<envelope>/<served_stem>.efs050.pdf`.

## The source

`cover_sheet: efs050` + `cover_sheet_only: true`, standard caption
front matter, and a forms block. What each field wants:

- `efs050_documents` — the **exact title** of what was served, with
  its form number if it is a JC form.
- `efs050_served_name` / `efs050_served_on_behalf_of` /
  `efs050_served_eservice_address` — the item-3 block covers **one
  person served**; several e-addresses for the same attorney or
  office may be listed together in the address field, but a second
  *person* needs the POS-050(P) attachment (`persons_in_attachment`).
- `efs050_service_date` — the date the email/e-service actually went
  out, from the sender's own record, never assumed.
- `efs050_residence_address` — the declarant's actual **residence or
  business address**. Rule 2.251 contemplates the proof stating this
  SEPARATELY from the electronic-service address, and **a PO box is
  neither a residence nor a business address — refuse it**. If the
  declarant does not want their residence stated in a served document,
  the answer is a business address, never the mailbox.
- `efs050_declarant_eservice_address` — the declarant's own e-service
  address (this one is the email).
- `print_name` filled; `sig_date` and the signature always left for
  the declarant.

## The loop

1. **Verify the send happened — prerequisite, not optional.** In a
   matter whose Gmail connector watches the recipient's domain, run
   `sc sync .` (or the gmail connector alone) and find the sent
   message in `assets/gmail/`: confirm the date, every recipient
   address, and that the attachment line names the served document
   (the connector renders an "N attachments" line; it does not keep
   the files). The proof's facts — date, addresses, title — come from
   that pulled record, not from memory. If the connector does not
   cover the recipient, ask the human for the sent email itself
   (forward or export) and triage it before papering. **Never
   backfill a service date, and never paper a service you cannot see
   evidence of.**
2. Write the source at the canonical path; wire it into the served
   document's envelope.
3. `make <envelope>` and read stderr per the build-envelope skill.
4. Verify the render (open it): exact title, addresses, date; the
   signature/date lines blank.
5. The declarant signs **and dates** — the declaration date belongs
   to the signing step, never to the form data at rest; do not
   pre-fill `sig_date`. Whether the signed proof is then **filed** or
   **held** depends on the served document: a proof for a document
   being filed is filed with or right after it; a proof for a
   served-not-filed document (safe-harbor motions, discovery) is held
   in the matter's records until needed.
6. Matter-side record: a `docket` commit with a `Served:` footer
   naming the date and recipients, sourced to the human's statement
   or the sending record.
