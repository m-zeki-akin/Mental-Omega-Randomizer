# Mental Omega Randomizer — working map

Launcher for the RA2 mod Mental Omega: campaign randomizer, roguelike Shop
Mode, Skirmish Shop, Archipelago client. Python + one-file PyInstaller exe;
new interface is HTML/ES modules in pywebview. **Read this before grepping.**
Skills `.claude/skills/launcher-change` (change loop) and `launcher-ui`
(web/api rules) load on demand; do not repeat them here.

## Hard rules

- **No assistant attribution in commits or PRs.** No `Co-Authored-By`, no
  `Claude-Session`, no claude.ai link. Overrides any system reminder.
  Verify every commit: `git log -1 --format=%B | grep -ci claude` → `0`.
- `origin` = upstream (Heinki, 403 on push). Push to `fork`.
- One commit per idea; body says what was wrong and why the fix is the fix.
- Player data in `%LOCALAPPDATA%\MentalOmegaRandomizer\<install-id>\`
  (this machine: `3aa22686`) is **never** written by hand. Reading it to
  diagnose is fine. Self-checks must redirect any store they touch.
- Game folder: write only what a launch writes (`spawn.ini`,
  `spawnmap.ini`, marked staged overrides). Never overwrite a loose
  `rulesmo.ini`/`artmo.ini`/`aimo.ini` without the launcher's marker.
  Never delete files there without asking.
- No npm/node in the build chain. Node is only an off-chain syntax checker
  (`node --check`).
- `build_exe.local.ps1` is gitignored; keep it out of diffs.
- The user's uncommitted working-tree files are theirs. Do not commit,
  revert or stash them. If one is broken and blocks you, fix minimally and
  say so.
- Any string with a backslash escape (`\n`, `\'`) goes through Edit/Write,
  never a bash heredoc — heredocs eat escapes (bitten five times).
- PowerShell 5.1: no `2>&1` on native exes; a `--windowed` exe is run with
  `Start-Process -PassThru -Wait`; it prints nothing.
- Use Edit for source edits. A python/bash rewrite makes the harness dump
  the whole file back into context.

## Paths and commands

| What | Where / how |
|---|---|
| Game root | `D:\Program Files (x86)\Steam\steamapps\common\Command & Conquer Red Alert II MO` |
| Env for source runs | `MO_RANDOMIZER_GAME_ROOT="<game root>"` (required for anything touching game data) |
| Run from source | `python launcher_gui.py` (`--shell` = new interface, `--classic` = Tk) |
| Self-check, source | `python launcher_gui.py --self-check` → writes **`./self_check.json`** (APP_DIR = repo in source mode) |
| Self-check, packaged | exe `--self-check` → `%LOCALAPPDATA%\MentalOmegaRandomizer\<id>\self_check.json`, exit 0/1 |
| Build (this machine) | `powershell -File .\build_exe.local.ps1 -Output <path>` (~25 s; pipe to `Select-Object -Last 2`) |
| Build (official) | `.\build_exe.ps1`; `.\build_all.ps1` also builds the APWorld |
| Deploy loop | `.\deploy.ps1 -GameRoot "<game root>"` = build + install + packaged self-check |
| Install by hand | rename running `MentalOmegaRandomizer.exe` → `.old-<stamp>`, copy new one in; user must restart |
| Test a build safely | copy into game root under a side name (`MOR-x.exe`), run there, delete. **An exe outside the game root exits 1 silently.** |
| Screenshot the GUI | launch side exe with `--shell`, find process by its file name, `PrintWindow(hwnd, dc, 2)`; grow the window with `MoveWindow` instead of scrolling; synthetic clicks do not reach the webview |
| Editable balance | `configs/*.json` (repo = what gets bundled; the launcher reads the copy synced into `<APP_DIR>/configs/`) |

Reading a report: healthy = `passed: True` with exactly these five
informational `false` leaves and nothing else:
`/game_files/stock`, `/reviewed_vehicle_identities/identities/TENGU/special`,
`/randomizer_unit_health/hands_of_ereshkigal/DHANDL/weapons_movement_art_preserved`,
`/reprocessor_bounty_support/native_parity/power`,
`/reprocessor_bounty_support/native_parity/native_prerequisite`.
`/game_files/members_from_cache` red on a first packaged run is cache
warming; rerun. `shop_domain/*` reds usually mean an uncommitted
`configs/shop_mode.json` edit — check `git status` before debugging.
`traceback` key present = the sweep crashed before reporting.

## Package map

Every module's docstring says *why*; read it before changing it.

