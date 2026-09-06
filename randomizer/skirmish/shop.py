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

from .model import BATTLES_PER_TIER, UpgradePurchase


# What a battle pays, by the tier it was fought in. Fixed rather than scaled
# by the score: a score can be farmed by dragging a won battle out, and a
# run's difficulty should not be something a player can grind around.
BATTLE_REWARD = 125
REWARD_PER_TIER = 75
CHALLENGE_REWARD_MULTIPLIER = 2
STARTING_ORE = 125
# How many upgrades stand on the shelf between battles. The shelf is drawn
# from the run's seed, so it is the same shelf every time the run is opened.
SHELF_SIZE = 6
# What a stolen-tech row costs on top of the dearest unit it improves, per
# extra unit it reaches. A row that raises a stat on five units is worth
# more than one that raises it on one, and some stats reach only one of
# them -- a unit with no weapon has no fire rate. Reach is what is paid for.
STOLEN_TECH_PRICE_PER_UNIT = 0.5


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


def upgrade_price(unit):
    """Return what one upgrade costs, off the unit's own credit cost.

    The campaign shop prices a hero flat and charges a premium on top: it
    is selling the only Tanya the run will ever have. A skirmish builds one
    in a barracks like anything else, so the flat prices and the premium
    have no claim here and the unit's own cost decides.
    """
    from randomizer.shop.config import SHOP_CONFIG
    from randomizer.shop.unit_pricing import cost_derived_buff_price

    return int(cost_derived_buff_price(unit, SHOP_CONFIG.price_scales['run_ore']))


def battle_reward(battle, *, challenge=False):
    """Return the Ore a won battle pays."""
    tier = (max(1, int(battle)) - 1) // BATTLES_PER_TIER + 1
    reward = BATTLE_REWARD + REWARD_PER_TIER * (tier - 1)
    return reward * (CHALLENGE_REWARD_MULTIPLIER if challenge else 1)


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
        if unit not in fielded:
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
        if not unit or not buff_type:
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
        effect = buff_effect_lines(
            reward, 1, include_label=False, include_stack=False
        )
        made = Upgrade(
            unit=unit,
            buff_type=buff_type,
            name=str(reward.get('name') or f'{unit} {buff_type}'),
            description=str(reward.get('description') or ''),
            price=upgrade_price(unit),
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
    return tuple(sorted(upgrades, key=lambda item: (item.price, item.name)))


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
    return f'{stat}, on all {count}'


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
        # it actually improves rather than the whole set.
        reached = sorted({item.unit for item in found})
        missing = sorted(set(members) - set(reached))
        bundles.append(Upgrade(
            unit=STOLEN_TECH_GROUP,
            buff_type=buff_type,
            name=f'Stolen Tech: {label}',
            description=(
                'Raised on ' + ', '.join(reached)
                + (
                    '. Not on ' + ', '.join(missing)
                    + ': that stat is not theirs to raise -- a unit with no '
                    'weapon has no fire rate, and one that carries nobody '
                    'has no room to spare.'
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


def draw_shelf(run, country, *, count=SHELF_SIZE, salt='shelf'):
    """Return the keys of the upgrades to offer for one battle.

    Drawn from the run's seed and its battle number, out of what the run
    does not already own.
    """
    upgrades = available_upgrades(
        country_upgrades(country),
        run.purchases if salt == 'shelf' else run.ally_purchases,
    )
    if not upgrades:
        return ()
    generator = random.Random(f'{run.seed}:{run.battle}:{salt}')
    return tuple(
        shelf_key(upgrade)
        for upgrade in generator.sample(upgrades, min(count, len(upgrades)))
    )


def shelf_key(upgrade):
    return f'{upgrade.unit}:{upgrade.buff_type}'


def shelf_for(run, country, *, count=SHELF_SIZE, salt='shelf'):
    """Return the upgrades standing on the shelf for this battle.

    The six the battle was given, in the order it was given them --
    including any already bought, which stay on the shelf marked as bought.
    A shelf that held only what you have not bought would reshuffle itself
    the moment you bought from it: six new names where the one you chose
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


def ally_shopping(run, country, coins):
    """Return what the ally buys with what it has, and what is left.

    The ally spends on its own, from its own country's list, and it spends
    what it has rather than saving: an ally that hoards is an ally that
    never gets better.
    """
    upgrades = available_upgrades(
        country_upgrades(country), run.ally_purchases
    )
    if not upgrades:
        return run.ally_purchases, coins
    generator = random.Random(f'{run.seed}:{run.battle}:ally')
    purchases = run.ally_purchases
    affordable = True
    while affordable:
        choices = [
            upgrade for upgrade in available_upgrades(upgrades, purchases)
            if upgrade.price <= coins
        ]
        if not choices:
            affordable = False
            continue
        chosen = generator.choice(choices)
        purchases = purchase_stacks(purchases, chosen)
        coins -= chosen.price
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
