# Static Randomizer Configuration

These JSON files contain editable gameplay and presentation data previously
embedded in Python modules. Restart the launcher after changing a file.

`player/mental_omega_randomizer.yaml` is different: it is ignored local runtime
state containing next-seed and launcher choices. Source runs create it here so
all configuration is grouped under `configs/`. Packaged runs create the same
relative path under `%LOCALAPPDATA%/MentalOmegaRandomizer/<installation>/configs/player/`. Do not commit a
personal player YAML.

The two `Randomizer*.ini` files do not replace these documents. They say which
units get a player-owned copy and carry the handful of bodies no rules file
contains; every other clone body is built at load from the installed rules. JSON files define randomizer
policy, reward identity/display, mission exceptions, cross-faction roles,
stacking, compatibility aliases, and building-free power conversion. The main
intentional overlap is `rewards/unit_data.json`: roster/base-stat snapshots
could eventually be derived from static INI templates, but current reward
construction and old-save compatibility still consume its labels, categories,
role groups, linked identities, and special damage metadata. Remove or migrate
that overlap only with full reward-plan and 97-map parity coverage.

## Files

- `default_player_config.json`: fallback player, generation, launch, privacy,
  reward-weight, and future Archipelago settings used when active YAML keys are
  absent. `generation.reward_weights` stores bounded `0`–`100` main,
  unit-buff, and power-buff selection weights; absent legacy keys use `100`.
  `generation.starting_reward_count` and `starting_reward_types` control the
  separately seeded pre-mission unlock grant; allowed families are access,
  offensive powers, secondary powers, and aid powers. Buff-family IDs from
  legacy or portable settings are discarded; legacy configs default to zero.
  `generation.starting_unlock_rewards` stores portable canonical reward names
  manually selected in Advanced -> Starting Unlocks; only permanent content
  access/power rewards survive normalization, and legacy configs default empty.
  `generation.access_limits` optionally caps unique unit/building and power
  unlock identities across Starting Rewards and mission rewards. Its `units`
  and `powers` values are positive integers; `enabled` defaults to `false`, so
  absent legacy settings retain unrestricted planning. Shop Mode and Randomizer
  Arsenal ignore these caps.
- `missions.json`: mission build classifications, configurable mission reward
  classes/multipliers and per-mission overrides, optional-operation membership, helper/enemy house policy,
  production/power house exceptions, native identity exclusions, map-specific
  access rules, original mission-only MCV access, native-variant buff
  forwarding, and campaign starter families.
- `map_rules.json`: controlled technology locks, TechnoType registry mapping,
  and parser/engine safety limits used by generated maps.
- `factions.json`: Engineers, MCV/Construction Yard mapping, production
  buildings, amphibious transports, Chaos production, and tech
  ordering, plus default unlock owners and special-factory identities.
- `tier_one.json`: subfaction-specific land/air starter equivalents, faction
  naval-attack and anti-air ship equivalents, fixed faction Tier 1 defensive
  structures, Standard role markers, aircraft factories, and installed
  GenericPrerequisite aliases. `ground_roles` and `naval_roles` identify the
  separately faction-shuffled Chaos/Shop role groups; every naval-role entry
  must use production category `naval`.
- `shop_mode.json`: Shop Mode run length, mission offers and class rewards,
  stage difficulty weights, Ore/Gem unit prices, permanent upgrade
  definitions, reward exclusions, and launcher-only mission effects.
- `ui.json`: difficulties, game speeds, campaign/reward/progression choices,
  EVA announcer tags, reward-count messages, faction colors, and
  light/dark palettes.
- `rewards/unit_data.json`: unit and defense rosters, base stats, reviewed
  transport passenger/open-top baselines and behavior exclusions, weapon stats,
  cross-faction role-equivalence groups, linked land/water buff identities,
  buff targets, labels, hero limits, and
  special weapon damage fields.
- `rewards/unit_policy.json`: installed capabilities, reward exclusions,
  trainability/naval classification, always-available essentials, trainable
  defenses, alternative production facilities, linked land/water access
  identities, and unit-specific display wording.
