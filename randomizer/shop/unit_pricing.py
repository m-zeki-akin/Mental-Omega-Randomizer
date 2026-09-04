"""What a unit is worth in Gems, derived rather than tabulated.

Permanent access used to carry a hand-written Gem price per unit, scaled off
the unit's in-game cost with an 80 Gem floor. Cost is the wrong axis. It says
what a unit is worth to build once you already have it, which is a question
the game answers every match; the shop is answering a different one -- what it
is worth to *have* the unit at all, for the rest of the run and every run
after. That is decided by how far up the tech tree it sits and by whether
anyone else can field it, not by its price tag.

So tier sets the band and cost only positions the unit inside it. A unit
nobody can build more than one of, or one that has to be stolen, is priced on
its own terms and ignores the band entirely.

Everything except the tier is read from the live roster data, so a submod that
reprices a unit reprices its Gem cost with it. Tiers stay in configuration:
they are not in the unit data, and reconstructing them from tech-building
prerequisites is a great deal of work for a number that rarely moves.
"""

from functools import lru_cache

from randomizer.rewards.definitions import BUFF_TARGETS
from randomizer.rewards.roster import randomizer_unit_template_values

from .config import SHOP_CONFIG
from .model import ShopModeConfig

# Categories whose build-limited members are hero units. A Cloning Vat and an
# Ore Purifier are also limited to one, and pricing them as heroes would be
# absurd, so buildings and defenses fall through to the ordinary tier band.
UNIQUE_INFANTRY_CATEGORIES = frozenset({'infantry'})
UNIQUE_UNIT_CATEGORIES = frozenset({'units', 'aircraft', 'ships'})


def _template_value(values, key):
    for name, value in (values or {}).items():
        if name.lower() == key.lower():
            return value
    return None


@lru_cache(maxsize=1)
def _unit_traits():
    """Return the roster facts pricing needs, per unit id."""
    templates = randomizer_unit_template_values()
    traits = {}
    for unit_id, values in templates.items():
        target = BUFF_TARGETS.get(unit_id.upper()) or {}
        try:
            build_limit = int(
                str(_template_value(values, 'BuildLimit') or '').strip() or 0
            )
        except ValueError:
            build_limit = 0
        cost = target.get('cost')
        traits[unit_id.upper()] = {
            'cost': int(cost) if cost else 0,
            'category': str(target.get('category') or ''),
            'unique': build_limit == 1,
            'stolen_tech': bool(
                str(_template_value(values, 'Prerequisite.StolenTechs') or '')
                .strip()
            ),
        }
    return traits


def unit_pricing_traits(target_id):
    return _unit_traits().get(str(target_id).upper(), {})


def _unique_gems(traits, pricing):
    if not traits.get('unique'):
        return 0
    category = traits.get('category')
    if category in UNIQUE_INFANTRY_CATEGORIES:
        return int(pricing.unique_infantry_gems)
    if category in UNIQUE_UNIT_CATEGORIES:
        return int(pricing.unique_unit_gems)
    # A one-of-a-kind building is limited for balance, not because it is a
    # hero. It keeps its tier band.
    return 0


# A config carries dictionaries and so cannot be an lru_cache key. Keyed on
# identity instead, holding the config alive so the id stays meaningful.
_TIER_COST_WINDOWS = {}


