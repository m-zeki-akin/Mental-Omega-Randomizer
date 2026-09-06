"""What a run can buy between battles.

Upgrades only, and only for the army the run plays: a Soviet run never sees
an Allied unit on its shelf. The ally shops too, out of its own earnings and
its own faction's list, so the two armies grow apart over a run without the
player spending anything on it.

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
BATTLE_REWARD = 150
REWARD_PER_TIER = 75
CHALLENGE_REWARD_MULTIPLIER = 2
STARTING_ORE = 200
# How many upgrades stand on the shelf between battles. The shelf is drawn
# from the run's seed, so it is the same shelf every time the run is opened.
SHELF_SIZE = 6


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


def battle_reward(battle, *, challenge=False):
    """Return the Ore a won battle pays."""
    tier = (max(1, int(battle)) - 1) // BATTLES_PER_TIER + 1
    reward = BATTLE_REWARD + REWARD_PER_TIER * (tier - 1)
    return reward * (CHALLENGE_REWARD_MULTIPLIER if challenge else 1)


@lru_cache(maxsize=8)
def faction_upgrades(side):
    """Return every upgrade this faction can buy, cheapest first.

    Reads the campaign shop's own catalogue. An upgrade the installation
    would not notice -- a speed buff on a unit a submod already has at the
    ceiling -- is not offered, which is the same clamp the campaign shop
    applies at its own offer time.

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
    from randomizer.shop.economy import run_buff_price

    from .clones import clonable
    from .rules import unit_rules

    installed = _installed_sections()

    wanted = str(side or '').strip().lower()
    upgrades = []
    for reward in UNIT_BUFF_REWARDS:
        factions = [
            str(faction).strip().lower()
            for faction in (reward.get('factions') or ())
        ]
        if wanted not in factions:
            continue
        unit = str(reward.get('unit') or '').upper()
        buff_type = str(reward.get('buff_type') or '')
        if not unit or not buff_type:
            continue
        limit = effective_stack_limit(
            unit, buff_type, buff_stack_limit(reward) or 1
        )
        if limit <= 0:
            continue
        if not unit_rules(unit, buff_type, 1, installed, BUFF_TARGETS):
            continue
        if not clonable(unit, installed, BUFF_TARGETS):
            continue
        effect = buff_effect_lines(
            reward, 1, include_label=False, include_stack=False
        )
        upgrades.append(Upgrade(
            unit=unit,
            buff_type=buff_type,
            name=str(reward.get('name') or f'{unit} {buff_type}'),
            description=str(reward.get('description') or ''),
            price=int(run_buff_price(unit)),
            limit=int(limit),
            effect=effect[0] if effect else buff_type.replace('_', ' '),
        ))
    return tuple(sorted(upgrades, key=lambda item: (item.price, item.name)))


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


def shelf_for(run, side, *, count=SHELF_SIZE, salt='shelf'):
    """Return the upgrades standing on the shelf for this battle.

    Drawn from the run's seed and its battle number, so the shelf is the
    same one every time the run is opened, and a new one each battle.
    """
    upgrades = available_upgrades(
        faction_upgrades(side),
        run.purchases if salt == 'shelf' else run.ally_purchases,
    )
    if not upgrades:
        return ()
    generator = random.Random(f'{run.seed}:{run.battle}:{salt}')
    return tuple(generator.sample(upgrades, min(count, len(upgrades))))


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


def ally_shopping(run, side, coins):
    """Return what the ally buys with what it has, and what is left.

    The ally spends on its own, from its own faction's list, and it spends
    what it has rather than saving: an ally that hoards is an ally that
    never gets better.
    """
    upgrades = available_upgrades(
        faction_upgrades(side), run.ally_purchases
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


def purchase_labels(purchases, side):
    """Return one readable line per purchase, for showing what was bought."""
    named = {upgrade.key: upgrade for upgrade in faction_upgrades(side)}
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