- `rewards/special_buildings.json`: editable faction economy/special-building
  access rewards, including labels, native Construction Yards, tech levels,
  build limits, sidebar build category/priority, and whether repeatable +1
  capacity rewards are generated. Optional `granted_superweapon` names the
  power supplied by that structure; launch creates one private power copy and
  binds it to the isolated player building clone. Chaos translates these
  buildings to every faction Construction Yard.
- `rewards/buff_exceptions.json`: reviewed per-buff TechnoType exclusions.
- `rewards/power_buffs.json`: reviewed power-specific recharge, cost, area,
  damage, duration, delivered-payload, and reconnaissance-plane vision buff
  capabilities and stack tuning.
  Supported effects have no Randomizer-imposed stack ceiling.
  - `rewards/enemy_scaling.json`: reviewed hostile-AI CountryType armor,
    T1/T2/T3 unit and weapon bonuses, production-speed rewards, and support
    powers; per-stack tuning, positive engine clamps, allowed effect IDs, and
    hard per-effect caps. The base Randomizer assigns them beside normal
    reward slots without replacing player rewards. Archipelago exports the
    selected inventory as extra Trap items with matching extra locations.
    Player settings can narrow but never exceed the enabled bonuses' real
    combined capacity.
- `rewards/catalogue.json`: unit access items, faction access rules, buff type
  definitions, superweapon templates/rewards, support and aid-power definitions
  and mappings, access aliases, and retired reward compatibility entries.
- `rewards/tuning.json`: stack multipliers, per-category movement-speed
  ceilings, retry-assistance behavior, clone prefixes/production-field policy,
  reward count limits, and global-buff planning cadence. Display text,
  effective stack limits, and generated map values use the same data. Unit
  damage uses x1.15 per stack and caps at x6 total (+500%) on stack 13.
- `RandomizerUnits.ini`: which units get a `MORP*` player clone, and the
  registry slot each one occupies. 326 entries, 6 KB, and nothing else about
  them -- every clone body is built at load by applying the reviewed policy in
  `randomizer/rewards/template_policy.py` to the section the installation
  actually loads, so a submodded `rulesmo.ini` reaches every player clone.
  `randomizer_unit_roster()` checks this list against the reward catalogue on
  every load, so the two cannot drift apart. Ships register under engine
  `VehicleTypes`. Mission generation buffs the owned types while native IDs
  stay reserved for campaign AI and scripts.
- `RandomizerMapOnlySources.ini`: the six source bodies that exist only inside
  campaign, challenge and cooperative maps -- Boris, the Kirov Command
  Airship, Super Thor and the three boss Brutes -- and so can be looked up in
  no rules file. Verbatim map sections; the launcher applies clone policy to
  them exactly as it does to an installed section.

  These two replaced a 494 KB bake of every clone's complete stat line. The
  bake was stock Mental Omega with the same policy already applied, which
  meant it could be rebuilt from the rules the installation loads -- measured
  at 326 of 326 sections reproduced with no differences. Keeping it did active
  harm: the shop priced units off frozen stock numbers, so a submod repriced
  nothing.

  A consequence worth knowing: the reward catalogue is authored against stock
  Mental Omega, and on a submod some rewards do nothing. A speed buff on a
  unit the mod already moved to the safety ceiling, an `OpenTopped` buff on a
  transport the mod already opened, a weapon buff on a weapon the mod
  replaced. The self-check reports those under `inert_off_stock` rather than
  failing, because a modded game must still launch.

## Shop Mode balance

`shop_mode.json` is the only static source for Shop Mode economy and run-size
policy. `settings` defines positive `run_length` and `mission_offer_count`, the
non-negative `max_selected_permanent_units` and `starting_run_coins`, the
positive `maximum_starting_ore` and `minimum_shop_price`, and the version-1
`per_run` reroll policy.
`archipelago_purchase_locations` is the generated purchase-check count from
0 through 25, `archipelago_purchase_meta_coin_cost` is their positive shared
Gem price, and `archipelago_mission_victories_are_locations` controls
whether the ten stage victories also enter the shuffled AP item pool. These
values are signed into Shop player YAML and validated again at connection.
New Shop YAML signs `received_unit_loadout: all`: every received AP unit is
active on every Shop run without consuming permanent extra-unit slots. Legacy
`manual` and `random` rooms remain compatible and receive the same all-unit
behavior. This policy never changes Shop currency or mission-credit values.
`excluded_reward_ids` removes canonical rewards from Shop stock without
retiring them from normal Randomizer progression or old save receipts.

