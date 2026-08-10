# (matter name)

prosaic matter directory. Layout:

```
inbox/            Drop zone for new material — unprocessed by definition
processed_files/  Canonical raw bytes of triaged inbox material
assets/           Evidence, by topic; assets/INDEX.md is authoritative
pleadings/        Filed/court documents, YYYY-MM-DD_description.pdf
discovery/        Records produced under subpoena/discovery
src/              Pleading .md sources (built via envelopes.yaml)
out/              Build output (generated)
memos/            Analysis and strategy memos
lawyer_drafts/    Drafts exchanged with counsel
unfiled/          Lodged-but-returned or otherwise unfiled documents
KNOWLEDGE.md      Durable case knowledge
TODO.md           Live open tasks
QUESTIONS.md      Open interview prompts
matter.yaml       Case + connector configuration
envelopes.yaml    Filing envelope definitions
```

Build: `make list`, `make <envelope>`. Sync: `sc sync .`
