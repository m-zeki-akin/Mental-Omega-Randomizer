"""Focused schema validation for editable Shop Mode balance data."""


def _is_nonempty_string(value):
    return isinstance(value, str) and bool(value)


def _validate_stage_profiles(
    profiles, expected_keys, profile_message, coverage_message, path, invalid
):
    """Check an absolute-stage weight ladder that saturates at the end.

    Profiles are ordered by ascending through_stage and the last one uses
    0, meaning it applies to every stage beyond the numbered ones. An
    endless run has no final stage to interpolate towards, so that
    saturating profile is what makes the ladder total.
    """
    previous_stage = 0
    for index, profile in enumerate(profiles):
        saturating = index == len(profiles) - 1
        if not isinstance(profile, dict):
            invalid(profile_message, path)
            continue
        through_stage = profile.get('through_stage')
        weights = profile.get('weights')
        if (
            not isinstance(through_stage, int)
            or isinstance(through_stage, bool)
            or (
                through_stage != 0
                if saturating
                else not previous_stage < through_stage
            )
            or not isinstance(weights, dict)
            or set(weights) != expected_keys
            or any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
                for value in weights.values()
            )
            or not any(weights.values())
        ):
            invalid(profile_message, path)
        if not saturating and isinstance(through_stage, int):
            previous_stage = through_stage
    if not profiles or not isinstance(profiles[-1], dict) or profiles[
        -1
    ].get('through_stage') != 0:
        invalid(coverage_message, path)


def _validate_stage_score_ceilings(sections, path, invalid):
    ceilings = sections['stage_score_ceilings']
    if not ceilings:
        invalid('Shop Mode stage score ceilings cannot be empty', path)
    previous_stage = 0
    previous_score = 0
    for index, profile in enumerate(ceilings):
        saturating = index == len(ceilings) - 1
        if not isinstance(profile, dict):
            invalid('Invalid Shop Mode stage score ceiling', path)
            continue
        through_stage = profile.get('through_stage')
        maximum = profile.get('maximum_stage_score')
        if (
            not isinstance(through_stage, int)
            or isinstance(through_stage, bool)
            or (
                through_stage != 0
                if saturating
                else not previous_stage < through_stage
            )
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or maximum < 0
            # A ceiling that drops would make a later stage offer easier
            # missions than the stage before it.
            or (not saturating and maximum < previous_score)
        ):
            invalid('Invalid Shop Mode stage score ceiling', path)
        if not saturating and isinstance(through_stage, int):
            previous_stage = through_stage
            if isinstance(maximum, int):
                previous_score = maximum
    if not ceilings or not isinstance(ceilings[-1], dict) or ceilings[
        -1
    ].get('through_stage') != 0:
        invalid(
            'Shop Mode stage score ceilings must end with a saturating '
            'profile',
            path,
        )


def _validate_enemy_buff_tiers(sections, path, invalid):
    tiers = sections['enemy_buff_stage_tiers']
    if not tiers:
        invalid('Shop Mode enemy buff tiers cannot be empty', path)
    seen_ids = set()
    previous_stage = 0
    for tier in tiers:
        if not isinstance(tier, dict):
            invalid('Invalid Shop Mode enemy buff tier', path)
            continue
        minimum_stage = tier.get('minimum_stage')
        buff_ids = tier.get('buff_ids')
        if (
            not isinstance(minimum_stage, int)
            or isinstance(minimum_stage, bool)
            or minimum_stage < 1
            or minimum_stage < previous_stage
            or not isinstance(buff_ids, list)
            or not buff_ids
            or any(not _is_nonempty_string(item) for item in buff_ids)
            or seen_ids.intersection(buff_ids)
        ):
            invalid('Invalid Shop Mode enemy buff tier', path)
            continue
        seen_ids.update(buff_ids)
        previous_stage = minimum_stage
    if not any(
        isinstance(tier, dict) and tier.get('minimum_stage') == 1
        for tier in tiers
    ):
        invalid(
            'Shop Mode enemy buff tiers must open at stage 1', path
        )


def _is_price_range(value):
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(
            isinstance(bound, int) and not isinstance(bound, bool)
            and bound >= 1
            for bound in value
        )
        and value[0] <= value[1]
    )


