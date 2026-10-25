# Legal research sources

The workspace contract requires that every authority a draft relies on be
fetched in full from a primary source and combed before use (see
`templates/workspace/AGENTS.md`, "An authority is relied on only after its
full text is read"). This page lists the sources agents use and how to
reach them.

## Midpage (MCP)

[Midpage](https://midpage.ai) offers case-law search and full opinion
text through an MCP server. Register it once per machine, at user scope,
so every matter session can use it:

```bash
claude mcp add --transport http --scope user midpage https://app.midpage.ai/mcp/v4
```

The server needs an account. After adding it, run `/mcp` in Claude Code
and authenticate `midpage`; a session started before authentication
does not see its tools. What it does well:
- One `search` call returns every opinion in a multi-appeal case,
  with docket numbers, publication status and treatment counts.
- `analyzeCaseDocument` answers a targeted question about an opinion with
  verbatim, line-anchored quotes (deep links) and a `doesNotAddress` list.
- `analyzeLaw` does the same for statutes and regulations.

That makes it the fastest and cheapest way to find authority and to
extract what an opinion says on a point.

What it does not do: return the raw full text. Its answers are
model-selected passages, so they do not satisfy the full-text rule on
their own. For any authority a filing will rely on:
1. Fetch the full text (CourtListener storage, the court's site or the
   reporter).
2. Save Midpage's analysis beside it as the start of the comb note.
3. Read the rest yourself: footnotes, dissents and later history are
   where a targeted answer stops.

A search result or summary is a lead, not the text.

## CourtListener

The search API (`https://www.courtlistener.com/api/rest/v4/search/?q=...&type=o`)
works without a token. Opinion pages and the opinions endpoint may
refuse scripted access, but each search result carries a `local_path`.
The archived slip-opinion PDF is at
`https://storage.courtlistener.com/<local_path>`. Slip pagination is not
reporter pagination; record which you are citing.

## Statutes and rules

- **California codes:** leginfo.legislature.ca.gov blocks plain HTTP
  clients with a Cloudflare challenge. A headless browser (the
  connectors' Puppeteer install) loads it. Read the
  `#codeLawSectionNoHead` element and save the text with its source URL
  and fetch date. The Legislative Counsel's bulk download
  (`downloads.leginfo.legislature.ca.gov/pubinfo_<year>.zip`) is the
  fallback.
- **Rules of court** come from courts.ca.gov, and **federal regulations**
  from eCFR.
