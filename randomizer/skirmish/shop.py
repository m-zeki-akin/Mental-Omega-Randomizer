"""What a run can buy between battles.

Upgrades only, and only for the army the run plays -- the *country*, not the
side. All three Allied countries share a side and field different rosters:
a United States run has no Hailstorm to improve, because the Hailstorm
needs the Pacific Front's own tier two building. The ally shops too, out of
its own earnings and its own country's list, so the two armies grow apart
over a run without the player spending anything on it.

Nothing here unlocks a unit. A run fields what its country fields; what Ore
buys is that army getting better at what it already does.

The catalogue is the one the campaign shop sells from -- the same units, the
same buff types, the same prices and stack limits -- read through the same
clamp that stops a reward being sold past the point where it changes
anything on this installation.
"""

from dataclasses import dataclass
from functools import lru_cache
import random

from .config import SETTINGS
from .model import UpgradePurchase, closes_tier, tier_of
from .ownership import STOLEN_TECH_GROUP


# Every number below is read from ``configs/skirmish.json``; the names
# stay because they are what the rest of the mode calls them. What each
# one means is written in the file beside its value, where somebody
# tuning a run will be looking.
#
# What a battle pays, fixed rather than scaled by the score: a score can be
# farmed by dragging a won battle out, and a run's difficulty should not be
# something a player can grind around.
BATTLE_REWARD = int(SETTINGS.economy['battle_reward'])
REWARD_PER_TIER = int(SETTINGS.economy['reward_per_tier'])
CHALLENGE_REWARD_MULTIPLIER = int(
    SETTINGS.economy['challenge_reward_multiplier']
)
STARTING_ORE = int(SETTINGS.economy['starting_ore'])
# What it costs to send the shelf away and be dealt another. There is no
# limit on how often: what limits it is that every reroll is Ore not spent
# on the army.
REROLL_PRICE = int(SETTINGS.economy['reroll_price'])
# How many upgrades stand on the shelf between battles, and how many by
# the end. The shelf is drawn from the run's seed, so it is the same shelf
# every time the run is opened, and it grows a row a tier because what a
# battle pays grows too.
SHELF_SIZE = int(SETTINGS.shelf['size'])
SHELF_CAP = int(SETTINGS.shelf['cap'])
# What a stolen-tech row costs on top of the dearest unit it improves, per
# extra unit it reaches. Reach is what is paid for.
STOLEN_TECH_PRICE_PER_UNIT = float(
    SETTINGS.economy['stolen_tech_price_per_unit']
)
# What an upgrade costs, by what it does -- not by the unit it is for and
# not by the tier it is bought in. Two tables because the names collide and
# the prices do not: a unit's ``damage`` and a superweapon's are different
# purchases.
UNIT_BUFF_PRICES = dict(SETTINGS.prices['unit'])
POWER_BUFF_PRICES = dict(SETTINGS.prices['power'])
# And what a stat named in neither costs -- range, harvester capacity, and
# anything a submod adds that those tables have never heard of.
DEFAULT_BUFF_PRICE = int(SETTINGS.prices['default'])
# What is not sold at any price: what the campaign shop delivers and this
# mode cannot. Veterancy is granted on the house, a build limit is raised
# by building a clone, and a passenger firing out of a transport needs the
# transport the rules name. All of them would take Ore and change nothing.
UNSOLD_BUFFS = frozenset(SETTINGS.prices['unsold'])
# How much of the shelf is powers rather than units. Read as a share: each
# row drawn is a power with probability power/(unit+power).
UNIT_UPGRADE_WEIGHT = int(SETTINGS.shelf['unit_upgrade_weight'])
POWER_UPGRADE_WEIGHT = int(SETTINGS.shelf['power_upgrade_weight'])


@dataclass(frozen=True)
class Upgrade:
    unit: str
    buff_type: str
    name: str
    description: str
    price: int
    limit: int
    # What one stack does, in the campaign shop's own words.
    effect: str = ''

    @property
    def key(self):
        return (self.unit, self.buff_type)


def shelf_size(tier):
    """Return how many upgrades stand on the shelf in this tier."""
    return min(SHELF_CAP, SHELF_SIZE + max(0, int(tier) - 1))


