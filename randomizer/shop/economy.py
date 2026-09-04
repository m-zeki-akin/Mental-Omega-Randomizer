"""Pure Shop Mode reward and price calculations."""

from fractions import Fraction

from .config import SHOP_CONFIG
from .model import (
    CurrencyReward,
    MissionEconomyClass,
    ShopModeConfig,
    ShopRewardType,
)
from .modifiers import modifier_effects


def stage_income_multiplier(stage, config: ShopModeConfig = SHOP_CONFIG):
    """Return the Ore multiplier for the tier a mission sits in.

    An endless run gets harder every tier: each challenge victory hands the AI
    two permanent buffs that never come off. Ore has to climb with that or the
    run shop falls behind what the missions demand. Gems are deliberately not
    scaled here; see mission_reward.
    """
    from .missions import difficulty_stage

    tier = difficulty_stage(stage, config)
    percent = max(0, int(config.stage_income_percent_per_stage))
    return 1 + Fraction(percent, 100) * (tier - 1)


def stage_gem_multiplier(stage, config: ShopModeConfig = SHOP_CONFIG):
    """Return the Gem multiplier for the tier a mission sits in.

    Gems climb more slowly than Ore and this rate is not player-facing.
    Ore has to keep the run shop level with the mission in front of it,
    while Gems buy permanent progression: letting a long run compound
    them at the same rate would make run length, rather than difficulty,
    the fastest way to advance the profile.
    """
    from .missions import difficulty_stage

    tier = difficulty_stage(stage, config)
    percent = max(0, int(config.stage_gem_income_percent_per_stage))
    return 1 + Fraction(percent, 100) * (tier - 1)


def _scaled(amount, multiplier):
    """Round a scaled currency amount half-up so payouts stay whole."""
    return int(Fraction(amount) * Fraction(multiplier) + Fraction(1, 2))


def _bounded_upgrade_level(config, upgrade_id, level):
    definition = config.permanent_upgrades[upgrade_id]
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 0
    return max(0, min(definition.max_level, level))


