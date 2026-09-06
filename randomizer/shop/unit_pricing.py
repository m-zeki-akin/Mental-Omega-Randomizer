"""What a unit or a power is worth, derived rather than tabulated.

Every Shop price used to come from a hand-written table keyed on the target
and scaled off the unit's in-game credit cost. Cost is the wrong axis. It
answers what a unit is worth to build once you already have it -- a question
the game prices every match -- while the shop is asking a different one: what
is it worth to *have* the unit at all, for the rest of this run and every run
after. That is decided by how far up the tech tree it sits and by whether
anyone else can field one.

So tier sets a band and cost only positions the unit inside it. A unit nobody
can build more than one of, or one that has to be stolen, is priced on its own
terms and ignores the band. Powers have no credit cost at all, so for them the
tier decides outright.

Ore and Gems are the same model at two scales, so both read one
``ShopPriceScale`` and differ only in its numbers.

Cost, category, build limit and stolen-tech status all come from the live
roster, so a submod that reprices a unit reprices its Shop price with it.
Tiers stay in configuration: unit tiers from the roster's TechLevel, power
tiers from ``power_target_prices``. Neither is in the unit data, and rebuilding
them from tech-building prerequisites is a great deal of work for a number that
rarely moves.
"""

from randomizer.rewards.definitions import BUFF_TARGETS
from randomizer.rewards.roster import randomizer_unit_template_values

from .config import SHOP_CONFIG
from .model import ShopModeConfig

# Categories whose build-limited members are hero units. A Cloning Vat and an
# Ore Purifier are also limited to one, and pricing them as heroes would be
# absurd, so buildings and defenses fall through to the ordinary tier band.
UNIQUE_INFANTRY_CATEGORIES = frozenset({'infantry'})
UNIQUE_UNIT_CATEGORIES = frozenset({'units', 'aircraft', 'ships'})
# Buildings and defenses. Build-limited members of these are not heroes, so
# they take neither of the flat hero prices -- but a Gem scale may still want
# one number for all of them rather than a band position.
BUILDING_CATEGORIES = frozenset({'defenses', 'special_buildings'})

# Derived tables, memoised. A config carries dictionaries and so cannot be an
# lru_cache key; entries are keyed on its identity and hold it alive so the id
# stays meaningful. Only two ever exist: the loaded config, and whatever a
# self-check builds with dataclasses.replace.
_CACHE = {}


def _template_value(values, key):
    for name, value in (values or {}).items():
        if name.lower() == key.lower():
            return value
    return None


def _installed_rules_sections():
    """Return the rules the installation actually loads, keyed by section.

    Read through the cameo module, which already resolves the chain the engine
    resolves: a loose rulesmo.ini in the game folder outranks everything, and
    among the archives the highest-numbered expandmo wins. Imported here
    rather than at module load so the shop package stays importable where
    there is no game folder at all.
    """
    try:
        from randomizer.ui.cameos import installed_rules_registry
        _superweapons, sections = installed_rules_registry(synchronous=True)
    except Exception:
        return {}
    return {
        str(name).upper(): {str(k).lower(): v for k, v in values.items()}
        for name, values in (sections or {}).items()
    }


def _int_value(text):
    try:
        return int(str(text or '').strip() or 0)
    except ValueError:
        return 0


