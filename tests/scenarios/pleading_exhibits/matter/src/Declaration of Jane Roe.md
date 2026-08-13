---
filer_name: "Jane Roe"
filer_address_lines:
  - "123 Main Street"
  - "Springfield, CA 90000"
filer_phone: "(555) 555-0100"
filer_email: "jane.roe@example.com"
filer_role: "Respondent, In Pro Per"

court_name: "SUPERIOR COURT OF THE STATE OF CALIFORNIA"
court_county: "COUNTY OF EXAMPLE"

petitioner: "JOHN SMITH"
respondent: "JANE ROE"
case_number: "24CV00000"
paper_title: "DECLARATION OF JANE ROE IN SUPPORT OF MOTION TO COMPEL"
paper_subtitle:
  sealed: "CONDITIONALLY UNDER SEAL"
  public: "PUBLIC REDACTED VERSION"

redactions:
  "Wilhelmina Quixote": "W.Q."
  "Wilhelmina's": "W.Q.'s"

exhibits:
  - shortname: "smith_email"
    title: "January 15, 2026 Email from John Smith"
    path: "smith_email.pdf"
    pages: "2-3"
  - shortname: "roe_texts"
    title: "Screenshot of Text Messages Between the Parties"
    path: "roe_texts.png"
  - shortname: "medical_summary"
    title: "Medical Summary Prepared by Treating Physician"
    path: "medical_summary.pdf"
    public_disclosure: omitted
  - shortname: "intake_form"
    title: "Counseling Intake Form Signed by the Parties"
    path: "intake_form.pdf"
    public_disclosure: redacted
  - shortname: "therapy_notes"
    title: "Session Notes Lodged with the Court"
    sealed: true

notreal: "SCENARIO FIXTURE — fictional test matter shipped with prosaic"
---

I, Jane Roe, declare as follows:

1. I am the Respondent in this matter. Attached as \exhibit{smith_email}
is a true and correct copy of the relevant pages of the January 15,
2026 email---the schedule proposal is discussed there.

2. Nonparty witness \redact{Wilhelmina Quixote} began treatment in
January 2026. \redact{Wilhelmina's} counselor confirmed the intake in
writing; the signed intake paperwork is attached as
\exhibit{intake_form}.

3. Attached as \exhibit{roe_texts} is a true and correct screenshot of
the parties' text messages covering January 23--March 3, 2026. The
messages corroborate \exhibit{smith_email}.

4. The treating physician's summary, attached as
\exhibit{medical_summary}, describes
\redact{QQSEALED the diagnosed condition in clinical detail}{[medical
information redacted]}{C7: third-party medical privacy; sentinel
JUSTIF-99}.

5. The session notes, \exhibit{therapy_notes}, are lodged
conditionally under seal. \highlight{HIGHLIGHT-SENTINEL-77 this
sentence was added by the drafting assistant for counsel's review.}

I declare under penalty of perjury under the laws of the State of
California that the foregoing is true and correct.

\signblock{decl}{JANE ROE}{Springfield, California}