def _validate_price_scales(sections, path, invalid):
    """Check the two ladders every Shop price is derived from.

    Every field is load-bearing. A missing tier range silently reprices a
    third of the catalogue; an inverted one would make expensive units
    cheaper than cheap ones; a zero buff percentage would hand out upgrades
    for free.
    """
    scales = sections['price_scales']
    if not isinstance(scales, dict) or set(scales) != {
        'run_ore', 'permanent_gem'
    }:
        invalid(
            'Shop Mode price_scales must define run_ore and permanent_gem',
            path,
        )
    for name, scale in scales.items():
        tier_prices = scale.get('tier_prices') if isinstance(scale, dict) else None
        power_prices = (
            scale.get('power_tier_prices') if isinstance(scale, dict) else None
        )
        if (
            not isinstance(scale, dict)
            or scale.get('name') != name
            or not isinstance(tier_prices, dict)
            or set(tier_prices) != TIER_IDS
            or not all(
                _is_price_range(bounds) for bounds in tier_prices.values()
            )
            or not _is_price_range(scale.get('stolen_tech'))
            or not isinstance(power_prices, dict)
            or set(power_prices) != TIER_IDS
            or any(
                not isinstance(price, int) or isinstance(price, bool)
                or price < 1
                for price in power_prices.values()
            )
        ):
            invalid(f'Invalid Shop Mode price_scales.{name} ranges', path)
        if any(
            not isinstance(scale.get(key), int)
            or isinstance(scale.get(key), bool)
            or scale[key] < 1
            for key in (
                'unique_infantry', 'unique_unit', 'flagged_power_price',
                'buff_percent_of_access', 'rounding_step',
                'premium_target_multiplier', 'reward_pool_multiplier',
            )
        ):
            invalid(f'Invalid Shop Mode price_scales.{name} prices', path)
        # Flat prices that replace the band for one kind of target. Zero is
        # the way a scale says it has no such rule, which is why these are
        # checked apart from the prices that must be positive.
        if any(
            not isinstance(scale.get(key), int)
            or isinstance(scale.get(key), bool)
            or scale[key] < 0
            for key in (
                'build_limited_building', 'campaign_infantry',
                'campaign_unit', 'campaign_building',
            )
        ):
            invalid(f'Invalid Shop Mode price_scales.{name} flat prices', path)
        trim = scale.get('cost_window_trim_percent')
        if (
            not isinstance(trim, int) or isinstance(trim, bool)
            or not 0 <= trim <= 40
        ):
            invalid(f'Invalid Shop Mode price_scales.{name} cost window', path)
        # Tiers have to stay ordered, or the whole point of pricing by tier
        # is lost: a Tier 1 unit could cost more than a Tier 3 one.
        ordered = [tier_prices[tier] for tier in ('tier_1', 'tier_2', 'tier_3')]
        if any(
            higher[0] < lower[1]
            for lower, higher in zip(ordered, ordered[1:])
        ):
            invalid(
                f'Shop Mode price_scales.{name} tier ranges must not overlap '
                'downwards',
                path,
            )


TIER_IDS = frozenset({'tier_1', 'tier_2', 'tier_3'})