def _unit_traits():
    """Return the facts pricing needs, per unit id.

    Cost, build limit and stolen-tech status come from the installed rules
    wherever the installation has a section under the unit's own id. This
    used to read a committed bake of stock Mental Omega, which drifted from
    what was installed: it put Tanya at 1,500 credits where the shipped rules
    say 2,500, Centurion at 3,000 against 5,000, and it carried BuildLimits
    belonging to the randomizer's own player clones rather than to the game.
    Pricing off it meant a submod, or a patch, repriced nothing.

    The rest come from the clone body, which is itself built from the
    installed rules -- ``clone_template`` covers the units whose reviewed
    identity is templated from a differently named section (YURIX2 from
    Purgatory's YURIX) and the six that exist only inside campaign maps.
    """
    cached = _CACHE.get('traits')
    if cached is not None:
        return cached
    templates = randomizer_unit_template_values()
    installed = _installed_rules_sections()
    traits = {}
    for unit_id, values in templates.items():
        unit_id = unit_id.upper()
        target = BUFF_TARGETS.get(unit_id) or {}
        section = installed.get(unit_id)
        if section is not None:
            cost = _int_value(section.get('cost'))
            build_limit = _int_value(section.get('buildlimit'))
            stolen = bool(
                str(section.get('prerequisite.stolentechs') or '').strip()
            )
            source = 'installed_rules'
        else:
            cost = _int_value(_template_value(values, 'Cost'))
            build_limit = _int_value(_template_value(values, 'BuildLimit'))
            stolen = bool(
                str(_template_value(values, 'Prerequisite.StolenTechs') or '')
                .strip()
            )
            source = 'clone_template'
        if cost <= 0:
            # BUFF_TARGETS carries a cost for anything buildable but not for
            # special buildings, and a Cloning Vat priced as though it were
            # free would sit at the bottom of its band for no reason.
            fallback = int(target.get('cost') or 0)
            if fallback > 0:
                cost, source = fallback, 'buff_targets'
        traits[unit_id] = {
            'cost': max(0, cost),
            'cost_source': source,
            'category': str(target.get('category') or ''),
            # Any build limit at all: a defense you may have three of is
            # still something the game refuses to let you spam.
            'unique': build_limit >= 1,
            'build_limit': build_limit,
            'stolen_tech': stolen,
        }
    _CACHE['traits'] = traits
    return traits


def installed_rules_section(target_id):
    """Return one unit's installed rules section, for reporting."""
    return _installed_rules_sections().get(str(target_id).upper(), {})


def unit_cost_sources():
    """Return how many units each cost source accounts for.

    A complete fallback and a correct read look identical from the outside,
    and a development run has no game folder, so the counts are reported
    rather than assumed.
    """
    counts = {}
    for values in _unit_traits().values():
        source = values.get('cost_source') or 'unknown'
        counts[source] = counts.get(source, 0) + 1
    return counts


def unit_pricing_traits(target_id):
    return _unit_traits().get(str(target_id).upper(), {})


def _unique_price(traits, scale):
    if not traits.get('unique'):
        return 0
    category = traits.get('category')
    if category in UNIQUE_INFANTRY_CATEGORIES:
        return int(scale.unique_infantry)
    if category in UNIQUE_UNIT_CATEGORIES:
        return int(scale.unique_unit)
    # A one-of-a-kind building is limited for balance, not because it is a
    # hero. It keeps its tier band.
    return 0


def _priced_by_band(traits, scale):
    """Return whether a unit takes a tier band rather than a flat price."""
    return not (_unique_price(traits, scale) or traits.get('stolen_tech'))


def one_off_target(target_id):
    """Return whether the game itself refuses to let you field many.

    A build limit at any number, or a unit that has to be stolen. What this
    is worth is worth for a run: you have the thing no one else has while it
    lives, which is what the Ore premium is charging for.
    """
    traits = unit_pricing_traits(target_id)
    return bool(traits.get('unique') or traits.get('stolen_tech'))


def reward_pool_target(target_id, config: ShopModeConfig = SHOP_CONFIG):
    """Return whether a Reward Pool group names this unit.

    A different kind of rare: not capped, simply absent from any skirmish
    game. What that is worth is worth forever, which is what the Gem
    multiplier is charging for. Read through the economy, which already
    derives the set; the import is deferred because economy reads this module
    at load.
    """
    from .economy import _surcharged_target_ids

    return str(target_id).upper() in _surcharged_target_ids(config)


def premium_target(target_id, config: ShopModeConfig = SHOP_CONFIG):
    """Return whether a unit is priced as rare, for either reason.

    The two reasons are charged separately -- see the two functions above --
    but they distort the tier cost window identically, so the window asks
    this one question. Their prices are why a tier's ordinary units looked
    cheap: a 10,000 credit superunit dragged its tier's window up and pushed
    everything else toward the bottom of the band.
    """
    return bool(
        one_off_target(target_id) or reward_pool_target(target_id, config)
    )