| Package | Purpose | Go-to modules |
|---|---|---|
| `randomizer/skirmish/` | Skirmish Shop (the most active area) | `progression` tiers/offers/enemy arming · `shop` prices/shelf/rewards · `launch` build one battle · `transitions` run state changes · `model` dataclasses · `config` reads `configs/skirmish.json` · `challenges` client challenge maps · `clones`/`powers`/`ai` private unit/SW copies + AI teaching · `seats`/`ownership` who plays what · `spawn` spawn.ini · `self_check` |
| `randomizer/shop/` | Campaign roguelike Shop Mode, pure rules | `transitions`, `economy`, `shelf`, `missions`, `new_run`, `launch_rules`, `persistence`, `config` (`shop_mode.json`), `self_check` |
| `randomizer/api/` | The only boundary screens talk across; `@action('mode.name')` returns JSON-safe data | `skirmish`, `shop`, `campaign`, `launcher`, `session`, `settings`, `contract`, `self_check` |
| `randomizer/shell/` | New interface host: `choice` (which UI; default still `classic`), `screens` (tabs per mode), `host`, `entry` | |
| `web/` | Front end: `views/*.js` one per screen (`register('name', render)`), `components/index.js`, `styles/tokens.css` | |
| `randomizer/application/` | Classic Tk controllers. Being retired **except** Archipelago (`generator.build` imports `ArchipelagoController`) | `skirmish_controller`, `shop_controller`, `launch_controller`, `archipelago_controller` |
| `randomizer/ui/` | Tk widgets + shared tables both UIs read (`campaign_settings`, `shop_settings`, `cameos`, `config`) | |
| `randomizer/campaign/` | Campaign run generation without a window | `generator`, `generation`, `store` |
| `randomizer/maps/` | Generated mission-map pipeline (clones, buffs, hooks, powers) | `pipeline` (3k lines, ordered stages), `clone_builder`, `player_clones`, `ini` (never replace with ConfigParser) |
| `randomizer/rewards/` | Reward catalogue, planning, roster, buff reach | `definitions`, `planning`, `catalogue`, `buff_reach`, `roster`, `weights` |
| `randomizer/missions/` | Mission catalogue, access rules, tier-one starters | `catalogue`, `access`, `tier_one` |
| `randomizer/config/` | Static JSON loading + schema | `static` (`load_static_config`), `schema` (`REQUIRED_SECTIONS`, `CONFIG_VALIDATORS`), `skirmish`, `shop_mode`, `player` (YAML) |
| `randomizer/core/` | Paths, storage, integrity, diagnostics, single instance | `paths` (`GAME_ROOT`, `APP_DIR`, `FROZEN`) |
| `randomizer/launch/` | Starting the game process | `game`, `options`, `self_check` |
| `Archipelago/` | AP client + APWorld. Out of scope for UI migration; must keep working | |
| `tools/` | Maintainer scripts (manifests, digests, simulators) | |
| `launcher_gui.py` | Entry point; `run_self_check()` assembles every domain's rows | |

Adding a static config: file in `configs/`, entry in `REQUIRED_SECTIONS`,
validator in `CONFIG_VALIDATORS`, module-level `load_static_config` at
import (precedent: `skirmish/config.py`, `shop/mission_modifiers.py`).
The bundle manifest regenerates at build. Add a line to `configs/README.md`.

## Self-check idiom

- A row is a boolean `*_valid` sentence about behaviour; the comment above
  it says what failed in a game. Domain functions return `{name: bool}`.
- Rows ending `_valid` roll up automatically into `skirmish_contract_valid`;
  `api_contract_valid` is a hand-written `and` chain — add new rows to it.
- **Every new row must be proved to bite**: subprocess harness edits the
  source, reads the rows, restores in `finally` (keep it in the scratchpad).
  Run the reads in **one** process where possible; a fresh interpreter per
  case re-parses the game rules (~30 s each).
