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
court_street_address: "100 Court Street"
court_city_zip: "Example City, CA 90000"
court_branch: "Civil Division"

petitioner: "JOHN SMITH"
respondent: "JANE ROE"
caption_first_party_label: "Petitioner"
caption_second_party_label: "Respondent"
case_number: "24CV00000"
paper_title: "ATTACHMENT 3 TO DEPOSITION SUBPOENA FOR PRODUCTION OF BUSINESS RECORDS"

cover_sheet: subp010
# An attachment continues the form; the form already carried the
# caption. Without this the renderer prints the attorney block, court
# name and party caption as though this were a standalone pleading.
no_caption: true
forms:
  subp010:
    deponent: >-
      Custodian of Records, Example Bank, N.A., 500 Market Street,
      Example City, CA 90000, (555) 555-0199
    deposition_officer: "Example Records Service, Inc."
    production_date: "September 15, 2026"
    production_time: "10:00 a.m."
    production_location: "200 Commerce Way, Suite 300, Example City, CA 90000"
    method_mail_to_officer: true
  subp025:
    requesting_party: "JANE ROE, Respondent"
    production_date: "September 15, 2026"
    witness: >-
      Custodian of Records, Example Bank, N.A., 500 Market Street,
      Example City, CA 90000

consumer_notices:
  - consumer: "JOHN SMITH"
  - consumer: "MARY MAJOR"
    slug: mary_major
    witness: >-
      Custodian of Records, Example Employer, Inc., 900 Industrial Way,
      Example City, CA 90000

notreal: "SCENARIO FIXTURE — fictional test matter shipped with prosaic"
---

The records to be produced are:

1. All monthly account statements for any account held in the name of
JOHN SMITH, alone or jointly, for the period January 1, 2024 through
December 31, 2025.

2. All signature cards, account applications, and account-opening
documents for each such account.

3. All records of transfers between any such account and any account
held in the name of MARY MAJOR for the same period.
