---
name: deploy
description: Assemble a working prosaic deployment from scratch - clone the engine, mount the form module and local glue, install dependencies, and verify by resolving each layer. Use when setting up on a new machine, onboarding someone, or when a matter cannot find forms, templates or the workspace contract.
---

# Assemble a deployment

`git clone prosaic` gives you the engine, not a working setup. A
deployment is three repos layered `local/` → `modules/` → built-in; a
missing layer is silent. Why it is shaped this way:
[docs/deploy.md](../../docs/deploy.md).

## 0. Access, or stop

```bash
git ls-remote https://github.com/diogenescreosote/family-law-forms.git >/dev/null
git ls-remote https://github.com/diogenescreosote/slopcannon-local.git >/dev/null
```

Either failing means the operator needs GitHub access granted. Say so and
stop — a half-deployment fails silently later.

## 1. Clone the engine

**The path is permanent**: `sc init` symlinks each matter's `Makefile`
into this directory, so moving it later breaks every matter.

```bash
git clone https://github.com/diogenescreosote/prosaic.git ~/lawyering/slopcannon
cd ~/lawyering/slopcannon
```

## 2. Mount the form module

```bash
git submodule add https://github.com/diogenescreosote/family-law-forms.git modules/family-law-forms
git submodule update --init --recursive
```

`add` rather than plain `update --init` because `.gitmodules` does not
arrive with the clone — see docs/deploy.md, "Where the deployment itself
should live". If `.gitmodules` is already present, `update --init` alone
suffices.

## 3. Clone the local glue

`local/` is gitignored, so it never arrives with the clone:

```bash
git clone https://github.com/diogenescreosote/slopcannon-local.git local
```

## 4. Dependencies

Three layers, one file each ([docs/install.md](../../docs/install.md)):

```bash
uv sync                              # Python
cd connectors && npm ci && cd ..     # Node
./cli/sc deps                        # system binaries; non-zero if any required one is missing
brew install $(./cli/sc deps --format brew)      # macOS
sudo apt install $(./cli/sc deps --format apt)   # Debian/Ubuntu
```

## 5. Put the workspace contract in force

Matters inherit dash rules, NOTREAL, triage and change authority from an
`AGENTS.md` **above** them. Without it, none of those rules load:

```bash
cd ~/lawyering
ln -s slopcannon/local/templates/workspace/AGENTS.md AGENTS.md
ln -s slopcannon/local/templates/workspace/CLAUDE.md CLAUDE.md
```

## 6. Verify — do not skip

Every failure above is silent, so prove each layer resolved:

```bash
./cli/sc init /tmp/deploy-check --git
./cli/sc form list | head          # engine layer: forms found at all?
./cli/sc form info fl300           # module layer: submodule checked out?
uv run pytest -q                   # the suite, in this deployment
rm -rf /tmp/deploy-check
```

| symptom | layer that did not take |
|---|---|
| `form list` shows only general-civil forms | step 2 — submodule absent |
| `form info fl300` unknown form | step 2 — submodule not checked out |
| `ls local/templates/workspace/AGENTS.md` missing, so step 5's symlink dangles | step 3 — `local/` not cloned |
| a matter's `make` cannot find the Makefile | step 1 — deployment moved after `sc init` |

A dangling `AGENTS.md` symlink is the quiet one: the matter builds, and
none of the shared conventions are in force. Check it resolves:

```bash
cat ~/lawyering/AGENTS.md >/dev/null && echo "contract in force"
```

## 7. Scaffold the matter

Now use [new-matter](../new-matter/SKILL.md). It assumes a working
deployment and appears to work without one.
