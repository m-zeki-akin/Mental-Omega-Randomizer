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

- **Unit-level upgrades for the AI.** The ally and the enemies buy nothing
  that reaches a battle yet. An AI builds what its task forces name and
  those name the original unit, so each bought unit needs its task forces,
  team types and AI triggers copied for that house, written into a staged
  `aimo.ini`. Measured on the installed AI file: 697 task forces over 212
  units, about 5 task forces, 6 teams and 10 triggers per unit; 945 of the
  1090 trigger conditions look at a building, so cloning units does not
  disturb them, and every script argument is numeric, so scripts are shared
  rather than copied. Two houses' clones must not collide in
  `TYPE_LIST_KEY_START` or in the ID prefix.

- **Enemies that grow with the tier.** Once the AI channel exists, a tier's
  enemy strength is a purchase list generated for the enemy houses and put
  through the same copies. Until then the tier only changes how many
  enemies there are and how hard the AI plays.

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
