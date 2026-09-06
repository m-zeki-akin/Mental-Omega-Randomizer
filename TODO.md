# TODO

Work that is decided but not built. Anything already true of the code
belongs in the code's own comments, not here.

## Skirmish Shop

- **Confirm the speed slider is inert.** The slider cannot be removed --
  it lives in the game executable -- so every one of its positions is given
  the locked speed's delay through Phobos's `[GlobalControls] CustomGS`
  table, written as map code. Moving it should now change nothing. Not yet
  watched in a battle. If `DefaultDelay` turns out not to be the step's
  frame delay, the other two keys Phobos reads for each step
  (`ChangeInterval`, `ChangeDelay`) are where to look next. Dropping
  `-SPEEDCONTROL` was tried first and changed nothing; the spawner's own
  `[Settings]` keys, read out of `cncnet5.dll`, hold nothing about speed.

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

- **An ally that fields only its upgraded units.** The copies are written
  and the staged `aimo.ini` is in place, but they are offered *alongside*
  the originals: a house cannot be stopped from autocreating a team, teams
  carry no owner, and shutting the original out of the house left an ally
  that built defences all match and attacked almost never. So the ally
  fields a mixture, and how much of it is upgraded is luck. Making it
  exclusive needs a lever this AI file does not have --
  `STAND_DOWN_ORIGINALS` and `forbid_source` are where it would go.

- **The ally's shelf still offers units its AI never fields.** Only 212 of
  the units in the catalogue appear in a task force; an upgrade on one of
  the others is Ore the ally will never see the benefit of.

- **Enemies that grow with the tier.** The channel now exists: a tier's
  enemy strength is a purchase list generated for the enemy houses and put
  through the same copies the ally's purchases go through. Until then the
  tier only changes how many enemies there are and how hard the AI plays.

- **Buying a sibling country's units with Ore.** The shelf is one country's
  army, which is right: the three Allied countries field different rosters
  and a United States run has no Hailstorm to improve. The next thing Ore
  should buy is the unit itself -- a Pacific Front unit bought into a United
  States run, after which its upgrades join that run's shelf like any other.
  Mental Omega gates these by building rather than by country: `ALLT2` is
  `GAMERC,GASCEA,GASCPF`, one tier two building per Allied country, and a
  unit like the Hailstorm names the building (`Prerequisite=ALLWEAP,GATECH,
  GASCPF`) rather than naming Pacific Front. So buying a unit means either
  granting its prerequisite building or copying the unit with the
  prerequisite rewritten -- the second keeps the enemy's tech tree intact
  and is the same copy machinery a purchase already uses. The other three
  sides are shaped differently and each needs reading: Soviet tier two is
  three different tech labs, and some tier two units still use
  `RequiredHouses` outright (the Armadillo is `Owner=USSR,Latin,Chinese`
  with `RequiredHouses=Chinese`); Epsilon uses plugs -- ChemPlug, GenePlug,
  PsychPlug, each `PowersUpBuilding` -- and Foehn uses expansions the same
  way, three tech buildings at tier two and an expansion on one of them to
  reach tier three.

- **Upgrades for buildings.** Cost, health, armour, production speed, an
  extra garrison slot, power (more from a plant, less drawn by a defence or
  a superweapon), a wider `Adjacent`, and a larger
  `SpyEffect.StolenMoneyAmount` -- that last one is not really a building
  stat, but it is written under a building so it lands here. Buildings are
  excluded from the shelf today because they are what prerequisites are
  written against: a copy of a barracks satisfies nothing the original
  satisfied, so the copy needs teaching into every prerequisite and generic
  group that named the original.

- **Upgrades for the MCV, and so for the Construction Yard.** Health, speed,
  production, cost. The MCV is the one unit a skirmish hands out before
  anything is built, so shutting the original out of a house has to keep
  working: `BaseUnit=AMCV,SMCV,PCV,FMCV` is how the engine picks one, and
  the copy has to be picked the same way. The Construction Yard it deploys
  into is a building, so this waits on the building work and on the linked
  forms.

- **What the AI file becomes once buildings are in.** Every building a house
  upgrades is another copy, and the player and the ally take different
  upgrade paths, so the same building can exist several times over in one
  battle. The AI's base building reads `[AI] BuildPower`, `BuildRefinery`,
  `BuildBarracks`, `BuildTech`, `BuildWeapons` and the base defence lists by
  building ID, and its triggers name teams that name task forces -- so
  copied buildings mean those lists and those triggers get copied per house
  as well, the way task forces already are. This is the largest piece of the
  three and should not start until buildings are sold at all.

- **Buildings the copy cannot cover.** A building is what prerequisites are
  written against, so a copy of one satisfies nothing the original
  satisfied and none are sold. Covering them means teaching every
  prerequisite and generic group about the copy. The linked forms are done:
  a unit that deploys is copied together with what it deploys into, and the
  copies name each other.

- **The seat's flag.** The player is seated on a spare country wearing the
  country they chose. The in-game diplomacy panel shows the seat's own flag,
  because the flag comes from the client's resources by country index rather
  than from the rules the map rewrites. Cosmetic, and it needs a client-side
  mapping to fix.

- **A battle the launcher was not there to see.** Which battle is being
  played is kept in memory. Close the launcher while a game is up -- not the
  game, the launcher -- and nothing records the outcome: no life is charged
  and the same offer can be fought again. It has always worked this way, but
  the rule it breaks is the mode's own, that leaving a battle counts as
  losing it. Writing the committed launch beside the run -- the run it
  belongs to, its battle, and where the game's log stood when it began --
  would let the next start finish it.