def mission_reward(
    mission_class,
    *,
    victory_coin_bonus_level=0,
    modifiers=(),
    successful=True,
    mission_modifier=None,
    challenge_hunter_level=0,
    stage=1,
    gem_scale_percent=100,
    config: ShopModeConfig = SHOP_CONFIG,
):
    """Return configured victory currency; failures always return zero."""
    if not successful:
        return CurrencyReward()
    try:
        class_id = MissionEconomyClass(mission_class)
    except ValueError as exc:
        raise ValueError(
            f'Unknown Shop Mode mission class: {mission_class!r}'
        ) from exc
    definition = config.mission_rewards[class_id]
    effects = modifier_effects(modifiers, config)
    base_run_coins = int(
        definition.run_coins * effects['run_reward_percent']
    )
    meta_coins = int(definition.meta_coins * effects['meta_reward_percent'])
    challenge = bool(getattr(mission_modifier, 'challenge', False))
    stage_multiplier = stage_income_multiplier(stage, config)
    challenge_multiplier = (
        Fraction(max(100, int(config.challenge_reward_multiplier_percent)), 100)
        if challenge else Fraction(1)
    )
    base_run_coins = _scaled(
        base_run_coins, stage_multiplier * challenge_multiplier
    )
    # Gems use their own, slower tier curve; see stage_gem_multiplier.
    meta_coins = _scaled(
        meta_coins,
        stage_gem_multiplier(stage, config) * challenge_multiplier,
    )
    if challenge:
        meta_coins = int(
            meta_coins * effects['challenge_meta_reward_percent']
        )
    else:
        base_run_coins = int(
            base_run_coins * effects['normal_run_reward_percent']
        )
    base_run_coins = max(0, base_run_coins + effects['run_reward_flat'])
    meta_coins = max(0, meta_coins + effects['meta_reward_flat'])
    # Pacing chosen at run start scales Gems only. Ore is the run's own
    # currency and is already governed by the stage multiplier; scaling it
    # twice would let an easy run out-shop a hard one inside the run too.
    meta_coins = _scaled(meta_coins, Fraction(int(gem_scale_percent), 100))
    level = _bounded_upgrade_level(
        config, 'victory_run_coin_bonus', victory_coin_bonus_level
    )
    per_level = config.permanent_upgrades[
        'victory_run_coin_bonus'
    ].effects['run_coins_per_level']
    victory_bonus = level * int(per_level)
    mission_bonus_run = max(
        0, int(getattr(mission_modifier, 'bonus_run_coins', 0))
    )
    mission_bonus_meta = max(
        0, int(getattr(mission_modifier, 'bonus_meta_coins', 0))
    )
    if getattr(mission_modifier, 'challenge', False):
        mission_bonus_meta = int(
            mission_bonus_meta * effects['challenge_meta_reward_percent']
        )
    hunter_level = _bounded_upgrade_level(
        config, 'challenge_hunter', challenge_hunter_level
    )
    hunter_effects = config.permanent_upgrades['challenge_hunter'].effects
    challenge_hunter_run = (
        hunter_level * int(hunter_effects['run_coins_per_level'])
        if getattr(mission_modifier, 'challenge', False) else 0
    )
    interval = max(1, int(hunter_effects['meta_coins_every_levels']))
    # Awards are counted in levels but paid in Gems, so the payout comes from
    # a configured amount rather than the level count itself.
    per_award = int(hunter_effects['meta_coins_per_award'])
    challenge_hunter_meta = (
        (hunter_level // interval) * per_award
        if getattr(mission_modifier, 'challenge', False) else 0
    )
    return CurrencyReward(
        run_coins=(
            base_run_coins + victory_bonus + mission_bonus_run
            + challenge_hunter_run
        ),
        meta_coins=(
            meta_coins + mission_bonus_meta + challenge_hunter_meta
        ),
        base_run_coins=base_run_coins,
        victory_bonus_run_coins=victory_bonus,
        mission_bonus_run_coins=mission_bonus_run,
        mission_bonus_meta_coins=mission_bonus_meta,
        challenge_hunter_run_coins=challenge_hunter_run,
        challenge_hunter_meta_coins=challenge_hunter_meta,
    )


def starting_run_coins(
    *,
    starting_capital_level=0,
    modifiers=(),
    config: ShopModeConfig = SHOP_CONFIG,
):
    level = _bounded_upgrade_level(
        config, 'starting_capital', starting_capital_level
    )
    per_level = config.permanent_upgrades['starting_capital'].effects[
        'run_coins_per_level'
    ]
    effects = modifier_effects(modifiers, config)
    if effects['no_starting_run_coins']:
        # Greedy's whole cost is the empty wallet. A +125 Ore modifier or a
        # bought capital ladder cancelling it would make the modifier free,
        # so this overrides the sum rather than joining it.
        return 0
    return min(
        config.maximum_starting_ore,
        max(
            0,
            config.starting_run_coins
            + level * int(per_level)
            + effects['starting_run_coins_flat'],
        ),
    )


def discounted_shop_price(
    base_price,
    *,
    shop_discount_level=0,
    modifiers=(),
    additional_discount_ore=0,
    config: ShopModeConfig = SHOP_CONFIG,
):
    try:
        base_price = int(base_price)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid Shop Mode base price: {base_price!r}') from exc
    if base_price < 0:
        raise ValueError(f'Invalid Shop Mode base price: {base_price!r}')
    effects = modifier_effects(modifiers, config)
    modified = (
        int(base_price * effects['shop_price_percent'])
        + effects['shop_price_flat']
    )
    level = _bounded_upgrade_level(
        config, 'shop_discount', shop_discount_level
    )
    ore_per_level = config.permanent_upgrades['shop_discount'].effects[
        'ore_per_level'
    ]
    discounted = (
        modified
        - level * int(ore_per_level)
        - max(0, int(additional_discount_ore))
    )
    return max(config.minimum_shop_price, discounted)


def run_unit_price(
    target_id,
    *,
    shop_discount_level=0,
    modifiers=(),
    config: ShopModeConfig = SHOP_CONFIG,
):
    base_price = _unit_target_price(config, target_id, 'run_access')
    return discounted_shop_price(
        base_price,
        shop_discount_level=shop_discount_level,
        modifiers=modifiers,
        config=config,
    )


def run_buff_price(
    target_id,
    *,
    shop_discount_level=0,
    modifiers=(),
    config: ShopModeConfig = SHOP_CONFIG,
):
    base_price = _unit_target_price(config, target_id, 'run_buff')
    return discounted_shop_price(
        base_price,
        shop_discount_level=shop_discount_level,
        modifiers=modifiers,
        config=config,
    )


def _unit_target_price(config, target_id, price_field):
    normalized_id = str(target_id).upper()
    definition = config.unit_target_prices.get(normalized_id)
    if definition is None:
        raise ValueError(
            f'Unknown Shop Mode unit price target: {target_id!r}'
        )
    price = getattr(definition, price_field)
    if price is None:
        raise ValueError(
            f'Shop Mode target {normalized_id!r} has no {price_field} price'
        )
    return int(price)


def _power_target_price(config, target_id, price_field):
    normalized_id = str(target_id).upper()
    definition = config.power_target_prices.get(normalized_id)
    if definition is None:
        raise ValueError(
            f'Unknown Shop Mode power price target: {target_id!r}'
        )
    price = getattr(definition, price_field)
    if price is None:
        raise ValueError(
            f'Shop Mode power {normalized_id!r} has no {price_field} price'
        )
    return int(price)


def permanent_unit_price(target_id, *, config: ShopModeConfig = SHOP_CONFIG):
    return _unit_target_price(config, target_id, 'permanent_access')


def permanent_buff_price(target_id, *, config: ShopModeConfig = SHOP_CONFIG):
    return _unit_target_price(config, target_id, 'permanent_buff')


def permanent_upgrade_price(
    upgrade_id,
    next_level,
    *,
    config: ShopModeConfig = SHOP_CONFIG,
):
    definition = config.permanent_upgrades.get(str(upgrade_id))
    if definition is None:
        raise ValueError(f'Unknown Shop Mode permanent upgrade: {upgrade_id!r}')
    try:
        next_level = int(next_level)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid Shop Mode upgrade level: {next_level!r}') from exc
    if not 1 <= next_level <= definition.max_level:
        raise ValueError(
            f'Shop Mode upgrade {upgrade_id!r} has no level {next_level}'
        )
    return definition.prices[next_level - 1]


def run_reward_price(
    entry,
    *,
    shop_discount_level=0,
    modifiers=(),
    specialization='',
    specialization_level=0,
    coupon_discount_ore=0,
    config: ShopModeConfig = SHOP_CONFIG,
):
    """Return one run-shop price, including all permanent discounts."""
    # ``specialization`` remains accepted for old callers and saved runs. Its
    # former category value is intentionally ignored: every level now applies
    # to units, buffs, and powers.
    del specialization
    specialization_level = _bounded_upgrade_level(
        config, 'discount_specialization', specialization_level
    )
    per_level = config.permanent_upgrades[
        'discount_specialization'
    ].effects['ore_per_level']
    extra_ore = (
        specialization_level * int(per_level)
        + max(0, int(coupon_discount_ore))
    )
    if entry.reward_type is ShopRewardType.UNIT_ACCESS:
        base_price = _unit_target_price(
            config, entry.target_id, 'run_access'
        )
    elif entry.reward_type is ShopRewardType.UNIT_BUFF:
        base_price = _unit_target_price(
            config, entry.target_id, 'run_buff'
        )
    elif entry.reward_type is ShopRewardType.POWER_ACCESS:
        base_price = _power_target_price(
            config, entry.target_id, 'run_access'
        )
    elif entry.reward_type is ShopRewardType.POWER_BUFF:
        base_price = _power_target_price(
            config, entry.target_id, 'run_buff'
        )
    else:
        raise ValueError(
            f'Unknown Shop Mode reward type: {entry.reward_type!r}'
        )
    return discounted_shop_price(
        base_price,
        shop_discount_level=shop_discount_level,
        modifiers=modifiers,
        additional_discount_ore=extra_ore,
        config=config,
    )