def _tier_cost_windows(config: ShopModeConfig = SHOP_CONFIG):
    """Return the cost span each tier's band is stretched across.

    Measured per tier rather than across the whole roster. Tier 1 units are
    all cheap, so a single global window would push every one of them to the
    bottom of its band and throw away the distinction the band exists to
    draw. Outliers are trimmed to a percentile so one 5,000 credit superunit
    cannot flatten the tier it sits in.
    """
    from .catalogue import shop_catalogue, unit_access_tier
    from .model import ShopRewardType

    cached = _TIER_COST_WINDOWS.get(id(config))
    if cached is not None:
        return cached[1]
    costs_by_tier = {}
    traits = _unit_traits()
    pricing = config.unit_access_gem_pricing
    for entry in shop_catalogue():
        if entry.reward_type is not ShopRewardType.UNIT_ACCESS:
            continue
        unit = traits.get(entry.target_id, {})
        # Units priced on their own terms are not part of the band, so they
        # must not stretch it either.
        if _unique_gems(unit, pricing) or unit.get('stolen_tech'):
            continue
        cost = unit.get('cost') or 0
        if cost > 0:
            costs_by_tier.setdefault(unit_access_tier(entry.target_id), []).append(cost)
    windows = {}
    trim = max(0.0, min(0.4, float(pricing.cost_window_trim_percent) / 100))
    for tier, costs in costs_by_tier.items():
        costs.sort()
        low = costs[min(len(costs) - 1, int(len(costs) * trim))]
        high = costs[max(0, int(round(len(costs) * (1 - trim))) - 1)]
        windows[tier] = (low, max(low, high))
    _TIER_COST_WINDOWS[id(config)] = (config, windows)
    return windows


def _cost_position(target_id, tier, config: ShopModeConfig = SHOP_CONFIG):
    """Return where a unit's cost falls inside its tier, from 0 to 1."""
    window = _tier_cost_windows(config).get(tier)
    cost = unit_pricing_traits(target_id).get('cost') or 0
    if not window or window[1] <= window[0] or cost <= 0:
        # No cost in the roster data -- a few special buildings have none --
        # so the unit sits in the middle of its band rather than at the
        # bottom, which would read as a discount it has not earned.
        return 0.5
    return min(1.0, max(0.0, (cost - window[0]) / (window[1] - window[0])))


def unit_access_gem_price(target_id, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return the permanent Gem price for owning one unit outright."""
    from .catalogue import unit_access_tier

    pricing = config.unit_access_gem_pricing
    traits = unit_pricing_traits(target_id)
    flat = max(
        _unique_gems(traits, pricing),
        int(pricing.stolen_tech_gems) if traits.get('stolen_tech') else 0,
    )
    if flat:
        return flat
    tier = unit_access_tier(target_id)
    band = int(pricing.tier_gems.get(tier, pricing.tier_gems['tier_1']))
    low = int(pricing.cost_adjustment_minimum)
    high = int(pricing.cost_adjustment_maximum)
    adjustment = low + _cost_position(target_id, tier, config) * (high - low)
    step = max(1, int(pricing.rounding_step))
    return max(step, int(round((band + adjustment) / step)) * step)


def unit_access_gem_price_reason(target_id, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return why a unit costs what it costs, in one short phrase.

    The old prices tracked in-game cost, so a player could read them off the
    unit they knew. These do not, and a hero at 500 Gems beside a rifleman at
    90 is unexplained unless the shop says what it is charging for.
    """
    from .catalogue import unit_access_tier

    pricing = config.unit_access_gem_pricing
    traits = unit_pricing_traits(target_id)
    reasons = []
    if _unique_gems(traits, pricing):
        reasons.append(
            'Hero infantry'
            if traits.get('category') in UNIQUE_INFANTRY_CATEGORIES
            else 'Hero unit'
        )
    if traits.get('stolen_tech'):
        reasons.append('Stolen tech')
    if reasons:
        return ' / '.join(reasons) + ' -- flat price, tier does not apply'
    tier = unit_access_tier(target_id).replace('_', ' ').title()
    cost = traits.get('cost') or 0
    return (
        f'{tier} band'
        + (f', adjusted for its {cost} credit cost' if cost else '')
    )


def unit_access_gem_price_report(*, config: ShopModeConfig = SHOP_CONFIG):
    """Return every access target's Gem price, for tooling and self-checks."""
    from .catalogue import shop_catalogue
    from .model import ShopRewardType

    return {
        entry.target_id: unit_access_gem_price(entry.target_id, config=config)
        for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
    }