`mission_rewards` must contain exactly `act_1`, `act_2`, `operation`, and
`finale`. Each class has a display label, unique positive difficulty rank, and
non-negative Ore (`run_coins`) and Gem (`meta_coins`) rewards.
`stage_class_weights` uses ascending `through_percent` boundaries ending at
`100`; each profile supplies non-negative integer weights for all four mission
classes. Gem rewards must increase strictly with difficulty. Offer
generation samples only its named Shop RNG stream. A zero class weight is a
hard stage exclusion: stages 1–2 offer only Act 1, operations begin at stage 5,
and finales begin at stage 9. Protected opening offers include a fixed-unit or
hero mission when the eligible campaign pool provides one.
`stage_difficulty_weights` independently controls actual in-game Casual,
Normal, and Mental difficulty for each visible mission offer. Profiles use the
same ascending percentage boundaries. The offer's difficulty is derived from
run seed, stage, and mission code without consuming mission-selection RNG.
Stages 1–3 are Casual-heavy, stages 4–5 are Normal-heavy, stages 6–7 introduce
Mental, and stages 8–10 give Normal and Mental equal weight. Difficulty Assist
reduces only the chosen offer by one step.
`unit_inventory_size` controls the deterministic run-shop unit stock. Unit
stock remains stable during a stage and rotates after each mission victory;
eligible buffs remain available for every currently owned unit. Access entries
whose target is already active are removed before display and receive stable
replacement offers, covering starters, permanent/AP access, and run purchases.
`power_inventory_size` controls the power stock shown beside unit/building
offers in the same Run Shop list and uses the same owned-access exclusion.
`discount_specialization` retains its stable save ID but applies its configured
`ore_per_level` discount to all run-shop access and buff entries. Old saved
category fields remain readable and are ignored.

`mission_effects` defines deterministic one-mission player boons and hostile
challenges. Each entry contains display text, non-negative Ore/Gem bonuses,
and exactly one of `player_reward_ids` or `enemy_reward_id`.
`exclusive_reward_ids` suppresses a player boon when its access reward is
already active. Prefer access plus payload/recharge rewards for temporary
support boons: an unowned power becomes available, while an already-owned
power still receives a useful mission-only upgrade. The three visible mission
cards resolve duplicate effects to other entries of the same boon/challenge
kind without consuming gameplay RNG.

`price_scales` replaces the per-target price table the Shop used to carry.
Every price is derived now, because the table was scaled off each unit's
in-game credit cost and cost is the wrong axis: it says what a unit is worth
to build once you have it, while the shop is asking what it is worth to
*have* at all, for this run and every run after.

There are exactly two scales, `run_ore` and `permanent_gem`. They price the
same way and differ only in their numbers, so nothing in the pricing code has
to know which currency it is working in.

`tier_prices` gives each arsenal tier a `[low, high]` range, and the unit's
credit cost decides where inside it the unit lands -- interpolated across the
costs of the units in the *same* tier, since a single global window would push
every Tier 1 unit to the bottom of its range, they all being cheap.
`cost_window_trim_percent` trims the extremes of that per-tier window so one
superunit cannot flatten its tier. `rounding_step` rounds the result. The
ranges must not overlap downwards: a Tier 1 unit may never cost more than the
cheapest Tier 3 one, or pricing by tier means nothing.

`build_limited_building`, `campaign_infantry`, `campaign_unit` and
`campaign_building` are flat prices that replace the band outright and are not
multiplied afterwards; `0` means the scale has no such rule, which is how the
Ore scale declines all four. They exist because a credit cost is a poor guide
to what owning something forever is worth when the thing cannot be built at
all: a campaign unit has a cost the player will never pay, and a build-limited
building has one that says what it costs to put down rather than what having
the right to put it down is worth. Campaign-only outranks build-limited when a
target is both -- being absent from every skirmish game is the stronger claim,
and it is the one the player is buying past. A campaign target whose category
is unknown falls through to `reward_pool_multiplier` instead.

