# Assembling a deployment

`git clone prosaic` gives you the **engine**. It does not give you a
working setup for a matter, and the gap is invisible from the outside: a
fresh clone carries no form modules and no deployment glue, so the first
build of a family-law filing fails — or, worse, succeeds with labels
silently missing and the front-matter guard silently disabled.

The [deploy](../skills/deploy/SKILL.md) skill is the procedure. This file
is why it is shaped that way.

## Three repositories, three layers

| repo | carries | mounts at |
|---|---|---|
| `prosaic` | the engine, general-civil forms | the deployment root |
| `family-law-forms` (private) | FL-series descriptors and blanks | `modules/family-law-forms` (submodule) |
| `slopcannon-local` (private) | `front_matter_keys.yaml`, workspace contract templates, connector glue | `local/` (gitignored) |

Discovery precedence is `local/` → `modules/` → built-in
([ADR-0034](../design/adr/0034-module-repos-as-submodules.md),
[ADR-0032](../design/adr/0032-local-modules.md)). A missing layer never
announces itself; it just means a form or a key is not found, which looks
identical to a form or key that was never asked for.

## The deployment path is permanent

`sc init` symlinks a matter's `Makefile` to
`<deployment>/pleading/Makefile`. Every matter therefore points at the
deployment by absolute path, and moving the deployment later breaks all
of them at once. Choose the location before cloning.

## Why verification is a step and not a formality

Every failure in this procedure is silent. A missing submodule looks like
a form nobody registered. A missing `local/` looks like a workspace with
no shared conventions — which is indistinguishable, from inside a matter,
from a workspace whose conventions happen not to apply.

That last one is the dangerous one, and it is worth being precise about
what depends on `local/`, because the obvious guess is wrong.
`local/pleading/front_matter_keys.yaml` *merges into* the recognized-key
set rather than providing it (`recognized_front_matter_keys()` reads the
base schema and the overlay), so without `local/` the
`front-matter key X is not read by anything` warning still fires. As of
August 2026 the overlay contributes exactly one key, so its absence
costs almost nothing there.

What actually breaks is the workspace contract:
`local/templates/workspace/AGENTS.md` is the symlink target that puts the
dash rules, NOTREAL discipline, triage rules and change authority in
force across every matter. Without `local/`, that symlink dangles, and a
matter builds perfectly while none of those rules load.

So the skill checks that each layer *resolves* — a form from the module
layer, a readable contract from the local layer — rather than ending at
"the commands ran".

## Where the deployment itself should live

Today a deployment is a `prosaic` clone whose `origin` is prosaic. It is
therefore permanently divergent from its own remote: generic development
happens in a separate prosaic checkout and lands in the deployment by
patch-replay (cherry-pick from a local fetch — the two histories mirror
the same changes under different SHAs, so a plain merge is wrong).

That arrangement works for code, but it leaves the deployment's *own*
wiring homeless. `.gitmodules` — the file that mounts
`family-law-forms` — is tracked in the deployment and pushed nowhere,
because pushing it to prosaic would make the general engine carry a
family-law mount. As of August 25, 2026 it exists in exactly one
machine's working copy.

The consequence is concrete: a new operator cannot reproduce a deployment
from remotes alone, and the skill has to say `git submodule add` where it
should be able to say `git submodule update --init`.

The fix is for the deployment to have a remote of its own — a
`slopcannon` repository holding `.gitmodules`, the submodule pin, and
nothing else that prosaic should not see. Until then, treat step 2 of the
skill as hand-assembly and expect to repeat it on every new machine.