def _tier_cost_windows(scale, config: ShopModeConfig = SHOP_CONFIG):
    """Return the cost span each tier's band is stretched across.

    Measured per tier rather than across the whole roster. Tier 1 units are
    all cheap, so a single global window would push every one of them to the
    bottom of its band and throw away the distinction the band exists to draw.
    The extremes are trimmed so one 5,000 credit superunit cannot flatten the
    tier it sits in.
    """
    from .catalogue import shop_catalogue, unit_access_tier
    from .model import ShopRewardType

    key = ('windows', scale.name, id(config))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached[1]
    costs_by_tier = {}
    traits = _unit_traits()
    for entry in shop_catalogue():
        if entry.reward_type is not ShopRewardType.UNIT_ACCESS:
            continue
        unit = traits.get(entry.target_id, {})
        # One-offs do not take the band, so they must not stretch it either.
        # This is wider than "flat-priced": a Cloning Vat is band-priced and
        # costs 3,000 credits, and leaving it in dragged every ordinary Tier 3
        # unit toward the bottom of its range.
        if premium_target(entry.target_id, config):
            continue
        cost = unit.get('cost') or 0
        if cost > 0:
            costs_by_tier.setdefault(
                unit_access_tier(entry.target_id), []
            ).append(cost)
    windows = {}
    trim = max(0.0, min(0.4, float(scale.cost_window_trim_percent) / 100))
    for tier, costs in costs_by_tier.items():
        costs.sort()
        low = costs[min(len(costs) - 1, int(len(costs) * trim))]
        high = costs[max(0, int(round(len(costs) * (1 - trim))) - 1)]
        windows[tier] = (low, max(low, high))
    _CACHE[key] = (config, windows)
    return windows


def _cost_position(target_id, scale, config: ShopModeConfig = SHOP_CONFIG):
    """Return where a unit's cost falls inside its tier, from 0 to 1."""
    from .catalogue import unit_access_tier

    window = _tier_cost_windows(scale, config).get(unit_access_tier(target_id))
    cost = unit_pricing_traits(target_id).get('cost') or 0
    if not window or window[1] <= window[0] or cost <= 0:
        return 0.5
    return min(1.0, max(0.0, (cost - window[0]) / (window[1] - window[0])))


def _rounded(value, scale):
    step = max(1, int(scale.rounding_step))
    return max(step, int(round(value / step)) * step)


def _in_range(bounds, target_id, scale, config):
    """Return where in a price range a unit's credit cost puts it."""
    low, high = int(bounds[0]), int(bounds[1])
    if high <= low:
        return low
    position = _cost_position(target_id, scale, config)
    return _rounded(low + position * (high - low), scale)


def _require_offer(target_id, reward_type):
    from .catalogue import shop_offers_target

    if not shop_offers_target(target_id, reward_type):
        raise ValueError(
            f'Shop Mode has no {reward_type.value} offer for {target_id!r}'
        )


def _flat_override(target_id, scale, config):
    """Return a price that replaces the band outright, or 0.

    Two kinds of target are worth a number rather than a position. A unit no
    skirmish game offers is worth what owning it forever is worth, and that
    does not vary with the credit cost of a thing you cannot build. A
    build-limited building is the same argument one step down.

    A campaign-only building answers to the campaign rule, not the building
    one: being absent from every skirmish game is the stronger claim, and it
    is the one the player is buying past.
    """
    category = unit_pricing_traits(target_id).get('category')
    if reward_pool_target(target_id, config):
        by_category = (
            (UNIQUE_INFANTRY_CATEGORIES, scale.campaign_infantry),
            (UNIQUE_UNIT_CATEGORIES, scale.campaign_unit),
            (BUILDING_CATEGORIES, scale.campaign_building),
        )
        for categories, price in by_category:
            if category in categories and int(price) > 0:
                return int(price)
    if (
        category in BUILDING_CATEGORIES
        and unit_pricing_traits(target_id).get('unique')
        and int(scale.build_limited_building) > 0
    ):
        return int(scale.build_limited_building)
    return 0


