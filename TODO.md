# TODO

Work that is decided but not built. Anything already true of the code
belongs in the code's own comments, not here.

## Skirmish Shop

- **Game speed as a difficulty dial.** A run is locked to the speed named by
  `locked_game_speed` in `configs/ui.json`, which is `1` — the value Mental
  Omega's own client calls "5 Faster" and its skirmish default. A slower
  game is an easier game: there is more time to react to everything the run
  throws at the player. So speed `2` ("4 Fast") belongs to an easier
  difficulty and not to the standard run, and the choice should come from
  the difficulty rather than from one setting shared by every difficulty.
  The speed already reaches both `spawn.ini` and the in-game options from
  one place (`LOCKED_GAME_SPEED_VALUE`), and `-SPEEDCONTROL` is no longer
  passed, so it cannot be moved mid-match; what is missing is the per
  difficulty value and the wiring from the difficulty to it.

- **Watch the ally play with what it bought.** The task force, team and
  trigger copies are written and the staged `aimo.ini` is in place, but no
  battle has been played with them. The design rests on one inference: that
  the engine picks autocreate teams by what a house can build, which is why
  a copy gated with `RequiredHouses` is its house's alone and why the
  original can be shut out. If that is wrong the ally stops building, the
  way the allied AI did when `[Sides]` was rewritten. The fallback is one
  flag -- `forbid_source=False` for AI houses, accepting a mixture of plain
  and upgraded units.

- **The ally's shelf still offers units its AI never fields.** Only 212 of
  the units in the catalogue appear in a task force; an upgrade on one of
  the others is Ore the ally will never see the benefit of.

- **Enemies that grow with the tier.** The channel now exists: a tier's
  enemy strength is a purchase list generated for the enemy houses and put
  through the same copies the ally's purchases go through. Until then the
  tier only changes how many enemies there are and how hard the AI plays.

- **Units the copy cannot cover.** A unit that deploys, converts or carries
  a payload names its other form by ID, and buildings are what prerequisites
  are written against, so neither is sold. 696 upgrades sit behind this.
  Covering them means copying the whole chain of linked forms, and for
  buildings, teaching prerequisites about the copy.

- **The seat's flag.** The player is seated on a spare country wearing the
  country they chose. The in-game diplomacy panel shows the seat's own flag,
  because the flag comes from the client's resources by country index rather
  than from the rules the map rewrites. Cosmetic, and it needs a client-side
  mapping to fix.