`unique_infantry` and `unique_unit` price units nobody can build more than
one of; `stolen_tech` is a `[low, high]` range for units gated behind
`Prerequisite.StolenTechs` (set both ends equal for a flat price). A unit that
is both takes the higher. These ignore the tier range entirely, because what
makes them worth having is that no one else can field one. **Unique buildings
and defenses are not heroes** -- an Ore Purifier is limited for balance -- so
they keep their tier range.

`premium_target_multiplier` then applies to every one-off: anything the game
build-limits **at any number**, whatever its category, and anything gated
behind stolen tech. It prices what fielding one for a run is worth, so the Ore
scale charges it and the Gem scale sets it to 1.

`power_tier_prices` and `flagged_power_price` price superweapons and aid
powers, which have no credit cost to read, so their tier decides outright.
"Flagged" means named by the superweapon or campaign-power Reward Pool group:
one list serves as both the filter and the premium price list, so a power
added to a group is priced as one without a second edit.

`buff_percent_of_access` prices one upgrade stack as a percentage of what its
target costs on the same scale. It applies even where the unit itself has no
access offer -- a Tier 1 starter is never for sale and its upgrades still need
a number. Only the Ore scale has anything to charge it on: the Gem shop sells
units, not unit upgrades. The Gem figure is kept so both scales stay the same
shape.

`reward_pool_multiplier` is the second, over a different set and for a
different reason: what the Reward Pool groups name is not capped, it is simply
absent from every skirmish game. That is worth something forever rather than
for a run, so the Gem scale charges it and the Ore scale sets it to 1. A unit
that is both -- Boris is build-limited *and* campaign-only -- pays each
multiplier on its own currency, not both on one.

Both sets are held out of the per-tier cost window, which is the more
important half. A one-off's price is the reason a tier's ordinary units looked
cheap: leaving a 10,000 credit superunit in stretched Tier 3's window and
pushed every ordinary tank toward the bottom of its range.

Cost, build limit and stolen-tech status are read from **the rules the
installation actually loads** -- a loose `rulesmo.ini` in the game folder
first, then the highest-numbered `expandmo` archive that carries the section,
which is the order the engine itself resolves. Nineteen units are priced from
their clone body instead, which is built from those same rules: units whose
reviewed identity is templated from a differently named section, and the six
that exist only inside maps. This used to read a committed bake of stock
Mental Omega, which drifted -- Tanya at 1,500 credits where the shipped rules
say 2,500, Centurion at 3,000 against 5,000, and BuildLimits belonging to the
randomizer's own player clones rather than to the game. Pricing off the bake
meant a submod repriced nothing.

Cost, category, build limit, and stolen-tech status all come from the live
roster, so a submod that reprices a unit reprices its Shop price with it.
Tiers stay in configuration: unit tiers come from the roster's TechLevel and
power tiers from `power_target_prices`, because neither is in the unit data
and reconstructing them from tech-building prerequisites is a great deal of
work for a number that rarely moves.

`power_target_prices` no longer carries prices; it carries the one thing a
power's price is derived from. Every Shop power target must appear exactly
once with a `tier` of `tier_1`, `tier_2`, or `tier_3`.

```json
"LIGHTNINGSTORMSPECIAL": {"tier": "tier_3"}
```

Discounted Ore prices use integer percentages, round down, then clamp to
`minimum_shop_price` -- which is why the cheapest upgrades all sit at that
floor rather than at their computed fraction.

`permanent_upgrades` maps stable IDs to `display_name`, positive `max_level`,
one positive price per level, and integer `effects`. Optional boolean
`purchasable` defaults to `true`; `false` retains a retired upgrade ID for old
profile normalization while hiding it and rejecting new purchases. An upgrade
deleted outright instead is listed in `RETIRED_UPGRADE_IDS`
(`randomizer/shop/state.py`), which drops the level from a saved profile rather
than refusing the profile. Version 1 requires the full stable account-upgrade
catalogue, including `coupon_book`, `stock_lock`, `veteran_academy`, and
`premium_supplier`.
`modifiers` maps stable IDs to display text and additive or
percentage economy effects. Percentage modifiers multiply exactly; flat
modifiers add. Unknown saved modifier or upgrade IDs fail with a
clear state error instead of silently changing balance.