def _access_value(target_id, scale, config):
    """Return what a unit is worth, whether or not it is for sale."""
    from .catalogue import unit_access_tier

    override = _flat_override(target_id, scale, config)
    if override:
        # A set price is set: the multipliers below exist to move a derived
        # number, and there is nothing derived left to move.
        return override
    traits = unit_pricing_traits(target_id)
    flat = _unique_price(traits, scale)
    if traits.get('stolen_tech'):
        # Stolen tech is a range of its own, positioned by cost like a band.
        # A scale that wants one number sets both ends to it.
        flat = max(flat, _in_range(
            scale.stolen_tech, target_id, scale, config
        ))
    if not flat:
        flat = _in_range(
            scale.tier_prices.get(
                unit_access_tier(target_id), scale.tier_prices['tier_1']
            ),
            target_id,
            scale,
            config,
        )
    if one_off_target(target_id):
        flat *= max(1, int(scale.premium_target_multiplier))
    if reward_pool_target(target_id, config):
        flat *= max(1, int(scale.reward_pool_multiplier))
    return flat


def unit_access_price(target_id, scale, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return what owning a unit outright costs on one currency's scale."""
    from .model import ShopRewardType

    _require_offer(target_id, ShopRewardType.UNIT_ACCESS)
    return _access_value(target_id, scale, config)


def _buff_price(access_price, scale):
    """Return one upgrade's price: a floor, plus a share of the target's.

    A pure share of what the unit is worth made the early shelf almost
    free -- a Humvee's optics at 18 Ore against a Barracuda's at 60, when
    both are one upgrade and one shelf slot to the player buying them. The
    floor is what an upgrade costs at all; the share is what improving an
    expensive thing costs on top. Together they compress the range without
    flattening it.
    """
    return max(1, int(round(
        scale.buff_flat_price
        + access_price * scale.buff_percent_of_access / 100
    )))


def unit_buff_price(target_id, scale, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return one upgrade stack's price for a unit.

    Priced off what the unit is worth even where the unit itself is not for
    sale: a Tier 1 starter has no access offer, and its upgrades still need a
    number.
    """
    from .model import ShopRewardType

    _require_offer(target_id, ShopRewardType.UNIT_BUFF)
    return _buff_price(_access_value(target_id, scale, config), scale)


def power_access_price(target_id, scale, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return what a superweapon or aid power costs.

    Powers have no credit cost to read, so tier decides outright. The ones the
    Reward Pool groups single out -- superweapons, and the campaign-only
    powers no skirmish game offers -- are flat and deliberately steep: they
    are what a run gets built around, not stock.
    """
    from .catalogue import power_access_tier, power_is_flagged

    if power_is_flagged(target_id, config=config):
        return int(scale.flagged_power_price)
    tier = power_access_tier(target_id, config=config)
    return int(
        scale.power_tier_prices.get(tier, scale.power_tier_prices['tier_1'])
    )


def power_buff_price(target_id, scale, *, config: ShopModeConfig = SHOP_CONFIG):
    return _buff_price(
        power_access_price(target_id, scale, config=config), scale
    )


def unit_access_price_reason(target_id, scale):
    """Return why a unit costs what it costs, in one short phrase.

    The old prices tracked in-game cost, so a player could read them off the
    unit they already knew. These do not, and a hero beside a rifleman is
    unexplained unless the shop says what it is charging for.
    """
    from .catalogue import unit_access_tier

    traits = unit_pricing_traits(target_id)
    reasons = []
    if _unique_price(traits, scale):
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


def unit_access_price_report(scale, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return every access target's price, for tooling and self-checks."""
    from .catalogue import shop_catalogue
    from .model import ShopRewardType

    return {
        entry.target_id: unit_access_price(entry.target_id, scale, config=config)
        for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
    }
