# Decisions

Each entry: the decision, the alternatives, why, and what it costs.

## 1. The model never computes dates

**Decision.** The deadline engine is reachable from the agent layer only
through a typed `compute_deadline` tool that takes facts (a rule name, a
trigger date, a service method) and returns the engine's result. The
operator's system prompt says the same thing, but the prompt is redundant:
no tool exists whose input is a model-asserted date.

**Alternatives.** Let the model do date arithmetic and check it afterward;
or trust prompt instructions alone.

**Why.** A missed deadline is the one error class in this domain that
cannot be fixed by review the night before. Post-hoc checking still leaves
the checker deciding which of two dates to believe. Making the wrong path
structurally impossible is cheaper than making it unlikely.

**Cost.** Every new rule needs engine code, tests, and a tool-schema entry
before the model can use it. The model cannot answer deadline questions the
engine doesn't implement — by design, it must say so instead.

## 2. Court days and calendar days are distinct types

**Decision.** `CourtDays` and `CalendarDays` are separate frozen dataclasses,
and every function signature says which it takes.

**Alternatives.** Integers with parameter names or comments.

**Why.** California rules mix the units inside a single computation — CCP
§ 1005(b) measures notice in court days but extends it in calendar days for
mail service, and the § 1013 table extends some methods in calendar days
and others in court days. With integers, passing a 5 meant for calendar
days into a court-day walk type-checks fine and lands on a date wrong by a
weekend. With distinct types it doesn't compile.

**Cost.** Construction noise (`CourtDays(16)` instead of `16`) and two
nearly identical class definitions.

## 3. Provenance is tracked per fact, not per document

**Decision.** Values extracted from records are `Fact[T]` — the value plus
a provenance record naming the source document and page, or the user who
asserted it. Service dates, case numbers, party names, and docket dates are
facts; contact details and other user-maintained configuration are plain
fields.

**Alternatives.** Track provenance per document and assume everything
parsed from it inherits the citation; or skip provenance entirely.

**Why.** The values that carry provenance are the ones that flow into
filings and deadline computation, where "where did this date come from?" is
the question a reviewing human actually asks. Document-level provenance
can't answer it: one PDF yields many facts, extracted with different
confidence, and the wrong service date silently shifts every downstream
deadline. Fact-level provenance also marks unsourced values as exactly
that — asserted, to be confirmed.

**Cost.** Verbosity. Fixtures and constructors write
`Fact.from_document("26CV012345", document_id=..., page=1)` where a string
would do, and consumers write `.value`.

## 4. Form knowledge is a pack, not configuration

**Decision.** Each form is a Python module: a frozen context dataclass, a
typed `build_values` function, validation, and a docstring of the form's
quirks. A pack is a tuple of these behind a small registry.

**Alternatives.** A YAML/JSON mapping DSL from model paths to field names;
or template PDFs with positional text stamping.

**Why.** Real forms defeated the declarative version on contact: CM-010's
case-type on-states are irregular (`/17` inserted mid-column, `/44` at the
end), POS-010's mutually exclusive choices are independent checkboxes whose
exclusivity someone must enforce, MC-030's capacity boxes mix one checkbox
with a five-state radio group, and conditional logic (fictitious-name
service adds two fields on one page and two on another) is just code. A
mapping language grows conditionals until it is a worse programming
language. Python with types was already there.

**Cost.** Writing a pack requires a programmer, not just a spreadsheet of
field names. The interface documentation (FORM_PACKS.md) carries the weight
a schema would otherwise carry.

## 5. Fill official AcroForms; generate pleading paper from scratch

**Decision.** Where the Judicial Council publishes a fillable form, prosaic
fills the official blank, shipped unmodified in the pack. Pleading paper,
which has no official fillable artifact, is generated from scratch per
CRC 2.100–2.119.

**Alternatives.** Recreate the forms' appearance ourselves; or overlay text
on flattened scans.

