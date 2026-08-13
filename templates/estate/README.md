# Estate pack

Markdown templates for a small, self-maintained California estate
plan, rendered by the pleading pipeline (`doctype: document`), with
a cryptographic protocol that lets the documents be verified years
later against a key anchored in their own executed paper
(ADR-0022, ADR-0025).

> **Not legal advice.** These templates are one layperson-shaped
> starting point, written to be short enough to actually read.
> Statutes are cited so you can check them; two templates
> deliberately defer to statutory form text (§ 4401, § 4701) rather
> than restate it. If your situation involves a taxable estate,
> blended families, a business, or anything contested: lawyer.

| File | What it is |
|---|---|
| `will.md` | Pour-over will: executor, guardianship, no-contest, the Anchored Key, § 6110 witness attestation |
| `living-trust.md` | Revocable living trust: successor trustees, incapacity mechanism, per-stirpes shares, the full crypto protocol article |
| `certification-of-trust.md` | § 18100.5 certification — what banks actually want |
| `durable-power-of-attorney.md` | § 4401 statutory-form finances POA (defer to statute for mandatory text) |
| `advance-health-care-directive.md` | § 4701-shaped health care directive (defer to statute for witness declarations) |
| `KEY-PROTOCOL.md` | The verification story, written for the person checking a document later |
| `EXECUTION.md` | Signing-ceremony checklists, and the crypto steps after |
| `assets/anchor-key.asc` | EXAMPLE key — replace with your own before anything is real |

## Use

Work inside a matter (`sc init`), copy the templates into `src/`,
and build with the ordinary envelope machinery. Every template
carries `notreal:` and stamps TEMPLATE on every page until you
remove it — which you do only for the version being executed.

The design decisions the crypto articles implement — why a
rebuttable presumption rather than "conclusive," why the trust gets
the full protocol and the will only an evidentiary hook, why a
signed manifest instead of hashes hard-coded across instruments —
are recorded in ADR-0022 and ADR-0025.