Modifier effects support economy, stock size, mission-choice count, starter
composition/veterancy, player clone damage/durability/cost/production,
aid-power recharge, mission starting Credits, and feature-disable flags.
Percentages multiply in persisted modifier order; flat effects add. Each
distinct active ID contributes one visible difficulty point. `blind_choice`
uses the hidden-offer count only for presentation and never consumes gameplay
RNG. Combat changes are applied to isolated player clones; overlapping
production modifiers multiply instead of overwriting each other.

Example mission reward:

```json
"operation": {
  "display_name": "Operation",
  "difficulty": 3,
  "run_coins": 7,
  "meta_coins": 3
}
```

## Mission-specific overrides

Add reviewed map exceptions to `missions.json`; do not add mission-code
branches to the Python pipeline. Available sections cover player/helper houses,
native clone exclusions, required access rules, base-section values, native
unlock preservation, arbitrary map-section values, superweapon payload clones,
and native variant buff rules, plus reviewed Time Freeze immunity targets.
An expansion map can use the same sections once its mission code is present in
the catalogue/classification data.

`player_production_houses` lists houses whose factories later become usable by
the player without changing their initial factory-owner identity. Native
production isolation adds each listed house's country to
`FactoryOwners.Forbidden`, preventing an original unit cameo beside its
isolated player clone while preserving authored TaskForces. Zero Signal lists
`Pacific House` so its captured Barracks cannot expose locked native Allied
infantry.

`scripted_player_buff_taskforces` lists reviewed player or transferred-player
TaskForce IDs whose unit references follow the launch's isolated player clones.
Use it when authored Action-created teams must receive player buffs or when
native production-isolation fields would stop Ares from assembling the team.
Noise Severe lists its Rhino, Tesla Cruiser, Tigr/Shock/Flak, and paradrop
TaskForces; their scripted waves therefore form before the FriendlyTank handoff
and remain available to the player. Optional
`scripted_player_buff_taskforce_access_requirements` entries limit a rewrite to
launches that already own every listed source TechnoType.

`original_mcv_access` maps mission codes to native MCV TechnoType IDs. The
bundled default exposes `AMCV` and `SMCV` only in Foehn 06 (`FREMNANT`). These
remain original mission identities; no `MORP*` MCV clone is created. Replace
that mission's list to change the available MCVs, or set it to `[]` to disable
the exception. Missions absent from the mapping receive no original MCV access.

`time_freeze_immune_techno_ids` maps mission codes to exact scripted
TechnoTypes. Generation gives each target a mission-private armor alias that
inherits its normal armor, then gives only that alias `0%` verses on the
mission's private Time Freeze warhead. Other units sharing the original armor
remain affected. Use only for mission-critical objects whose EMP/AttachEffect
state can trigger AI selling, invalidate an objective chain, or permit
script-breaking stunlock abuse. Power Hunger protects `MORALES` and `NAHAMM`;
Bleed Red protects its scripted map-local `MORALES` Boris identity.

`native_production_gate_exclusions` is narrower engine-safety policy for
script-created native units. Power Hunger excludes `SAPC` because its player
MCV delivery team needs the authored Zubr identity. Its map-authored
`TechLevel=-1` still blocks native player production, while the isolated
buildable transport clone remains available.

Mermaid likewise excludes its map-local `TANY`. The authored Tanya changes
weapons after collecting her equipment, and its placed unit, attached trigger,
and scripted control flow must never inherit the hidden player production gate.

Bleed Red excludes its map-local `MORALES` identity because Ares also evaluates
the randomizer's hidden production gate while assembling the authored Boris
TeamType. The extracted type, TaskForce, and exact-type Events must stay native;
historical attempts to move or replace that identity caused instant defeat and
runtime fatal errors.

Power Hunger also patches four authored `Actions` values. Objective 2
completion now creates both Latin AI and player MCV delivery teams. The Latin
team reuses the proven native `SAPC+SMCV` TaskForce and unloads before running
an explicit deploy action, its authored base-ready sequence, and guard. Live
play proved `TransportsReturnOnUnload=yes` leaves the empty transporter in the
MCV's deployment cells. Unload mode `8,2` separates that SAPC from the MCV
team. Local-47 action `01001542` then creates Latin-only
`MORSREDLatinSAPCReturn`, which recruits exactly one free SAPC with the
authored SAPC-only TaskForce/script, moves it to waypoint 400, and deletes it.
No whole-team delete touches the MCV. Authored script `01001529` originally
moved a land MCV to waypoint 3. The transported version repeats that move after
unload so the separated MCV receives it, waits six seconds for the SAPC to
clear, then deploys. The delivery uses the same prebuilt,
non-Autocreate mode as working Latin SAPC reinforcements. Objective 2 also sets
authored local `47`, guaranteeing the unchanged Latin ConYard and AI activation
chain even if the engine rejects the visual transport at water waypoint `EY`.
Later native actions retain every non-MCV effect but omit duplicate MCV
creation. This replaces the authored 7.5-minute plus 3-minute Latin MCV delay;
the player MCV originally waited for that AI MCV to deploy into `NACNST`.