**Why.** Clerks and opposing counsel receive the exact artifact they
expect, revision date and all, and a form revision is handled by swapping
the blank and re-verifying the mapping rather than re-typesetting. The
cost of the alternative is visible in this repo's own field-mapping notes:
the official files contain misspelled field names and stale tooltips —
recreating their layout pixel-perfectly would be strictly harder than
mapping them.

**Cost.** Dependence on the forms' internal field names, which are
unversioned implementation details; AES-encrypted blanks pull in a crypto
dependency; and the blanks add ~800KB to the repository.

## 6. The deadline engine is pure, and calendars are data with a hard edge

**Decision.** `prosaic/deadlines/` computation imports only the standard
library. Holiday calendars are packaged JSON with an explicit coverage
window; asking about a date outside the window raises
`CalendarCoverageError`.

**Alternatives.** Compute holidays from observance rules (third Monday of
January, Saturday-to-Friday shifts); default unknown years to
holiday-free.

**Why.** Purity is what makes the property-based suite meaningful — a
thousand Hypothesis cases run in milliseconds with no fixtures. Shipping
dates rather than rules means the data can be checked against what courts
actually publish, which is also the ground truth when a county deviates.
The hard coverage edge exists because the failure mode of the alternative
is a confidently computed, wrong deadline — the worst output this software
can produce.

**Cost.** Someone must append a year of holidays annually, and computations
near the coverage edge fail loudly even when every date involved is a plain
weekday.

## 7. The wordmark animates by default

**Decision.** The README shows the animated wordmark — a terminal cursor
blinking at 1.06s with a hard opacity step (SMIL `calcMode="discrete"`) —
with static variants committed alongside.

**Alternatives.** Static by default; or CSS animation.

**Why.** The blink is the identity: a prompt waiting for input, which is
what the tool is. SMIL is used because GitHub's markdown pipeline strips
embedded stylesheets but renders SMIL inside `<img>`. SMIL cannot honor
`prefers-reduced-motion`, which is a real accessibility trade: the honest
mitigations are keeping the mark small (~330px, one line of motion) and
shipping `wordmark-static*.svg` for any context that wants stillness. A
`<picture>` element can't switch on reduced-motion for the README, so the
default had to be chosen, and the animated mark was chosen knowingly.

**Cost.** Users with vestibular sensitivity see a blinking element on the
README. The glyphs are outlined paths, so the mark is also ~10KB instead
of a 300-byte `<text>` element (font fallback on systems without Courier
New would misplace the cursor otherwise).

## 8. Mail ingestion is IMAP, not a provider API

**Decision.** The mail connector speaks IMAP behind a two-method session
protocol; Gmail works via an app password.

**Alternatives.** The Gmail REST API with OAuth.

**Why.** The connector's actual logic — search, fetch, parse RFC 822,
extract PDF attachments, date them — is provider-neutral, and behind the
protocol it is fully tested with real message bytes and no network. The
OAuth alternative adds a heavy dependency, a token-refresh dance, and a
consent flow that cannot run in CI, all to reach the same messages a
15-line stdlib client reaches. A provider API connector remains a
straightforward addition behind the same `RecordSource` protocol if
someone needs threads or labels.

**Cost.** App passwords require the user to enable two-factor
authentication and generate a credential by hand, and IMAP exposes less
metadata than the API.

## 9. A model refusal stops the operator; nothing reroutes

**Decision.** When the model's safety layer declines a request, the
operator raises `OperatorRefusedError` to the human. There is no automatic
fallback to another model.

**Alternatives.** The API's server-side fallback parameter, which reruns a
declined request on a second model transparently.

**Why.** In most products a refusal is an availability problem to engineer
around. Here the user is a self-represented litigant and the requests are
about their own case; a refusal is information the human should see and
act on deliberately, not a signal to shop the same request to a more
permissive route. The operator is also a library — the embedding
application, which knows its context, is the right place for retry policy.

**Cost.** A false-positive refusal interrupts the session instead of being
absorbed, and the user has to rephrase or escalate themselves.