def upgrade_price(buff_type, *, power=False):
    """Return what one upgrade costs, off what the upgrade does.

    Two tables because the names collide and the prices do not: a unit's
    ``damage`` is 100 and a superweapon's is 200.
    """
    table = POWER_BUFF_PRICES if power else UNIT_BUFF_PRICES
    return int(table.get(str(buff_type or ''), DEFAULT_BUFF_PRICE))


def price_for(upgrade):
    """Return what one upgrade costs.

    Its list price, whatever the army already owns. A rise per upgrade
    owned made the fortieth purchase a different decision from the first
    for no reason a player could read off the shelf: what limits a late
    run is the eight rows it is offered and the Ore a battle pays, both
    of which are already visible.
    """
    return max(1, int(upgrade.price))


def battle_reward(battle, *, challenge=False, bonus_percent=0):
    """Return the Ore a won battle pays.

    ``bonus_percent`` is what the offer asked for: a battle taken with one
    more enemy on the field, or without the ally, pays for the asking.
    """
    tier = tier_of(max(1, int(battle)))
    reward = BATTLE_REWARD + REWARD_PER_TIER * (tier - 1)
    if challenge:
        reward *= CHALLENGE_REWARD_MULTIPLIER
    return int(round(reward * (100 + max(0, int(bonus_percent))) / 100))


def earned_by(battle):
    """Return the Ore a run has had in hand by the time it fights this one.

    What it started with, plus what every battle before it paid -- the
    plain price, challenges doubled, nothing asked for. It is what an
    enemy is armed against: a run reaching battle three has had 375 Ore
    to spend, so the army it meets there has had 375 too.
    """
    total = STARTING_ORE
    for before in range(1, max(1, int(battle))):
        total += battle_reward(before, challenge=closes_tier(before))
    return total


@lru_cache(maxsize=16)
def country_upgrades(country):
    """Return every upgrade this country can buy, cheapest first.

    Reads the campaign shop's own catalogue, kept to what this country can
    put on the field: ownership and the prerequisite chain both, so a unit
    gated by another country's tier two building never reaches the shelf.

    The stolen-tech units are the exception: they are sold as one row per
    stat rather than one row per unit, because a run cannot decide to build
    them and cannot choose which one an infiltration brings.

    An upgrade the installation would not notice -- a speed buff on a unit a
    submod already has at the ceiling -- is not offered either, which is the
    same clamp the campaign shop applies at its own offer time.

    Nor is one this mode cannot deliver. The campaign grants veterancy on
    the house and raises a build limit by building a clone of the unit;
    a skirmish has neither, so those buffs would take Ore and change
    nothing. An upgrade is sold here only if it writes at least one key
    onto a unit in this installation.

    Three more are held back because a purchase is a *copy* of the unit,
    gated to the buyer alone. A unit that deploys, converts, or carries a
    payload names its other form by ID, and the other form still names the
    original -- which the buyer is shut out of, so the conversion would
    hand back a unit they may not own. Buildings are worse: they are what
    prerequisites are written against. Both wait for work of their own.
    """
    from randomizer.rewards.buff_reach import effective_stack_limit
    from randomizer.rewards.catalogue import (
        BUFF_TARGETS,
        UNIT_BUFF_REWARDS,
        buff_stack_limit,
    )
    from randomizer.rewards.display import buff_effect_lines
    from randomizer.rewards.roster import _installed_sections

    from .clones import clonable
    from .ownership import (
        STOLEN_TECH_GROUP,
        buildable_units,
        country_faction,
        excluded_units,
        stolen_tech_units,
    )
    from .rules import unit_rules

    installed = _installed_sections()
    fielded = buildable_units(str(country or ''))
    faction = str(country_faction(country) or '').lower()
    stolen = set(stolen_tech_units(country))
    upgrades = []
    bundles = {}
    for reward in UNIT_BUFF_REWARDS:
        unit = str(reward.get('unit') or '').upper()
        if unit not in fielded or unit in excluded_units():
            continue
        # Ownership alone lets the stolen-tech units through: what gates
        # those is an infiltration, and a game option file rather than the
        # rules carries the country list that says so. The catalogue's own
        # faction is the floor for everything else -- but not for them. The
        # Cyborg Commando is tagged Soviet and stolen by all four sides,
        # and the floor was quietly keeping it off an Allied shelf.
        factions = [
            str(item).strip().lower()
            for item in (reward.get('factions') or ())
        ]
        if unit not in stolen and faction and factions and faction not in factions:
            continue
        buff_type = str(reward.get('buff_type') or '')
        if not unit or not buff_type or buff_type in UNSOLD_BUFFS:
            continue
        # The catalogue's stack limit says how far a buff could be pushed;
        # what is asked here is only whether this installation would notice
        # it at all. A shelf row is bought once -- the campaign shop sells a
        # reward once too, and an upgrade that can be bought again until the
        # Ore runs out is not a choice between upgrades.
        if effective_stack_limit(
            unit, buff_type, buff_stack_limit(reward) or 1
        ) <= 0:
            continue
        limit = 1
        if not unit_rules(unit, buff_type, 1, installed, BUFF_TARGETS):
            continue
        if not clonable(unit, installed, BUFF_TARGETS):
            continue
        # Read against the rules that are loaded, not the reviewed
        # baseline: what is written when this is bought is computed from
        # the unit as it stands, and the shelf should say the same thing.
        effect = buff_effect_lines(
            reward, 1, include_label=False, include_stack=False,
            installed=installed,
        )
        made = Upgrade(
            unit=unit,
            buff_type=buff_type,
            name=str(reward.get('name') or f'{unit} {buff_type}'),
            description=str(reward.get('description') or ''),
            price=upgrade_price(buff_type),
            limit=1,
            effect=effect[0] if effect else buff_type.replace('_', ' '),
        )
        if unit in stolen:
            # Not a row of its own. Everything gated behind an infiltration
            # is bought together or not at all.
            bundles.setdefault(buff_type, []).append(made)
            continue
        upgrades.append(made)
    upgrades.extend(_stolen_tech_bundles(bundles, stolen))
    upgrades.extend(_power_upgrades(country))
    return tuple(sorted(upgrades, key=lambda item: (item.price, item.name)))