def validate_shop_mode_config(sections, path, invalid):
    mission_classes = {'act_1', 'act_2', 'operation', 'finale'}
    settings = sections['settings']
    integer_settings = {
        # Archipelago-only run length. The APWorld builds one location per
        # stage and validates 5..20, so keep this inside that window even
        # though standalone runs never end.
        'run_length': (5, 20),
        'stage_length': (1, 20),
        'starting_lives': (1, 10),
        'stage_income_percent_per_stage': (0, 200),
        'stage_gem_income_percent_per_stage': (0, 200),
        'challenge_reward_multiplier_percent': (100, 1000),
        'permanent_enemy_buffs_per_challenge': (0, 5),
        'enemy_buff_escalation_stages': (1, 100),
        'mission_offer_count': (1, 10),
        'unit_inventory_size': (1, 100),
        'power_inventory_size': (1, 100),
        'upgrade_inventory_size': (0, 100),
        'mission_upgrade_reward_count': (0, 10),
        'mission_unit_gift_count': (0, 10),
        'max_selected_permanent_units': (0, 100),
        'starting_run_coins': (0, 1000000),
        'starting_rerolls': (0, 20),
        'maximum_starting_ore': (1, 1000000),
        'minimum_shop_price': (1, 1000000),
        'archipelago_purchase_locations': (0, 25),
        'archipelago_purchase_meta_coin_cost': (1, 1000000),
    }
    for key, (minimum, maximum) in integer_settings.items():
        value = settings.get(key)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not minimum <= value <= maximum
        ):
            invalid(f'Invalid Shop Mode setting {key!r}', path)
    stage_length = settings.get('stage_length')
    run_length = settings.get('run_length')
    if (
        isinstance(stage_length, int)
        and not isinstance(stage_length, bool)
        and stage_length > 0
        and isinstance(run_length, int)
        and not isinstance(run_length, bool)
        and run_length % stage_length
    ):
        invalid(
            'Shop Mode run_length must be a whole number of stages',
            path,
        )
    if settings.get('reroll_policy') != 'per_run':
        invalid('Shop Mode reroll_policy must be "per_run"', path)
    if not isinstance(
        settings.get('archipelago_mission_victories_are_locations'), bool
    ):
        invalid(
            'Shop Mode archipelago_mission_victories_are_locations must be '
            'a boolean',
            path,
        )
    excluded_reward_ids = settings.get('excluded_reward_ids')
    if (
        not isinstance(excluded_reward_ids, list)
        or any(not _is_nonempty_string(item) for item in excluded_reward_ids)
        or len(excluded_reward_ids) != len(set(excluded_reward_ids))
    ):
        invalid('Invalid Shop Mode excluded_reward_ids', path)

    rewards = sections['mission_rewards']
    if set(rewards) != mission_classes:
        invalid('Shop Mode mission reward classes are incomplete', path)
    difficulties = []
    for class_id, definition in rewards.items():
        if not isinstance(definition, dict):
            invalid(f'Invalid Shop Mode mission reward {class_id!r}', path)
        if not _is_nonempty_string(definition.get('display_name')):
            invalid(
                f'Invalid Shop Mode mission reward field '
                f'{class_id}.display_name',
                path,
            )
        for key in ('difficulty', 'run_coins', 'meta_coins'):
            value = definition.get(key)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < (1 if key == 'difficulty' else 0)
            ):
                invalid(
                    f'Invalid Shop Mode mission reward field {class_id}.{key}',
                    path,
                )
        difficulties.append(definition['difficulty'])
    if len(set(difficulties)) != len(mission_classes):
        invalid('Shop Mode mission difficulties must be unique', path)
    ordered_rewards = sorted(
        rewards.values(), key=lambda definition: definition['difficulty']
    )
    if any(
        harder['meta_coins'] <= easier['meta_coins']
        for easier, harder in zip(ordered_rewards, ordered_rewards[1:])
    ):
        invalid(
            'Shop Mode Gem rewards must increase with difficulty',
            path,
        )

    profiles = sections['stage_class_weights']
    if not profiles:
        invalid('Shop Mode stage class weights cannot be empty', path)
    _validate_stage_profiles(
        profiles,
        mission_classes,
        'Invalid Shop Mode stage weight profile',
        'Shop Mode stage weights must end with a saturating profile',
        path,
        invalid,
    )

    difficulty_names = {'Casual', 'Normal', 'Mental'}
    difficulty_profiles = sections['stage_difficulty_weights']
    if not difficulty_profiles:
        invalid('Shop Mode stage difficulty weights cannot be empty', path)
    _validate_stage_profiles(
        difficulty_profiles,
        difficulty_names,
        'Invalid Shop Mode stage difficulty profile',
        'Shop Mode stage difficulty weights must end with a saturating '
        'profile',
        path,
        invalid,
    )
    if not any(
        isinstance(profile, dict)
        and isinstance(profile.get('weights'), dict)
        and profile['weights'].get('Mental')
        for profile in difficulty_profiles
    ):
        invalid(
            'Shop Mode stage difficulty weights must enable Mental '
            'difficulty',
            path,
        )

    _validate_stage_score_ceilings(sections, path, invalid)
    _validate_enemy_buff_tiers(sections, path, invalid)

    power_prices = sections['power_target_prices']
    if not power_prices:
        invalid('Shop Mode power_target_prices cannot be empty', path)
    for target_id, prices in power_prices.items():
        if (
            not _is_nonempty_string(target_id)
            or target_id != target_id.upper()
            or not isinstance(prices, dict)
            or set(prices) != {'tier'}
            or prices['tier'] not in TIER_IDS
        ):
            invalid(
                f'Invalid Shop Mode power_target_prices.{target_id}', path
            )

    _validate_price_scales(sections, path, invalid)

    required_upgrades = {
        'mission_reroll': ('rerolls_per_level',),
        'mission_difficulty_assist': ('assists_per_level',),
        'victory_run_coin_bonus': ('run_coins_per_level',),
        'starting_capital': ('run_coins_per_level',),
        'mission_starting_credits': ('credits_per_level',),
        'shop_discount': ('ore_per_level',),
        'extra_shop_stock': ('units_per_level', 'powers_per_level'),
        'expanded_loadout': ('slots_per_level',),
        'emergency_revival': ('lives_per_level',),
        'free_buff_token': ('tokens_per_level',),
        'challenge_hunter': (
            'run_coins_per_level', 'meta_coins_every_levels',
            'meta_coins_per_award',
        ),
        'recovery_salvage': ('ore_per_level', 'maximum_saved_ore'),
        'starting_buff_draft': ('buffs_per_level',),
        'discount_specialization': ('ore_per_level',),
        'coupon_book': ('ore_per_level',),
        'stock_lock': ('locks_per_stage',),
        'veteran_academy': ('veteran_loadout',),
        'premium_supplier': ('minimum_stage', 'guaranteed_offers'),
    }
    upgrades = sections['permanent_upgrades']
    if not set(required_upgrades).issubset(upgrades):
        invalid('Shop Mode permanent upgrades are incomplete', path)
    for upgrade_id, definition in upgrades.items():
        if not _is_nonempty_string(upgrade_id) or not isinstance(definition, dict):
            invalid(f'Invalid Shop Mode upgrade {upgrade_id!r}', path)
        maximum = definition.get('max_level')
        prices = definition.get('prices')
        effects = definition.get('effects')
        if (
            not _is_nonempty_string(definition.get('display_name'))
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or maximum < 1
            or not isinstance(prices, list)
            or len(prices) != maximum
            or any(
                not isinstance(price, int)
                or isinstance(price, bool)
                or price < 1
                for price in prices
            )
            or not isinstance(effects, dict)
            or not isinstance(definition.get('purchasable', True), bool)
        ):
            invalid(f'Invalid Shop Mode upgrade {upgrade_id!r}', path)
        for effect_key in required_upgrades.get(upgrade_id, ()):
            if (
                not isinstance(effects.get(effect_key), int)
                or isinstance(effects.get(effect_key), bool)
                or effects[effect_key] < 1
            ):
                invalid(
                    f'Invalid Shop Mode upgrade effect '
                    f'{upgrade_id}.{effect_key}',
                    path,
                )

    mission_effects = sections['mission_effects']
    if not mission_effects:
        invalid('Shop Mode mission_effects cannot be empty', path)
    for effect_id, definition in mission_effects.items():
        player_rewards = (
            definition.get('player_reward_ids')
            if isinstance(definition, dict) else None
        )
        enemy_reward = (
            definition.get('enemy_reward_id', '')
            if isinstance(definition, dict) else ''
        )
        exclusive_rewards = (
            definition.get('exclusive_reward_ids', [])
            if isinstance(definition, dict) else None
        )
        if (
            not _is_nonempty_string(effect_id)
            or not isinstance(definition, dict)
            or not _is_nonempty_string(definition.get('title'))
            or not _is_nonempty_string(definition.get('description'))
            or not isinstance(definition.get('bonus_run_coins'), int)
            or isinstance(definition.get('bonus_run_coins'), bool)
            or definition['bonus_run_coins'] < 0
            or not isinstance(definition.get('bonus_meta_coins'), int)
            or isinstance(definition.get('bonus_meta_coins'), bool)
            or definition['bonus_meta_coins'] < 0
            or player_rewards is not None and (
                not isinstance(player_rewards, list)
                or not player_rewards
                or any(not _is_nonempty_string(item) for item in player_rewards)
            )
            or enemy_reward and not _is_nonempty_string(enemy_reward)
            or bool(player_rewards) == bool(enemy_reward)
            or not isinstance(exclusive_rewards, list)
            or any(not _is_nonempty_string(item) for item in exclusive_rewards)
            or len(exclusive_rewards) != len(set(exclusive_rewards))
            or exclusive_rewards and not player_rewards
            or not isinstance(definition.get('buffs_allied_helpers', False), bool)
        ):
            invalid(f'Invalid Shop Mode mission effect {effect_id!r}', path)

    allowed_modifier_effects = {
        'starting_run_coins_flat',
        'no_starting_run_coins',
        'run_reward_percent',
        'run_reward_flat',
        'meta_reward_percent',
        'meta_reward_flat',
        'shop_price_percent',
        'shop_price_flat',
        'hidden_offer_count',
        'player_damage_percent',
        'player_armor_percent',
        'production_time_percent',
        'combat_production_time_percent',
        'player_cost_percent',
        'support_recharge_percent',
        'unit_inventory_flat',
        'power_inventory_flat',
        'starter_veteran',
        'starter_unit_count_flat',
        'disable_rerolls',
        'disable_assists',
        'disable_revivals',
        'mission_starting_credits_flat',
        'mission_offer_count_flat',
        'liquidate_ore_after_victory',
        'challenge_meta_reward_percent',
        'normal_run_reward_percent',
    }
    percent_flat_pairs = {
        'run_reward_percent': 'run_reward_flat',
        'meta_reward_percent': 'meta_reward_flat',
        'shop_price_percent': 'shop_price_flat',
    }
    for modifier_id, definition in sections['modifiers'].items():
        effects = definition.get('effects') if isinstance(definition, dict) else None
        has_benefit = bool(isinstance(effects, dict) and (
            effects.get('starting_run_coins_flat', 0) > 0
            or effects.get('run_reward_flat', 0) > 0
            or effects.get('meta_reward_flat', 0) > 0
            or effects.get('run_reward_percent', 100) > 100
            or effects.get('meta_reward_percent', 100) > 100
            or effects.get('shop_price_percent', 100) < 100
            or effects.get('shop_price_flat', 0) < 0
            or effects.get('player_damage_percent', 100) > 100
            or effects.get('production_time_percent', 100) < 100
            or effects.get('unit_inventory_flat', 0) > 0
            or effects.get('power_inventory_flat', 0) > 0
            or effects.get('starter_veteran', 0) > 0
            or effects.get('support_recharge_percent', 100) < 100
            or effects.get('challenge_meta_reward_percent', 100) > 100
        ))
        has_penalty = bool(isinstance(effects, dict) and (
            effects.get('starting_run_coins_flat', 0) < 0
            or effects.get('no_starting_run_coins', 0) > 0
            or effects.get('run_reward_flat', 0) < 0
            or effects.get('meta_reward_flat', 0) < 0
            or effects.get('run_reward_percent', 100) < 100
            or effects.get('meta_reward_percent', 100) < 100
            or effects.get('shop_price_percent', 100) > 100
            or effects.get('shop_price_flat', 0) > 0
            or effects.get('hidden_offer_count', 0) > 0
            or effects.get('player_armor_percent', 100) < 100
            or effects.get('player_cost_percent', 100) > 100
            or effects.get('production_time_percent', 100) > 100
            or effects.get('combat_production_time_percent', 100) > 100
            or effects.get('starter_unit_count_flat', 0) < 0
            or effects.get('disable_rerolls', 0) > 0
            or effects.get('disable_assists', 0) > 0
            or effects.get('disable_revivals', 0) > 0
            or effects.get('mission_starting_credits_flat', 0) < 0
            or effects.get('mission_offer_count_flat', 0) < 0
            or effects.get('liquidate_ore_after_victory', 0) > 0
            or effects.get('normal_run_reward_percent', 100) < 100
        ))
        mixes_percent_and_flat = bool(isinstance(effects, dict) and any(
            effects.get(percent_key, 100) != 100
            and effects.get(flat_key, 0) != 0
            for percent_key, flat_key in percent_flat_pairs.items()
        ))
        if (
            not _is_nonempty_string(modifier_id)
            or not isinstance(definition, dict)
            or not _is_nonempty_string(definition.get('display_name'))
            or not _is_nonempty_string(definition.get('description'))
            or not isinstance(effects, dict)
            or not effects
            or not set(effects).issubset(allowed_modifier_effects)
            or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in effects.values()
            )
            or any(
                key.endswith('_percent') and value < 0
                for key, value in effects.items()
            )
            or not 0 <= effects.get('hidden_offer_count', 0) <= settings.get(
                'mission_offer_count', 0
            )
            or not has_benefit
            or not has_penalty
            or mixes_percent_and_flat
        ):
            invalid(f'Invalid Shop Mode modifier {modifier_id!r}', path)

    # Optional shelf filters the player ticks before a run. That every id
    # names something the shop could otherwise sell is checked in
    # randomizer/shop/catalogue.py: unit prices are derived now, so the
    # catalogue is the only place that still knows what is sellable.
    group_settings = set()
    claimed_targets = set()
    for group_id, definition in sections['reward_exclusion_groups'].items():
        target_ids = (
            definition.get('target_ids') if isinstance(definition, dict) else None
        )
        setting_key = (
            definition.get('setting_key') if isinstance(definition, dict) else None
        )
        if (
            not _is_nonempty_string(group_id)
            or not isinstance(definition, dict)
            or not _is_nonempty_string(setting_key)
            or setting_key in group_settings
            or not _is_nonempty_string(definition.get('display_name'))
            or not _is_nonempty_string(definition.get('description'))
            or not isinstance(target_ids, list)
            or not target_ids
            or any(not _is_nonempty_string(item) for item in target_ids)
            or len(target_ids) != len(set(target_ids))
            or claimed_targets.intersection(target_ids)
        ):
            invalid(
                f'Invalid Shop Mode reward exclusion group {group_id!r}', path
            )
        group_settings.add(setting_key)
        claimed_targets.update(target_ids)