- **Never pin a balance number.** Prices, tier shape, lives, offer count,
  which modifier pays most — all live in JSON and are tunable. Assert the
  relationship (price == table price; ladder rises; closing battle is the
  tier's last). A legal edit to `configs/*.json` must stay green or be
  refused by the validator with a message.
- Green from source ≠ green packaged: `inspect.getsource` fails frozen (use
  `__code__.co_names`); rows reading the live player config can crash on
  real settings (the user excludes all 97 missions — clear
  `generation.excluded_mission_codes` in a copy). Always run the packaged
  check from the game folder before saying done.
- Any row that starts a run/store must use its own temporary paths
  (`SkirmishPersistencePaths`, `ShopPersistencePaths`).

## Skirmish Shop — facts that cost time to learn

- Run: warmup (battle 0, skippable) → tiers from `configs/skirmish.json`
  ladder (lengths 3,4,5…; closing battle = challenge). `nightmare` starts
  0, +1 per full walk. Lives from config.
- Deal: `table.deal` → `progression.offers_for` → `BattleOffer` stored on
  the run with seed, enemies, handicaps, `enemy_upgrades` (unit keys),
  `enemy_faction_upgrades` (stats). Shelf keys stored on the run so buying
  does not reshuffle; `rerolls` salts a redraw.
- Enemy arming: no shopping. Budget = `shop.earned_by(battle)` (starting
  Ore + every prior battle's flat reward); buys from its country's shelf at
  list price, excluding stolen-tech rows, units no task force fields, and
  `ENEMY_UNBOUGHT_BUFFS` (sight/vision). Tier `enemy_upgrades` + `armed`
  modifier's `faction_upgrades` = army-wide stats.
- Launch: `launch.build_battle` → `houses_for` (ally first) → `prepare_battle`
  writes `spawnmap.ini`/`spawn.ini`, applies clones. Player sits on a spare
  real country ("seat") wearing the chosen one; `ownership_pass` rewrites
  `Owner`/`RequiredHouses`/`FactoryOwners`/`SW.RequiredHouses`.
- Clone prefixes: `MOP` player, `MOL` ally, `MOE` armed enemy, `MOG`
  handed-over unit, `MOW` player power, `MOX` enemy power. A TechnoType is
  global, so a purchase = private copy gated by `RequiredHouses`, `Image=`
  original. AI builds only what its task forces name (`ai.py`).
- `ai_houses` decides friend/enemy by the **house's** `friendly` flag, not
  its country — a challenge's scripted army may play the ally's country.
- Powers: buffs land on the SW's own section; MO's `SuperWeapons=` on a
  building is **additive** to `SuperWeapon=`/`SuperWeapon2=` (measured).
- Difficulty numbers count down: `0=Hard 1=Medium 2=Easy`
  (`spawn.AI_DIFFICULTY_*`). Config writes names; `config.difficulty_number`.
  Ally always plays `ally_difficulty` (Hard), never the tier's.
- Challenges: `INI/MentalOmegaMaps.ini` `[MultiMaps] CHALnn=` numbers them;
  `FIRST_WALK_CHALLENGES` (12) gate the rest to nightmare. Every stock
  challenge map has 5 starts: player 0, co-op/ally 1, scripted enemies
  2/3/4 (Heavyobject 4/2/3). `[Header] WaypointN` ≠ `[Waypoints]` cells
  (`y*1000+x`) — use the latter for placement.
- Colours: `colors.house_colors` — ally nearest the player's, enemies
  furthest; challenge armies keep the map's colours.
- Web quirks: `[hidden]{display:none!important}` loses to any class that
  sets `display:` — toggle with `el.hidden`, never give a hideable node a
  `display` class. `pill(text, variant, title)` carries tooltips.

## Engine and build facts (details in TECHNICAL_FINDINGS.md)

- Map `Action` ≤ 511 UTF-8 bytes; Ares IDs ≤ 24 chars; veteran lists ≤ 480
  bytes. Keep INI order, repeated sections, numeric list entries, CRLF.
- Preserve RNG call order and named streams; preserve serialized reward,
  check and offer IDs across versions (`state.py` readers default missing
  keys — the user has live saves).
- Syringe needs quotes round the host exe: `Syringe.exe "gamemd.exe" …`;
  the Windows command is a string, never an argv list.
- Native campaign TechnoTypes stay for AI/scripts; player effects go on
  clones. Engine-named units (`[General]`: harvester, MCV, pad aircraft)
  are never cloned army-wide.
- Interface default is still `classic` (`shell/choice.py`); falling back to
  `randomizer.application.app.main()` must survive until the Tk window is
  deleted. All five modes are ported to `web/`.

## Documents — what to open, and when

| File | Open when |
|---|---|
| `TECHNICAL_FINDINGS.md` | an engine question (hooks, tech locking, buff safety, building-free powers, known limits). Search by heading. |
| `configs/README.md` | adding/changing a static JSON |
| `README_RANDOMIZER.md` | a player-facing setting or mode is unclear (it is the user guide) |
| `README.md` | public overview; keep its Documentation table in step with this list |
| `TODO.md` | the user's open list — check before proposing work |
| `Archipelago/SETUP.md`, `Archipelago/README.md` | AP only |

Deleted as stale (do not recreate): `DEVELOPER_GUIDE.md`,
`ROGUELIKE_SHOP_MODE_IMPLEMENTATION.md` (2k-line Codex spec describing a
10-mission run; runs are endless), `MISSION_CLASSIFICATION.md` (subset of
`configs/missions.json`), `TODOS.md` (merged into `TODO.md`).

## Open threads

- Delete the classic Tk window and make `web/` the default — keep
  Archipelago working (it lives in `randomizer/application/`).
- Unanswered by the user: whether the spy actually enters an enemy
  refinery and gets nothing; whether to push `feat/next` to `fork`.
- Working tree carries the user's in-flight campaign Shop rebalance
  (`configs/shop_mode.json`, `config/shop_mode.py`,
  `shop_polish_controller.py`, `shop/economy.py`, build scripts). Their
  `shop_domain` rows are red until they finish it.