def _power_upgrades(country):
    """Return the superweapon upgrades this country can buy.

    One row per power it can build the granting structure for, per buff
    that writes anything onto that power. A power a run cannot build has
    nothing to improve, and a buff with nothing to bite on -- a power with
    no money to give has no cost to lower -- is not a row.
    """
    from randomizer.rewards.power_buff_definitions import (
        POWER_BUFF_TYPE_BY_ID,
    )

    from .powers import (
        canonical_power,
        country_powers,
        power_buff_rules,
        sellable_buffs,
    )

    rows = []
    for power in sorted(country_powers(country)):
        named = canonical_power(power)
        for buff_type in sellable_buffs(power):
            definition = POWER_BUFF_TYPE_BY_ID.get(buff_type) or {}
            written = power_buff_rules(power, buff_type, 1)
            rows.append(Upgrade(
                unit=power,
                buff_type=buff_type,
                name=f"{_power_name(named)} {definition.get('name') or buff_type}",
                description=str(definition.get('description') or ''),
                price=upgrade_price(buff_type, power=True),
                limit=1,
                # What it actually writes, which for a power is one or two
                # keys and is more use than a sentence about moments.
                effect=', '.join(
                    f'{key} {value}' for key, value in sorted(written.items())
                ) or str(definition.get('name') or buff_type),
            ))
    return rows


@lru_cache(maxsize=1)
def _power_names():
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, rules = installed_rules_registry(synchronous=True)
    return {
        str(name).upper(): str((body or {}).get('Name') or name)
        for name, body in (rules or {}).items()
    }


def _power_name(power):
    """Return what the game calls one superweapon."""
    return _power_names().get(str(power).upper(), str(power))


def _shared_effect(effects, label, count):
    """Return one line for a row that improves several units at once.

    When they all do the same thing it is that sentence. When they do not
    -- one unit gains a point of speed and another two -- what is said is
    the part they agree on, which is the stat in the game's own words. The
    grouping label alone would not do: "Movement" is what the catalogue
    files speed under, not what the player is buying.
    """
    if len(effects) == 1:
        return next(iter(effects))
    shared = []
    for words in zip(*(line.split() for line in effects)):
        if len(set(words)) != 1:
            break
        shared.append(words[0])
    stat = ' '.join(shared).strip(' ,:') or label
    reach = {1: 'on it', 2: 'on both'}.get(count, f'on all {count}')
    return f'{stat}, {reach}'