`objective_clone_event_refs` retargets exact reviewed objective Events to the
player clone allocated for that launch without rewriting enemy placements or
scripted TaskForces. Machinehead uses this for Foxtrot Events `01000926` and
`01000942`; both count the isolated build-only clone, including compact veteran
IDs, while enemy Foxtrots stay native. Its GHTNK transports carry the Driller
reinforcements. Changing or disabling their return triggers also crashed and is
not part of the fix. Original/generated comparison found every native type in
that reinforcement wave had received randomizer production-isolation fields:
`GHTNK`, `CNTR`, its initial `COVE` payload, `EMPR`, `CTNK`, and `ARMA`.
`native_runtime_identity_preserve_ids` restores reviewed runtime sections after
clone planning. EHEAD uses it for that complete set; return triggers, scripts,
TaskForces, and runtime identities therefore retain the original map values,
except the two final return-script deletes. After identity preservation removed
the earlier invalid-vtable crash, the next live dump failed inside gamemd at
`004F9AB1`: a returned GHTNK had already had its Owner cleared by action 37 but
was still referenced by the engine's object scan. Scripts `01000557` and
`01000558` retain their authored move-to-edge action and replace only final
`37,0` with guard `5,2`; triggers and team creation remain authored.
Singularity attaches an
Entered-by-PsiCorps tag to the authored Driller, so Malver boarding completes
the evacuation condition even though transported passengers remain live game
objects.

`transport_factory_exceptions` adds reviewed physical factory alternatives to
an always-available amphibious transport without removing its normal naval
yard path. Keys are mission codes, then transport TechnoType IDs; each value is
a non-empty list of extra factory IDs. Golden Gate adds `GAWEAP` for `SAPC`, so
its Zubr can be rebuilt from the captured Allied War Factory or Soviet Naval
Yard in every reward mode.

`special_infantry_factory_exclusions` lists map-local `Factory=InfantryType`
buildings that serve only authored mission production. Excluded factories are
never appended to randomizer Engineer, Standard infantry, or Chaos infantry
prerequisite alternatives.

`map_section_rules` can patch any INI section in any configured mission. A
literal replaces a value, `null` removes its key, and `add`/`remove` edits a
comma-separated ID list without copying the map's complete original value:

```json
"map_section_rules": {
  "SFATAL": {
    "YTUNNEL": {
      "Passengers.Allowed": {
        "add": ["MORPSVOLKOV"],
        "remove": []
      }
    }
  }
}
```

`rewards/tuning.json` changes newly generated maps and reward plans. Clone ID
prefixes, the `ui_description` shown on every Randomizer-owned unit, and
production-field lists are advanced engine policy: keep IDs within the Ares
24-character limit and retain `Projectile`/`Warhead` requirements unless a
modified engine has been tested. Older files without `ui_description` retain
the compatible `NOSTR:* Granted by Randomizer` default.

Aid reward identity and display data live in `catalogue.json` under
`aid_power_rewards` (`name`, `description`, `faction`, `superweapon`, `index`).
Map injection behavior for each matching `superweapon` remains under
`aid_power_map_configs`.

Power buff applicability lives separately in `rewards/power_buffs.json`.
Grouped lists make every supported power/effect pairing reviewable without
mixing superweapon mechanics into unit/building buff policy. Runtime folds
earned stacks only into an actually earned power unlock and its isolated
`MOR...` clone; a buff alone emits no grant or clone. The Unlock dashboard also
tracks earned buffs separately from earned access, keeps the power locked, and
labels those effects stored until the real unlock is received. Native mission
SuperWeaponTypes and effect helpers remain unchanged.
`payload.drop_pod_type_weight_additions` adds configured type weights for each
DropPod payload stack. Moon Reinforcements adds both `SHOCK` and `CYBO` per
stack while increasing its minimum and maximum pod count.
`vision.power_fields` privately clones the configured SpyPlane aircraft and
increments only its `Sight`; Spy Plane is deliberately excluded from payload
count because additional planes do not improve that power.

