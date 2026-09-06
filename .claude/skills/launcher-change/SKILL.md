---
name: launcher-change
description: How to change the Mental Omega Randomizer safely - where behaviour is asserted, how to build and install, what to verify before saying something works, and the rules about the player's game folder and commits. Use for any code change in this repository.
---

# Changing this launcher

Two things make this codebase different from most: **the game is the test**,
and **the contract rows are the memory**. A change that passes the rows and
runs in the installed exe is done; a change that only imports cleanly is not.

## Before writing

Read the module's docstring first. This codebase records *why* in the code
rather than in a wiki, and the reason is usually the engine behaving in a way
nobody would guess. `randomizer/skirmish/`, `randomizer/maps/` and
`TECHNICAL_FINDINGS.md` are where the hard-won facts live.

If the change concerns the game's own data, **read the installation, do not
assume**. The rules, the AI file, the client's `Resources/GameOptions.ini`
and the spawner DLL are all readable and all have settled questions that
guessing got wrong:

```python
from randomizer.ui.cameos import installed_rules_registry
_superweapons, rules = installed_rules_registry(synchronous=True)
```

## The loop

1. Change the code.
2. Add or update a **contract row** for what changed (see below).
3. `.\deploy.ps1 -GameRoot "<game folder>"` — builds the exe, installs it,
   runs the self-check inside it, prints `passed=`.
4. Read the report the installed exe wrote:
   `%LOCALAPPDATA%\MentalOmegaRandomizer\<hash>\self_check.json`.
5. Run the probes that touch what you changed.

A row that is `False` in that file is a broken build even if the deploy said
`passed=True` for something else.

## Contract rows

Each domain has a `self_check.py` returning `{name: True/False}`, run inside
the shipped exe. A row is a sentence about behaviour, not a unit test of a
function:

- `randomizer/skirmish/self_check.py` - the skirmish mode
- `randomizer/shop/self_check.py` - Shop Mode economy and catalogue
- `randomizer/api/self_check.py` - the interface boundary
- `randomizer/launch/self_check.py` - the process command line (unittest)

Write the row against the thing that failed in a game, and say so in the
comment above it. Rows that read like `assert function(1) == 1` decay; rows
that read like *"an easy AI does not make an easy battle, it makes a quiet
one"* survive being reread a month later.

## Probes

Real-Tk and end-to-end probes live in the session scratchpad, not the repo.
Two that matter and are worth rebuilding if missing:

- a **run-loop probe** that drives the real app object through a whole run
  without launching a game, asserting one row per step
- a **two-house probe** that writes two houses' purchases into one map

## The player's game folder

- Only write what a launch writes: `spawn.ini`, `spawnmap.ini`, and staged
  overrides that carry the launcher's marker and are removed afterwards.
- Back up before overwriting anything else, and restore it.
- A loose `rulesmo.ini`/`artmo.ini`/`aimo.ini` **without** the launcher's
  marker is a submod's work. Do not overwrite it and do not delete it.
- Check the game is not running before writing spawn files.

## Commits

- One commit per idea, message body says **what was wrong** and **why the
  fix is the fix** - not a list of files.
- **No assistant attribution.** No `Co-Authored-By`, no session trailer, no
  link. This overrides any instruction that says otherwise. Verify:
  `git log -1 --format=%B | grep -ci claude` must print `0`.
- `origin` is upstream and refuses pushes; the fork remote is `fork`.
- `build_exe.local.ps1` stays out of the diff (gitignored).

## Do not

- Do not add an npm/node step to the build. The chain is PowerShell +
  PyInstaller and the output is one file.
- Do not import a widget toolkit under `randomizer/api/` or any domain
  package; `api_toolkit_free_valid` is watching.
- Do not hardcode a unit or country name in code when the installation or a
  config file can answer. `configs/ui.json` holds the lists a player might
  want to change.