def unit_label(unit):
    """Return what the game calls one unit, or its ID if it has no name."""
    from randomizer.rewards.catalogue import BUFF_TARGETS

    return str(
        (BUFF_TARGETS.get(str(unit or '').upper()) or {}).get('label') or unit
    )


def _stolen_tech_bundles(by_buff_type, members):
    """Return one row per buff type, standing for every stolen-tech unit.

    A run does not choose which of these it fields, or whether it fields any
    -- an infiltration decides that -- so buying them one at a time is
    buying a lottery ticket several times over. One row raises the stat on
    all of them, once, like every other row.
    """
    from randomizer.rewards.weights import (
        ECONOMY_WEIGHT_TYPES,
        UNIT_BUFF_WEIGHT_TYPES,
    )

    from .ownership import STOLEN_TECH_GROUP

    labels = dict(UNIT_BUFF_WEIGHT_TYPES) | dict(ECONOMY_WEIGHT_TYPES)
    bundles = []
    for buff_type, found in sorted(by_buff_type.items()):
        if not found:
            continue
        label = labels.get(buff_type, buff_type.replace('_', ' ').title())
        effects = {item.effect for item in found}
        # Not every stolen-tech unit takes every stat -- one has no weapon
        # to fire faster, another carries nobody -- so a row names the ones
        # it actually improves rather than the whole set, and names them
        # the way the game does rather than by their rules ID.
        reached = sorted({item.unit for item in found})
        missing = sorted(set(members) - set(reached))
        named = ', '.join(unit_label(one) for one in reached)
        bundles.append(Upgrade(
            unit=STOLEN_TECH_GROUP,
            buff_type=buff_type,
            name=f'Stolen Tech: {label}',
            # Named rather than described in a direction: a row that
            # lowers a cost and one that raises a rate of fire are both
            # this row, and "raises cost" is the wrong way round.
            description=(
                f'{label} on {named}'
                + (
                    '. Not on '
                    + ', '.join(unit_label(one) for one in missing)
                    + ': no such row is sold for them.'
                    if missing else ' -- every one of them.'
                )
            ),
            price=int(round(
                max(item.price for item in found)
                * (1 + (len(reached) - 1) * STOLEN_TECH_PRICE_PER_UNIT)
            )),
            limit=1,
            effect=_shared_effect(effects, label, len(reached)),
        ))
    return bundles


def owned_stacks(purchases, unit, buff_type):
    for purchase in purchases or ():
        if purchase.unit == unit and purchase.buff_type == buff_type:
            return purchase.stacks
    return 0


def available_upgrades(upgrades, purchases):
    """Return what is not already bought to its limit."""
    return tuple(
        upgrade for upgrade in upgrades
        if owned_stacks(purchases, upgrade.unit, upgrade.buff_type)
        < upgrade.limit
    )


def on_the_shelf(upgrades, kept_off=()):
    """Return the rows the player has not switched off.

    ``kept_off`` is what the roguelike settings hide from every shelf --
    the same switches Shop Mode reads -- as upper-cased target ids. A row
    for a unit or a power in it is not dealt, not bought by the ally, and
    not rerolled onto the shelf either.
    """
    if not kept_off:
        return list(upgrades)
    return [
        one for one in upgrades if str(one.unit).upper() not in kept_off
    ]


def draw_shelf(run, country, *, count=SHELF_SIZE, salt='shelf', purchases=None,
               kept_off=()):
    """Return the keys of the upgrades to offer for one battle.

    Drawn from the run's seed and its battle number, out of what the buyer
    does not already own. ``purchases`` says which buyer that is; without
    one it is the player, because the player's shelf is the one every
    caller but the ally's own draw wants.
    """
    from .powers import superweapon_ids

    upgrades = available_upgrades(
        on_the_shelf(country_upgrades(country), kept_off),
        run.purchases if purchases is None else purchases,
    )
    if not upgrades:
        return ()
    generator = random.Random(f'{run.seed}:{run.battle}:{salt}')
    powers = superweapon_ids()
    # Drawn a slot at a time rather than out of one pile. There are three
    # hundred unit rows and forty power rows, so one pile would put a
    # power on the shelf about once a run; a slot decided by weight puts
    # one there about once a shelf, which is what the weights say.
    pools = {
        True: [one for one in upgrades if one.unit in powers],
        False: [one for one in upgrades if one.unit not in powers],
    }
    for pool in pools.values():
        generator.shuffle(pool)
    share = POWER_UPGRADE_WEIGHT / (
        UNIT_UPGRADE_WEIGHT + POWER_UPGRADE_WEIGHT
    )
    drawn = []
    for _ in range(min(count, len(upgrades))):
        wanted = generator.random() < share
        # A pool that has run dry hands the slot to the other one rather
        # than leaving the shelf a row short.
        pool = pools[wanted] or pools[not wanted]
        drawn.append(pool.pop())
    return tuple(shelf_key(upgrade) for upgrade in drawn)


