"""Typed adapter for editable Shop Mode balance configuration."""

from dataclasses import replace

from randomizer.config.static import load_static_config

from .model import (
    MissionEconomyClass,
    MissionRewardDefinition,
    ModifierDefinition,
    PermanentUpgradeDefinition,
    EnemyBuffTier,
    ShopModeConfig,
    ShopPowerPriceDefinition,
    ShopTargetPriceDefinition,
    StageDifficultyProfile,
    StageScoreCeiling,
    StageWeightProfile,
)


def load_shop_mode_config() -> ShopModeConfig:
    sections = load_static_config('shop_mode.json')
    settings = sections['settings']
    mission_rewards = {
        MissionEconomyClass(class_id): MissionRewardDefinition(
            class_id=MissionEconomyClass(class_id),
            display_name=str(definition['display_name']),
            difficulty=int(definition['difficulty']),
            run_coins=int(definition['run_coins']),
            meta_coins=int(definition['meta_coins']),
        )
        for class_id, definition in sections['mission_rewards'].items()
    }
    stage_weights = tuple(
        StageWeightProfile(
            through_stage=int(profile['through_stage']),
            weights={
                MissionEconomyClass(class_id): int(weight)
                for class_id, weight in profile['weights'].items()
            },
        )
        for profile in sections['stage_class_weights']
    )
    stage_difficulty_weights = tuple(
        StageDifficultyProfile(
            through_stage=int(profile['through_stage']),
            weights={
                str(difficulty): int(weight)
                for difficulty, weight in profile['weights'].items()
            },
        )
        for profile in sections['stage_difficulty_weights']
    )
    stage_score_ceilings = tuple(
        StageScoreCeiling(
            through_stage=int(profile['through_stage']),
            maximum_stage_score=int(profile['maximum_stage_score']),
        )
        for profile in sections['stage_score_ceilings']
    )
    enemy_buff_stage_tiers = tuple(
        EnemyBuffTier(
            minimum_stage=int(tier['minimum_stage']),
            buff_ids=tuple(str(buff_id) for buff_id in tier['buff_ids']),
        )
        for tier in sections['enemy_buff_stage_tiers']
    )
    upgrades = {
        upgrade_id: PermanentUpgradeDefinition(
            id=upgrade_id,
            display_name=str(definition['display_name']),
            max_level=int(definition['max_level']),
            prices=tuple(int(price) for price in definition['prices']),
            effects={
                str(effect): int(value)
                for effect, value in definition['effects'].items()
            },
            purchasable=bool(definition.get('purchasable', True)),
        )
        for upgrade_id, definition in sections['permanent_upgrades'].items()
    }
    modifiers = {
        modifier_id: ModifierDefinition(
            id=modifier_id,
            display_name=str(definition['display_name']),
            description=str(definition['description']),
            effects={
                str(effect): int(value)
                for effect, value in definition['effects'].items()
            },
        )
        for modifier_id, definition in sections['modifiers'].items()
    }
    return ShopModeConfig(
        run_length=int(settings['run_length']),
        stage_length=int(settings['stage_length']),
        starting_lives=int(settings['starting_lives']),
        stage_income_percent_per_stage=int(
            settings['stage_income_percent_per_stage']
        ),
        challenge_reward_multiplier_percent=int(
            settings['challenge_reward_multiplier_percent']
        ),
        permanent_enemy_buffs_per_challenge=int(
            settings['permanent_enemy_buffs_per_challenge']
        ),
        mission_offer_count=int(settings['mission_offer_count']),
        unit_inventory_size=int(settings['unit_inventory_size']),
        power_inventory_size=int(settings['power_inventory_size']),
        max_selected_permanent_units=int(
            settings['max_selected_permanent_units']
        ),
        starting_run_coins=int(settings['starting_run_coins']),
        starting_rerolls=int(settings['starting_rerolls']),
        maximum_starting_ore=int(settings['maximum_starting_ore']),
        minimum_shop_price=int(settings['minimum_shop_price']),
        reroll_policy=str(settings['reroll_policy']),
        archipelago_purchase_locations=int(
            settings['archipelago_purchase_locations']
        ),
        archipelago_purchase_meta_coin_cost=int(
            settings['archipelago_purchase_meta_coin_cost']
        ),
        archipelago_mission_victories_are_locations=bool(
            settings['archipelago_mission_victories_are_locations']
        ),
        excluded_reward_ids=tuple(
            str(reward_id) for reward_id in settings['excluded_reward_ids']
        ),
        mission_rewards=mission_rewards,
        stage_class_weights=stage_weights,
        stage_difficulty_weights=stage_difficulty_weights,
        stage_score_ceilings=stage_score_ceilings,
        enemy_buff_stage_tiers=enemy_buff_stage_tiers,
        power_target_prices={
            str(target_id): ShopPowerPriceDefinition(
                run_access=definition['run_access'],
                run_buff=definition['run_buff'],
            )
            for target_id, definition
            in sections['power_target_prices'].items()
        },
        unit_target_prices={
            str(target_id): ShopTargetPriceDefinition(
                run_access=definition['run_access'],
                run_buff=definition['run_buff'],
                permanent_access=definition['permanent_access'],
                permanent_buff=definition['permanent_buff'],
            )
            for target_id, definition in sections['unit_target_prices'].items()
        },
        permanent_upgrades=upgrades,
        modifiers=modifiers,
    )


SHOP_CONFIG = load_shop_mode_config()

# Player-adjustable run pacing. Each entry is the reward_settings key, the
# ShopModeConfig field it overrides, and the inclusive range the launcher
# offers. The configured value is the baseline every run is measured against.
RUN_PACING_SETTINGS = {
    'shop_starting_lives': ('starting_lives', 1, 5),
    'shop_stage_income_percent': ('stage_income_percent_per_stage', 0, 100),
    'shop_enemy_buffs_per_challenge': (
        'permanent_enemy_buffs_per_challenge', 0, 4
    ),
    'shop_stage_length': ('stage_length', 2, 5),
    'shop_starting_ore': ('starting_run_coins', 0, 50),
    'shop_starting_rerolls': ('starting_rerolls', 0, 5),
}


def _bounded_setting(value, minimum, maximum, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, number))


def run_pacing_overrides(reward_settings, config: ShopModeConfig = SHOP_CONFIG):
    """Return the pacing fields a run overrides, clamped to their range."""
    settings = reward_settings or {}
    overrides = {}
    for key, (field, minimum, maximum) in RUN_PACING_SETTINGS.items():
        if key not in settings:
            continue
        baseline = getattr(config, field)
        value = _bounded_setting(settings.get(key), minimum, maximum, baseline)
        if value != baseline:
            overrides[field] = value
    return overrides


def run_shop_config(run, config: ShopModeConfig = SHOP_CONFIG):
    """Return the config a run actually plays under.

    Pacing choices live in reward_settings, which is already persisted per run
    and snapshotted at creation, so a run keeps the rules it started with even
    if the launcher defaults change underneath it.
    """
    if run is None:
        return config
    overrides = run_pacing_overrides(
        getattr(run, 'reward_settings', None), config
    )
    return replace(config, **overrides) if overrides else config