`health.techno_fields`, `effect.multiplier_fields`, and
`targeting.vehicle_armor_fields` describe isolated delivered-structure health,
AttachEffect multiplier, and all-vehicle upgrades. All-vehicle targeting derives
armor overrides from selectable installed `VehicleTypes`; explicitly
unselectable or non-scoring spawners, dummy objects, timed beams, and add-ons
remain excluded. Script-only map armor aliases continue inheriting their
authored immunity. An optional
`clone_key` selects an existing private clone whose lookup key differs from its
installed `source` section. `payload.internal_unit_delivery_fields` increases a
nested delivery SuperWeaponType instead of duplicating its outer structure.
`duration.draining_techno_fields` gives timed self-damaging structures a private
armor alias, allowing health and lifetime stacks to remain independent.

`techno_clones` may provide private weapons, projectiles, warheads, delivered
academy markers, or hidden EMPulse cannon buildings. A BuildingType with
`startup_count` is created for each power-grant country; runtime replaces its
inherited ownership with that country and splits map-start action lists by both
the configured action-count ceiling and the engine's byte limit.
`provides_superweapon=true` binds the generated SuperWeaponType clone to that
hidden BuildingType through its vanilla primary `SuperWeapon` slot. This
supplies a real player-owned launch source for engine paths such as
GenericWarhead EMP/AttachEffect filtering without adding a weapon.
`static_startup=true` places that provider directly in `[Structures]` under
each exact mission House instead of creating it through action 125. Use this
when engine filtering must resolve the provider from the owning House before
map-start grant triggers run.

Custom power artwork uses `sidebar_image` with a plain PNG filename from
`assets/`; its matching `values.SidebarPCX` supplies the loose PCX filename
referenced by the generated map. The launcher converts the PNG to the game's
required 60×48 indexed PCX format on launch and uses the same PNG for its
Unlocks preview. Packaged defaults become visible under
`%LOCALAPPDATA%/MentalOmegaRandomizer/<installation>/assets` so replacement artwork remains editable.
For a custom power, copy `my_power.png` into that `assets` directory and set:

```json
"sidebar_image": "my_power.png",
"values": {
  "SidebarPCX": "mormypwr.pcx"
}
```

Use a plain PNG filename and a unique PCX filename beginning with `mor`; no
manual image conversion or `cameo_superweapon` fallback is needed.

Map-only unit cameos use `rewards/unit_data.json:unit_sidebar_images`. Keep the
existing `image` + namespaced `pcx` pair for bundled PNG artwork. Use a single
`source_pcx` filename for game/Bonus MIX artwork. Installed game-root MIX files
always win; `assets/expandmo21 Bonus.mix` is fallback only. Required PCXs are
extracted into launcher staging, activated beside the game only for the spawned
mission, and removed afterward by hash-verified cleanup.
When a TechnoType uses a different `Image=`, add `art_id` to the PNG mapping so
the same cameo is merged into that complete installed art section.

`rewards/buff_exceptions.json` section `excluded_buff_type_ids` maps each buff type
to TechnoType IDs that must not receive it. Use `all` for complete exclusions.
These entries affect newly planned rewards; retired items in old saves stay in
state for compatibility but are omitted from the Unlocks list. Weapon buffs
must change a direct weapon on the isolated player clone. Keep damage rewards
for shared spawned aircraft, missiles, or payload weapons excluded unless the
complete payload chain gains a private, validated clone path.

`rewards/unit_data.json` section `spawned_missile_range_support` maps a reviewed
launcher TechnoType to its spawned missile AircraftType and installed base
`GuardRange`. When that launcher's weapon range is upgraded, map generation
adds the same range increase to the missile pursuit envelope. Keep this list
narrow: extending missile pursuit is safe only when the native launcher's
unchanged weapon range remains within its original envelope. Akula is the only
reviewed entry.

## Load locations