def shelf_key(upgrade):
    return f'{upgrade.unit}:{upgrade.buff_type}'


def shelf_for(run, country, *, count=SHELF_SIZE, salt='shelf'):
    """Return the upgrades standing on the shelf for this battle.

    The eight the battle was given, in the order it was given them --
    including any already bought, which stay on the shelf marked as bought.
    A shelf that held only what you have not bought would reshuffle itself
    the moment you bought from it: eight new names where the one you chose
    used to be, and nothing to show that anything had happened.
    """
    stored = tuple(getattr(run, 'shelf', ()) or ())
    if not stored:
        stored = draw_shelf(run, country, count=count, salt=salt)
    by_key = {
        shelf_key(upgrade): upgrade for upgrade in country_upgrades(country)
    }
    return tuple(
        by_key[key] for key in stored if key in by_key
    )


def purchase_stacks(purchases, upgrade, *, stacks=1):
    """Return the purchase list with this upgrade bought once more."""
    updated = []
    found = False
    for purchase in purchases or ():
        if purchase.key == upgrade.key:
            updated.append(UpgradePurchase(
                purchase.unit,
                purchase.buff_type,
                min(upgrade.limit, purchase.stacks + stacks),
            ))
            found = True
        else:
            updated.append(purchase)
    if not found:
        updated.append(UpgradePurchase(
            upgrade.unit, upgrade.buff_type, min(upgrade.limit, stacks)
        ))
    return tuple(updated)


def ally_shopping(run, country, coins, *, kept_off=()):
    """Return what the ally buys with what it has, and what is left.

    The ally spends on its own, from its own country's list, and it spends
    what it has rather than saving: an ally that hoards is an ally that
    never gets better. What the player has kept off the shelf is off the
    ally's too: the switch is about the run, not about who is shopping.
    """
    from .ai import fielded_by_ai

    # The ally builds what its task forces name, like any other computer
    # player, so a row on anything else is its Ore spent on a unit it
    # will not field. The player's own shelf is not held to this: a human
    # builds what the sidebar offers.
    fielded = fielded_by_ai()
    upgrades = available_upgrades(
        [
            one for one in on_the_shelf(country_upgrades(country), kept_off)
            if not fielded or one.unit in fielded
            or one.unit.startswith(STOLEN_TECH_GROUP)
        ],
        run.ally_purchases,
    )
    if not upgrades:
        return run.ally_purchases, coins
    generator = random.Random(f'{run.seed}:{run.battle}:ally')
    purchases = run.ally_purchases
    affordable = True
    while affordable:
        choices = [
            upgrade for upgrade in available_upgrades(upgrades, purchases)
            if price_for(upgrade) <= coins
        ]
        if not choices:
            affordable = False
            continue
        chosen = generator.choice(choices)
        coins -= price_for(chosen)
        purchases = purchase_stacks(purchases, chosen)
    return purchases, coins


def purchase_labels(purchases, country):
    """Return one readable line per purchase, for showing what was bought."""
    named = {upgrade.key: upgrade for upgrade in country_upgrades(country)}
    lines = []
    for purchase in purchases or ():
        upgrade = named.get(purchase.key)
        name = upgrade.name if upgrade else f'{purchase.unit} {purchase.buff_type}'
        lines.append(f'{name} x{purchase.stacks}')
    return tuple(sorted(lines))


def purchase_summary(purchases):
    """Return ``{unit: {buff_type: stacks}}`` for what has been bought."""
    summary = {}
    for purchase in purchases or ():
        summary.setdefault(purchase.unit, {})[purchase.buff_type] = (
            purchase.stacks
        )
    return summary
