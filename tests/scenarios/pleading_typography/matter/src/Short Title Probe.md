---
notreal: "SCENARIO FIXTURE — probes the undocumented short_title footer override"
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
paper_title: "DECLARATION OF JANE ROE RE FOOTER TITLE"
short_title: "TKSHORTPROBE FOOTER OVERRIDE"
---

The body of this probe is a single paragraph. The spec promises the
footer always carries the caption's paper title, so the string in the
undocumented short_title key should never reach the rendered page.