Source runs load static files from this directory directly. A packaged EXE
bundles these defaults plus a hash manifest and exposes them under
`%LOCALAPPDATA%/MentalOmegaRandomizer/<installation>/configs` beside the game. First launch after upgrading
from a pre-manifest build backs up differing legacy files as
`*.pre-bundle-sync-backup`, then installs one complete current set. Later
updates replace only files still matching the preceding bundled hash; locally
edited files remain authoritative. Player YAML lives in the separate
`configs/player/` child, is always launcher-managed, and is excluded from
packaged build inputs.

EVA voice labels and engine tags have one source under `ui.json`:
`eva_voice_tags`. Object order controls menu order. Add, remove, or rename one
mapping there; launcher derives its choices automatically, with fixed
`Mission default` and `Random` options around configured entries. Engine tags
`Allied`, `Russian`, and `Yuri` use Ares EVA indexes 0–2. Other configured tags
use indexes 3 onward in this same object order, which must match their order in
the installed `EVATypes` list.

`eva_appearance_profiles` optionally binds the matching faction sidebar and
mission-text color to an EVA choice. Profile keys normally match the visible
choice label from `eva_voice_tags`; an engine tag also works as a fallback.
`Mission default` applies neither voice nor appearance overrides. Built-in
Allied, Soviet, Epsilon, and Foehn voices retain their installed appearance
defaults when an older external `ui.json` does not yet contain profiles. All
four Mental Omega sidebar sets use Yuri's Revenge filenames, so their
`sidebar_yuri_file_names` value must be `true`; runtime enforces this for the
built-in EVA tags to protect preserved older editable configurations.

Every document requires `schema_version: 1` and a `sections` object. Startup
validates required sections and important value types. Invalid JSON or missing
required data stops startup with the exact file and section in the error.

Keep a backup before gameplay changes. These files define compatibility facts;
invalid mission houses, production IDs, or role groups can break campaign maps
even when JSON validation succeeds.

## authenticity_manifest.json

Generated, not edited. `tools/build_authenticity_manifest.py` runs over a
pristine Mental Omega tree and writes the hashes an installation is compared
against: 487 files by path and 105 members inside the MIX archives, in 59 KB
describing about a gigabyte.

Members rather than archives, because Mental Omega ships the archives
protected and unprotecting one repacks the container. Every archive-level hash
then breaks -- including Mental Omega's own `version` manifest, on archives
nobody modified -- while the members inside are untouched. Text is hashed with
line endings normalised, since the same INI reaches the launcher CRLF from one
source and LF from another.

`MapsMO/Standard` is deliberately outside the manifest: 1,440 skirmish maps
and 276 MB that a campaign randomizer never reads. The map pool that matters
comes from `configs/maps`, which is also where the member names are taken
from -- MIX indexes store hashed names rather than names, so a member can be
looked up but never enumerated, and anything unnamed is unchecked.

The result is reported, never enforced. A modded or patched installation is a
fact about the player's game, not a fault in the launcher.

## rules_digest.json

The same question one level down. The manifest answers "is this file stock";
this answers "is this *section* stock", which is what the launcher needs once
every player clone is built from the rules the installation actually loads:
a submod's Rhino must reach the game as the submod's Rhino, and still be
marked as not stock.

Answering it needs the stock rules, and shipping them costs 4.2 MB and puts
the answer in a file the player can edit. So what ships is 146 KB of hashes:
one 48-bit keyed digest per section, 11,699 of them across all four stock
INIs. Enough to say a section differs; not enough to reconstruct a line of it.
Keys are compared lower-case and sorted before hashing, because INI key case
and order mean nothing to the engine and must mean nothing here either.

`rulesmo` drives the unit marker and `artmo` the clone art. `aimo` and
`battlemo` are digested because they are part of what "stock" means, at a few
kilobytes each, so a later check needs no new format.

The hash is keyed rather than plain for the reason `randomizer/core/integrity`
gives about its own: a plain SHA lets anyone recompute a digest for their edit
and patch it into the table. It is a doorstep, not a lock. For the same
reason `tools/build_rules_digest.py` is not committed -- neither are the
`configs/*-original.ini` files it reads -- so the table cannot be rebuilt from
a modified installation. Regenerating it is a maintenance step, run once per
Mental Omega version.
