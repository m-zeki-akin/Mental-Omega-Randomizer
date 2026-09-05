"""Write the Shop price model out as CSV, inputs beside outputs.

Every price the Shop charges is derived: tier sets a range, the unit's credit
cost positions it inside, and two multipliers may sit on top. That is auditable
in principle and invisible in practice -- the launcher shows a number and a
one-line reason, which is no way to check whether the formula does what it
should across three hundred units.

So this writes the whole model out. ``price_scales.csv`` is the configured
bands, the shape a balance discussion starts from. ``unit_prices.csv`` is every
sellable unit with the inputs the formula read and the number it produced, in
that order, so a row can be recomputed by hand. ``power_prices.csv`` is the
same for powers, which have no cost to read and take their tier outright.

Run it against a real installation to audit real numbers, or the costs come
from the committed roster bake rather than the rules the game loads::

    MO_RANDOMIZER_GAME_ROOT="<game folder>" python tools/shop_price_audit.py
"""

import csv
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from randomizer.shop.catalogue import (  # noqa: E402
    power_access_tier,
    power_is_flagged,
    shop_catalogue,
    unit_access_tier,
)
from randomizer.shop.config import SHOP_CONFIG  # noqa: E402
from randomizer.shop.model import ShopRewardType  # noqa: E402
from randomizer.shop.unit_pricing import (  # noqa: E402
    _cost_position,
    _tier_cost_windows,
    _unique_price,
    installed_rules_section,
    one_off_target,
    power_access_price,
    power_buff_price,
    reward_pool_target,
    unit_access_price,
    unit_buff_price,
    unit_cost_sources,
    unit_pricing_traits,
)

SCALES = ('run_ore', 'permanent_gem')


def _plain(scale):
    """The same scale with both multipliers off, to show the base price."""
    return replace(scale, premium_target_multiplier=1, reward_pool_multiplier=1)


def _basis(target_id, scale):
    """Which of the model's four prices this unit took."""
    traits = unit_pricing_traits(target_id)
    if traits.get('stolen_tech'):
        return 'stolen_tech'
    flat = _unique_price(traits, scale)
    if flat == int(scale.unique_infantry):
        return 'unique_infantry'
    if flat == int(scale.unique_unit):
        return 'unique_unit'
    return 'tier_band'


def _optional(price_function, target_id, scale):
    try:
        return price_function(target_id, scale)
    except ValueError:
        return ''


def _multiplier(target_id, scale):
    factor = 1
    if one_off_target(target_id):
        factor *= int(scale.premium_target_multiplier)
    if reward_pool_target(target_id):
        factor *= int(scale.reward_pool_multiplier)
    return factor


def write_price_scales(path):
    rows = [[
        'scale', 'tier_1', 'tier_2', 'tier_3', 'unique_infantry',
        'unique_unit', 'stolen_tech', 'power_t1', 'power_t2', 'power_t3',
        'superweapon_or_campaign_power', 'upgrade_percent_of_access',
        'one_off_multiplier', 'reward_pool_multiplier', 'rounding_step',
        'cost_window_trim_percent',
    ]]
    for name in SCALES:
        scale = SHOP_CONFIG.price_scales[name]
        low, high = scale.stolen_tech
        rows.append([
            scale.name,
            *(
                '{}-{}'.format(*scale.tier_prices[tier])
                for tier in ('tier_1', 'tier_2', 'tier_3')
            ),
            scale.unique_infantry,
            scale.unique_unit,
            low if low == high else '{}-{}'.format(low, high),
            *(
                scale.power_tier_prices[tier]
                for tier in ('tier_1', 'tier_2', 'tier_3')
            ),
            scale.flagged_power_price,
            scale.buff_percent_of_access,
            scale.premium_target_multiplier,
            scale.reward_pool_multiplier,
            scale.rounding_step,
            scale.cost_window_trim_percent,
        ])
    _write(path, rows)


def write_unit_prices(path):
    ore = SHOP_CONFIG.price_scales['run_ore']
    gem = SHOP_CONFIG.price_scales['permanent_gem']
    windows = _tier_cost_windows(ore)
    targets = sorted({
        entry.target_id for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
    })
    rows = [[
        'target_id', 'name', 'category', 'tier', 'cost', 'cost_source',
        'build_limit', 'stolen_tech', 'reward_pool', 'one_off',
        'cost_window_low', 'cost_window_high', 'cost_position',
        'price_basis', 'ore_band_low', 'ore_band_high', 'ore_base',
        'ore_multiplier', 'ore_price', 'ore_upgrade',
        'gem_base', 'gem_multiplier', 'gem_price',
    ]]
    for target in targets:
        traits = unit_pricing_traits(target)
        tier = unit_access_tier(target)
        window = windows.get(tier, (0, 0))
        band = ore.tier_prices.get(tier, (0, 0))
        rows.append([
            target,
            installed_rules_section(target).get('name') or '',
            traits.get('category') or '',
            tier,
            traits.get('cost') or 0,
            traits.get('cost_source') or '',
            traits.get('build_limit') or 0,
            int(bool(traits.get('stolen_tech'))),
            int(reward_pool_target(target)),
            int(one_off_target(target)),
            window[0], window[1],
            round(_cost_position(target, ore), 4),
            _basis(target, ore),
            band[0], band[1],
            unit_access_price(target, _plain(ore)),
            _multiplier(target, ore),
            unit_access_price(target, ore),
            # A few units are sold without upgrades of their own.
            _optional(unit_buff_price, target, ore),
            unit_access_price(target, _plain(gem)),
            _multiplier(target, gem),
            unit_access_price(target, gem),
        ])
    _write(path, rows)


def write_power_prices(path):
    ore = SHOP_CONFIG.price_scales['run_ore']
    gem = SHOP_CONFIG.price_scales['permanent_gem']
    targets = sorted({
        entry.target_id for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.POWER_ACCESS
    })
    rows = [[
        'target_id', 'tier', 'flagged', 'ore_price', 'ore_upgrade',
        'gem_price',
    ]]
    for target in targets:
        rows.append([
            target,
            power_access_tier(target),
            int(power_is_flagged(target)),
            power_access_price(target, ore),
            power_buff_price(target, ore),
            power_access_price(target, gem),
        ])
    _write(path, rows)


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel opens it without mangling the unit names.
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        csv.writer(handle).writerows(rows)
    print('{}  ({} satir)'.format(path, len(rows) - 1))


def main(argv):
    out = Path(argv[1]).resolve() if len(argv) > 1 else ROOT / 'price_audit'
    write_price_scales(out / 'price_scales.csv')
    write_unit_prices(out / 'unit_prices.csv')
    write_power_prices(out / 'power_prices.csv')
    print('cost kaynaklari:', unit_cost_sources())
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
