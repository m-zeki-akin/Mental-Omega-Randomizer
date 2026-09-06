"""Focused executable contracts for Shop Mode domain and persistence."""

from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from randomizer.config.schema import StaticConfigError, validate_sections
from randomizer.config.static import load_static_config
from randomizer.core.storage import (
    OPAQUE_MAGIC,
    atomic_write_json,
    atomic_write_text,
    read_opaque_object,
)
from randomizer.missions.tier_one import (
    _tier_one_airfield_rules,
    tier_one_defense_ids,
    tier_one_unit_ids,
)
from randomizer.maps.shop_modifiers import apply_shop_clone_modifiers
from randomizer.rewards.catalogue import REWARD_BY_NAME
from randomizer.rewards.rules import tech_ids_for_rewards
from randomizer.ui.cameos import (
    ARCHIPELAGO_CAMEO_PATH,
    ensure_superweapon_cameos,
    ensure_unit_cameos,
)

from .catalogue import (
    DEFAULT_BUFF_DRAW_WEIGHT,
    buff_draw_weights,
    power_access_tier,
    power_is_flagged,
    canonical_reward_for_id,
    run_excluded_target_ids,
    shop_catalogue,
    shop_catalogue_by_reward_id,
    shop_entry_available,
    unit_access_tier,
)
from .active import (
    active_shop_power_ids,
    active_shop_rewards,
    active_shop_starter_defense_ids,
    active_shop_starter_unit_ids,
    active_shop_tech_ids,
)
from .archipelago import (
    ap_unit_entitlement_ids,
    archipelago_shop_identity,
    shop_reward_ids_from_ap_ledger,
)
from .archipelago_purchases import (
    archipelago_purchase_placement_text,
    archipelago_purchase_records,
)
from .config import (
    MODIFIER_SETTING_KEY,
    PACING_SETTING_KEY,
    RUN_PACING_SETTINGS,
    SHOP_CONFIG,
    configured_modifiers,
    configured_pacing,
    pacing_to_store,
)
from .economy import (
    discounted_shop_price,
    mission_reward,
    permanent_target_surcharged,
    permanent_unit_price,
    run_buff_price,
    run_unit_price,
    run_reward_price,
    starting_run_coins,
)
from .meta import (
    PERMANENT_PURCHASE_LOCKED_MESSAGE,
    permanent_purchase_block_reason,
    purchase_permanent_unit,
    purchase_permanent_upgrade,
    validate_starting_loadout,
)
from .inventory import (
    guarantee_premium_offer,
    preserve_locked_offer,
    rotating_power_inventory,
    rotating_unit_inventory,
)
from .missions import (
    enemy_buffs_for_stage,
    is_challenge_stage,
    classify_mission,
    generate_mission_offers,
    mission_classes_for_stage,
    mission_difficulty,
    mission_difficulty_weights_for_stage,
)
from .mission_modifiers import (
    MISSION_MODIFIERS,
    mission_modifier_for_offer,
    mission_modifier_for_run_offer,
)
from .modifiers import (
    hidden_offer_codes,
    modifier_difficulty,
    modifier_effects,
    modifier_mission_offer_count,
)
from .model import (
    SHOP_ACCESS_REWARD_MODE,
    SHOP_RUN_COLLECTION_SCHEMA_VERSION,
    BuffPurchase,
    MissionEconomyClass,
    MissionOffer,
    PurchaseRecord,
    PurchaseResult,
    RunStatus,
    ShopProfile,
    ShopCatalogueEntry,
    ShopRewardType,
    ShopRun,
)
from .purchases import apply_validated_run_purchase, validate_run_purchase
from .unit_pricing import (
    UNIQUE_INFANTRY_CATEGORIES,
    UNIQUE_UNIT_CATEGORIES,
    _flat_override,
    one_off_target,
    power_access_price,
    premium_target,
    reward_pool_target,
    unit_cost_sources,
    unit_access_price,
    unit_access_price_report,
    unit_buff_price,
    unit_pricing_traits,
)


def _plain_scale(scale):
    """The scale with its multipliers off, to show what they multiplied."""
    return replace(scale, premium_target_multiplier=1, reward_pool_multiplier=1)


def _model_scale(scale):
    """The scale with every override off: the derived model, on its own.

    Band membership, the flat hero prices and tier ordering are all claims
    about how a price is *derived*. Measuring them on the live scale would
    make every set price look like a broken band and prove nothing.
    """
    return replace(
        _plain_scale(scale),
        build_limited_building=0,
        campaign_infantry=0,
        campaign_unit=0,
        campaign_building=0,
    )

from .shelf import (
    shop_shelf,
    shop_shelf_reward_ids,
    upgradeable_entries,
)
from randomizer.core.integrity import SIGNATURE_KEY, SIGNED, sign, verify

from .archipelago_purchases import validate_archipelago_purchase
from .persistence import (
    SHOP_TRANSACTION_SCHEMA_VERSION,
    ShopPersistenceError,
    ShopPersistencePaths,
    ShopRepository,
)
from .service import ShopProgressionService
from .state import ShopStateError, normalize_shop_profile, normalize_shop_run
from .summary import reward_breakdown_lines, run_summary_lines
from .transitions import (
    ShopTransitionError,
    abandon_run,
    apply_mission_difficulty_assist,
    apply_mission_failure,
    apply_mission_victory,
    commit_selected_mission,
    merge_archipelago_entitlements,
    reroll_missions,
    select_mission,
    start_new_run,
)


def _closing_mission(tier):
    """Return the mission index that closes a difficulty tier.

    Fixtures that hard-code a mission number are really asserting about the
    tier it falls in, and silently start testing a different tier the moment
    stage_length moves.
    """
    return tier * SHOP_CONFIG.stage_length


def _reward(reward_id):
    reward = canonical_reward_for_id(reward_id)
    if reward.get('name') != reward_id:
        raise AssertionError(f'Missing self-check reward {reward_id!r}')
    return reward


def _requested_upgrade_modifier_checks():
    required_upgrades = {
        'coupon_book', 'stock_lock', 'veteran_academy',
        'premium_supplier',
    }
    required_modifiers = {
        'glass_cannon', 'overclocked_factories', 'black_market',
        'elite_force', 'no_safety_net', 'support_doctrine',
        'war_economy', 'narrow_intelligence', 'liquid_assets',
        'treasure_hunter',
    }
    all_modifier_ids = tuple(SHOP_CONFIG.modifiers)
    effects = modifier_effects(all_modifier_ids)

    tier_one = ShopCatalogueEntry(
        'Test Tier One Access', ShopRewardType.UNIT_ACCESS,
        'TESTONE', 'tier_1', None, ('Allies',),
    )
    tier_two = ShopCatalogueEntry(
        'Test Tier Two Access', ShopRewardType.UNIT_ACCESS,
        'TESTTWO', 'tier_2', None, ('Allies',),
    )
    other = ShopCatalogueEntry(
        'Test Other Access', ShopRewardType.UNIT_ACCESS,
        'TESTOTHER', 'tier_1', None, ('Allies',),
    )
    locked = preserve_locked_offer((tier_one, other), tier_two)
    premium = guarantee_premium_offer(
        (tier_one, other),
        (tier_one, tier_two, other),
        run_seed='SELF-CHECK',
        stage=3,
        minimum_stage=3,
    )

    final_offer = MissionOffer('FINALE', MissionEconomyClass.FINALE)
    final_run = ShopRun(
        run_id='final-victory',
        seed='FINAL-VICTORY',
        status=RunStatus.ACTIVE,
        stage=SHOP_CONFIG.run_length,
        run_length=SHOP_CONFIG.run_length,
        run_coins=200,
        mission_offers=(final_offer,),
        selected_mission_code='FINALE',
        mission_committed=True,
    )
    liquid_offer = MissionOffer('NEXT', MissionEconomyClass.ACT_1)
    liquid_run = replace(
        final_run,
        run_id='liquid',
        stage=1,
        run_coins=99,
        modifiers=('liquid_assets',),
        mission_offers=(MissionOffer('NOW', MissionEconomyClass.ACT_1),),
        selected_mission_code='NOW',
    )
    liquid = apply_mission_victory(
        ShopProfile(), liquid_run, 'NOW', next_offers=(liquid_offer,)
    )
    liquid_reward = mission_reward(
        MissionEconomyClass.ACT_1, modifiers=('liquid_assets',)
    )

    rules = {
        'CLONE': {
            'Strength': '111',
            'Cost': '100',
            'BuildTimeMultiplier': '1',
        },
        'WEAPON': {'Damage': '115'},
    }
    report = apply_shop_clone_modifiers(
        rules,
        {'E1': {'clone_id': 'CLONE', 'weapon_clone_ids': {'M60': 'WEAPON'}}},
        {
            'shop_player_damage_percent': 1.25,
            'shop_player_armor_percent': 0.8,
            'shop_production_time_percent': 0.75,
            'shop_combat_production_time_percent': 1.2,
            'shop_player_cost_percent': 1.2,
            'shop_modifier_armor_seed_stacks': {'E1': 0},
            'shop_modifier_damage_seed_stacks': {'E1': 0},
        },
    )
    challenge = SimpleNamespace(
        challenge=True,
        bonus_run_coins=0,
        bonus_meta_coins=0,
    )
    challenge_reward = mission_reward(
        MissionEconomyClass.ACT_1,
        modifiers=('treasure_hunter',),
        mission_modifier=challenge,
    )
    normal_reward = mission_reward(
        MissionEconomyClass.ACT_1,
        modifiers=('treasure_hunter',),
    )
    base_reward = SHOP_CONFIG.mission_rewards[MissionEconomyClass.ACT_1]

    return {
        'requested_permanent_upgrades_valid': required_upgrades.issubset(
            SHOP_CONFIG.permanent_upgrades
        ),
        'requested_modifiers_valid': required_modifiers.issubset(
            SHOP_CONFIG.modifiers
        ),
        'modifier_composition_valid': bool(
            modifier_difficulty(all_modifier_ids) == len(all_modifier_ids)
            and float(
                effects['production_time_percent'] * effects[
                    'combat_production_time_percent'
                ]
            ) == 1.125
            and effects['disable_rerolls']
            and effects['disable_assists']
            and effects['disable_revivals']
            and modifier_mission_offer_count(('narrow_intelligence',)) == 2
        ),
        'stock_upgrade_effects_valid': bool(
            tier_two in locked
            and tier_two in premium
            and len(locked) == 2
            and len(premium) == 2
        ),
        'liquid_assets_valid': bool(
            liquid.run.run_coins == liquid_reward.run_coins
        ),
        # Treasure Hunter doubles challenge Gems on top of the configured
        # challenge multiplier every stage-closing mission already pays.
        'treasure_hunter_valid': bool(
            challenge_reward.meta_coins == (
                base_reward.meta_coins
                * SHOP_CONFIG.challenge_reward_multiplier_percent // 100
            ) * 2
            and normal_reward.base_run_coins
            == int(base_reward.run_coins * 0.75)
        ),
        'shop_clone_modifiers_valid': bool(
            rules['CLONE']['Strength'] == '80'
            and rules['CLONE']['Cost'] == '120'
            and rules['CLONE']['BuildTimeMultiplier'] == '0.9'
            and rules['WEAPON']['Damage'] == '125'
            and all(report.values())
        ),
    }


def _permanent_feature_checks(mission_pool):
    catalogue = shop_catalogue()
    unit_entries = tuple(
        item for item in catalogue
        if item.reward_type is ShopRewardType.UNIT_ACCESS
    )
    buff_entry = next(
        item for item in catalogue
        if item.reward_type is ShopRewardType.UNIT_BUFF
    )
    power_entries = tuple(
        item for item in catalogue
        if item.reward_type is ShopRewardType.POWER_ACCESS
    )
    power_rewards = tuple(
        canonical_reward_for_id(item.reward_id) for item in power_entries
    )
    power_ids = {
        str(
            reward.get('cameo_superweapon') or reward.get('superweapon') or ''
        ).upper()
        for reward in power_rewards
        if reward.get('cameo_superweapon') or reward.get('superweapon')
    }
    sidebar_overrides = {
        str(
            reward.get('cameo_superweapon') or reward.get('superweapon')
        ).upper(): str(
            (reward.get('superweapon_rules') or {}).get('SidebarPCX')
        )
        for reward in power_rewards
        if (reward.get('superweapon_rules') or {}).get('SidebarPCX')
    }
    power_cameos = ensure_superweapon_cameos(
        power_ids, sidebar_overrides, synchronous=True
    )
    offers = generate_mission_offers(
        mission_pool, run_seed='SHOP-PERMANENT-FEATURES', stage=1
    )
    upgrade_levels = {
        'extra_shop_stock': 2,
        'expanded_loadout': 1,
        'emergency_revival': 1,
        'free_buff_token': 1,
        'challenge_hunter': 5,
        'recovery_salvage': 5,
        'starting_buff_draft': 1,
        'discount_specialization': 5,
    }
    profile = ShopProfile(
        meta_coins=1000,
        permanent_upgrades=upgrade_levels,
        salvaged_run_coins=7,
    )
    run = ShopRun(
        run_id='permanent-features',
        seed='SHOP-PERMANENT-FEATURES',
        status=RunStatus.ACTIVE,
        stage=1,
        run_length=SHOP_CONFIG.run_length,
        run_coins=20,
        mission_offers=offers,
        starting_draft_buffs=(BuffPurchase(buff_entry.reward_id, 1),),
        reward_settings={'shop_discount_specialization': 'Units'},
    )
    # A stage-closing mission is a challenge on its own; nothing else forces
    # one now that Permanent Challenge Slots is retired.
    late_run = replace(run, stage=SHOP_CONFIG.stage_length)
    forced = mission_modifier_for_run_offer(late_run, offers[0])
    between_stages = mission_modifier_for_run_offer(run, offers[0])
    challenge_reward = mission_reward(
        offers[0].economy_class,
        mission_modifier=forced,
        challenge_hunter_level=5,
    )
    normal_price = run_reward_price(unit_entries[0])
    specialized_price = run_reward_price(
        unit_entries[0], specialization='Units', specialization_level=5
    )
    globally_discounted = all(
        run_reward_price(entry, specialization_level=5)
        < run_reward_price(entry)
        and run_reward_price(
            entry, specialization='Units', specialization_level=5
        ) == run_reward_price(
            entry, specialization='Powers', specialization_level=5
        )
        for entry in (unit_entries[0], buff_entry, power_entries[0])
    )
    stock = rotating_unit_inventory(
        unit_entries,
        run_seed=run.seed,
        stage=run.stage,
        offer_count=SHOP_CONFIG.unit_inventory_size + 2,
    )
    marker_run = replace(
        run,
        starting_unit_ids=tier_one_unit_ids(
            ('allies', 'soviets', 'epsilon')
        ),
        starting_defense_ids=tier_one_defense_ids(
            ('allies', 'soviets', 'epsilon')
        ),
        reward_settings={'shop_faction_filter': 'All Campaigns'},
    )
    concrete_starters = active_shop_starter_unit_ids(marker_run)
    concrete_defenses = active_shop_starter_defense_ids(marker_run)
    starter_cameos = ensure_unit_cameos(
        (*concrete_starters, *concrete_defenses), synchronous=True
    )
    committed = commit_selected_mission(run, offers[0].mission_code)
    revived = apply_mission_failure(
        committed,
        offers[0].mission_code,
        profile=profile,
        maximum_lives=2,
        revival_offers=offers[1:] + offers[:1],
    )
    failed = apply_mission_failure(
        replace(committed, emergency_revivals_used=1),
        offers[0].mission_code,
        profile=profile,
        maximum_lives=1,
        salvage_run_coins=25,
        maximum_salvaged_run_coins=25,
    )
    free_validation = validate_run_purchase(
        canonical_reward_for_id(buff_entry.reward_id),
        price=0,
        run_coins=run.run_coins,
        active_tech_ids=(buff_entry.target_id,),
    )
    token_run = apply_validated_run_purchase(
        run,
        canonical_reward_for_id(buff_entry.reward_id),
        free_validation,
        consume_free_buff_token=True,
    )
    loadout_entries = unit_entries[:6]
    expanded = validate_starting_loadout(
        starter_tech_ids=(),
        selected_reward_ids=(item.reward_id for item in loadout_entries),
        entitled_reward_ids=(item.reward_id for item in loadout_entries),
        maximum_extra_units=6,
    )
    started = start_new_run(
        profile,
        run_id='salvage-start',
        seed='SALVAGE-START',
        mission_offers=offers,
    )
    retired_draft_purchase = purchase_permanent_upgrade(
        ShopProfile(meta_coins=1000), 'starting_buff_draft'
    )
    required = set(upgrade_levels)
    return {
        'permanent_features_config_valid': required.issubset(
            SHOP_CONFIG.permanent_upgrades
        ),
        'permanent_feature_persistence_valid': bool(
            normalize_shop_profile(profile.to_dict()) == profile
            and normalize_shop_run(run.to_dict()) == run
        ),
        'extra_shop_stock_valid': len(stock) == SHOP_CONFIG.unit_inventory_size + 2,
        'shop_power_cameos_valid': bool(
            power_ids and set(power_cameos) == power_ids
        ),
        'starter_loadout_display_valid': bool(
            len(concrete_starters) == 7
            and len(set(concrete_starters)) == 7
            and concrete_starters[-2] in {'DEST', 'SUB', 'SLED', 'SWORD'}
            and concrete_starters[-1] in {'AEGIS', 'SWLF', 'SLED', 'MANTA'}
            and len(concrete_defenses) == 2
            and concrete_starters == active_shop_starter_unit_ids(marker_run)
            and concrete_defenses == active_shop_starter_defense_ids(marker_run)
            and set(concrete_starters).union(concrete_defenses).issubset(
                active_shop_tech_ids(marker_run)
            )
            and set(starter_cameos)
            == set(concrete_starters).union(concrete_defenses)
            and not any(
                item.startswith('T1_')
                for item in (*concrete_starters, *concrete_defenses)
            )
        ),
        'expanded_loadout_valid': expanded.allowed and expanded.extra_slots_used == 6,
        'emergency_revival_valid': bool(
            revived.revived
            and revived.run.status is RunStatus.ACTIVE
            and revived.run.emergency_revivals_used == 1
            and not revived.run.mission_committed
        ),
        'free_buff_token_valid': bool(
            free_validation.allowed
            and token_run.run_coins == run.run_coins
            and token_run.free_buff_tokens_used == 1
        ),
        'challenge_hunter_valid': bool(
            forced is not None
            and forced.challenge
            and challenge_reward.challenge_hunter_run_coins == 50
            and challenge_reward.challenge_hunter_meta_coins == 20
        ),
        'recovery_salvage_valid': bool(
            not failed.revived
            and failed.profile is not None
            and failed.profile.salvaged_run_coins == 20
            and started.run.run_coins == SHOP_CONFIG.starting_run_coins + 7
            and started.profile.salvaged_run_coins == 0
        ),
        'starting_buff_draft_retirement_valid': bool(
            not SHOP_CONFIG.permanent_upgrades[
                'starting_buff_draft'
            ].purchasable
            and not retired_draft_purchase.validation.allowed
            and retired_draft_purchase.profile.meta_coins == 1000
            and run.starting_draft_buffs
            and canonical_reward_for_id(buff_entry.reward_id)
            in active_shop_rewards(run)
            and not started.run.starting_draft_buffs
        ),
        'discount_specialization_valid': bool(
            specialized_price < normal_price and globally_discounted
        ),
        # Challenges belong to the stage-closing mission and nowhere else.
        'challenge_placement_valid': bool(
            forced
            and forced.challenge
            and not (between_stages and between_stages.challenge)
        ),
    }


def _phase_two_checks(mission_pool):
    offers = generate_mission_offers(
        mission_pool, run_seed='SHOP-PERSISTENCE-CHECK', stage=1
    )
    profile = ShopProfile(
        meta_coins=20,
        permanent_unit_unlocks=('GI Access',),
        permanent_upgrades={'victory_run_coin_bonus': 3},
    )
    started = start_new_run(
        profile,
        run_id='shop-persistence-run',
        seed='SHOP-PERSISTENCE-CHECK',
        mission_offers=offers,
        permanent_entitlement_ids=profile.permanent_unit_unlocks,
    )
    selected_code = offers[0].mission_code
    selected = select_mission(started.run, selected_code)
    reroll_offer = generate_mission_offers(
        mission_pool,
        run_seed='SHOP-PERSISTENCE-CHECK',
        stage=1,
        reroll_count=1,
        previous_offer_codes=(offer.mission_code for offer in offers),
    )
    rerolled_run = reroll_missions(
        started.run, reroll_offer, maximum_rerolls=1
    )
    standalone_ui_transitions_valid = bool(
        selected.selected_mission_code == selected_code
        and not selected.mission_committed
        and rerolled_run.rerolls_used == 1
        and not rerolled_run.selected_mission_code
    )
    committed = commit_selected_mission(started.run, selected_code)
    next_offers = generate_mission_offers(
        mission_pool,
        run_seed='SHOP-PERSISTENCE-CHECK',
        stage=2,
        completed_codes=(selected_code,),
    )
    victory = apply_mission_victory(
        started.profile,
        committed,
        selected_code,
        next_offers=next_offers,
    )
    duplicate = apply_mission_victory(
        victory.profile, victory.run, selected_code
    )
    victory_idempotency_valid = bool(
        victory.changed
        and not duplicate.changed
        and duplicate.profile == victory.profile
        and duplicate.run == victory.run
        and victory.run.stage == 2
        and victory.run.rewarded_victories == (victory.victory_key,)
    )

    failed_source = replace(
        committed,
        run_coins=99,
        run_purchases=(PurchaseRecord('GI Access'),),
        ap_entitlements_snapshot=('Guardian GI Access',),
    )
    failure = apply_mission_failure(failed_source, selected_code)
    repeated_failure = apply_mission_failure(failure.run, selected_code)
    failure_valid = bool(
        failure.changed
        and failure.run.status is RunStatus.FAILED
        and failure.run.failed_stage == 1
        and not repeated_failure.changed
    )
    abandoned = abandon_run(started.run)
    abandon_valid = bool(
        abandoned.changed
        and abandoned.run.status is RunStatus.FAILED
        and abandoned.run.failed_mission_code == 'GAVE_UP'
        and abandoned.run.failed_stage == started.run.stage
        and not abandoned.run.mission_offers
        and not abandoned.run.mission_committed
    )

    # Endless runs never end on their own, so a rule that closed the
    # permanent shop for a whole run closed it forever. The window is the gap
    # between missions instead, and it has to shut the moment one starts.
    committed_run = commit_selected_mission(
        started.run, started.run.mission_offers[0].mission_code
    )
    permanent_window_valid = bool(
        permanent_purchase_block_reason(None) is None
        and started.run.status is RunStatus.ACTIVE
        and permanent_purchase_block_reason(started.run) is None
        and committed_run.mission_committed
        and permanent_purchase_block_reason(committed_run)
        == PERMANENT_PURCHASE_LOCKED_MESSAGE
        and permanent_purchase_block_reason(abandoned.run) is None
    )

    finale_offer = MissionOffer(
        'SC_FIN_1', MissionEconomyClass.FINALE
    )
    completion_source = ShopRun(
        run_id='shop-completion-run',
        seed='SHOP-COMPLETION-CHECK',
        status=RunStatus.ACTIVE,
        stage=SHOP_CONFIG.run_length,
        run_length=SHOP_CONFIG.run_length,
        run_coins=0,
        mission_offers=(finale_offer,),
        selected_mission_code=finale_offer.mission_code,
        mission_committed=True,
    )
    completion = apply_mission_victory(
        ShopProfile(), completion_source, finale_offer.mission_code
    )
    repeated_completion = apply_mission_victory(
        completion.profile, completion.run, finale_offer.mission_code
    )
    completion_valid = bool(
        completion.changed
        and completion.run.status is RunStatus.COMPLETED
        and completion.run.stage == SHOP_CONFIG.run_length
        and not completion.run.mission_offers
        and completion.profile.lifetime_runs_completed == 1
        and not repeated_completion.changed
        and repeated_completion.profile.lifetime_runs_completed == 1
    )

    legacy_profile = profile.to_dict()
    legacy_profile['meta_coins'] = 137
    for field in ('permanent_buffs', 'salvaged_run_coins', 'archipelago_profiles'):
        legacy_profile.pop(field, None)
    legacy_run = failed_source.to_dict()
    legacy_run['reward_mode'] = 'Standard'
    legacy_run['run_coins'] = 83
    for field in (
        'difficulty_assists_used', 'assisted_mission_code',
        'permanent_buffs_snapshot', 'starting_draft_buffs',
        'free_buff_tokens_used', 'emergency_revivals_used',
    ):
        legacy_run.pop(field, None)
    upgraded_profile = normalize_shop_profile(legacy_profile)
    upgraded_run = normalize_shop_run(legacy_run)
    upgrade_currency_compatibility_valid = bool(
        upgraded_profile.meta_coins == 137
        and upgraded_run.run_coins == 83
        and upgraded_run.reward_mode == 'Standard'
        and upgraded_run.run_purchases == failed_source.run_purchases
    )

    with TemporaryDirectory(prefix='mo-shop-self-check-') as temporary:
        root = Path(temporary)
        paths = ShopPersistencePaths(
            profile=root / 'shop_profile.json',
            run=root / 'shop_run.json',
            transaction=root / 'shop_transaction.json',
            backup_dir=root / 'backups',
        )
        repository = ShopRepository(paths)
        missing_profile, missing_run = repository.load()
        repository.commit(
            started.profile, started.run, started.transaction_id
        )
        repository.save_run(committed)
        reopened_profile, reopened_run = ShopRepository(paths).load()

        repository.prepare_commit(
            victory.profile, victory.run, victory.victory_key
        )
        atomic_write_json(
            paths.profile, victory.profile.to_dict(), indent=None
        )
        recovered_profile, recovered_run = ShopRepository(paths).load()
        replayed = ShopProgressionService(
            ShopRepository(paths)
        ).record_victory(selected_code)

        repository.commit(
            started.profile,
            failure.run,
            'shop-persistence-run:failure-test',
        )
        restarted = ShopProgressionService(repository).start_run(
            run_id='shop-persistence-run-2',
            seed='SHOP-PERSISTENCE-CHECK-2',
            mission_offers=offers,
            permanent_entitlement_ids=(
                started.profile.permanent_unit_unlocks
            ),
        )
        restart_valid = bool(
            restarted.run.run_coins == SHOP_CONFIG.starting_run_coins
            and not restarted.run.run_purchases
            and not restarted.run.run_buffs
            and restarted.profile.meta_coins == started.profile.meta_coins
            and restarted.profile.permanent_unit_unlocks
            == started.profile.permanent_unit_unlocks
            and restarted.profile.lifetime_runs_started
            == started.profile.lifetime_runs_started + 1
        )

        # A new run no longer ends the one in progress. Both are kept, the
        # new one is the one being played, and an id already stored is still
        # refused however old the run wearing it is.
        parallel = ShopProgressionService(repository).start_run(
            run_id='shop-persistence-run-3',
            seed='SHOP-PERSISTENCE-CHECK-3',
            mission_offers=offers,
        )
        stored_runs, active_run_id = repository.list_runs()
        try:
            ShopProgressionService(repository).start_run(
                run_id='shop-persistence-run',
                seed='SHOP-PERSISTENCE-CHECK-4',
                mission_offers=offers,
            )
            reused_id_refused = False
        except ShopTransitionError:
            reused_id_refused = True
        parallel_runs_valid = bool(
            active_run_id == parallel.run.run_id
            and {run.run_id for run in stored_runs} == {
                'shop-persistence-run',
                'shop-persistence-run-2',
                'shop-persistence-run-3',
            }
            and next(
                run for run in stored_runs
                if run.run_id == 'shop-persistence-run-2'
            ) == restarted.run
            and reused_id_refused
        )

        service_reset_profile, service_reset_run = ShopProgressionService(
            repository
        ).reset_profile()
        service_reset_valid = bool(
            service_reset_profile == ShopProfile()
            and service_reset_run is None
            and not paths.run.exists()
        )
        repository.commit(
            restarted.profile,
            restarted.run,
            'shop-persistence-run:restore-before-reset',
        )
        repository.prepare_commit(
            ShopProfile(), None, 'shop-persistence-run:reset-recovery'
        )
        atomic_write_json(paths.profile, ShopProfile().to_dict(), indent=None)
        recovered_reset_profile, recovered_reset_run = ShopRepository(
            paths
        ).load()
        reset_recovery_valid = bool(
            recovered_reset_profile == ShopProfile()
            and recovered_reset_run is None
            and not paths.run.exists()
            and not paths.transaction.exists()
        )

        atomic_write_text(paths.profile, '{')
        try:
            repository.load_profile()
            corrupt_state_rejected = False
        except ShopPersistenceError:
            corrupt_state_rejected = any(paths.backup_dir.iterdir())

        persistence_valid = bool(
            missing_profile == ShopProfile()
            and missing_run is None
            and reopened_profile == started.profile
            and reopened_run == committed
            and recovered_profile == victory.profile
            and recovered_run == victory.run
            and not paths.transaction.exists()
            and not replayed.changed
            and replayed.profile == victory.profile
            and replayed.run == victory.run
            and restart_valid
            and parallel_runs_valid
            and service_reset_valid
            and reset_recovery_valid
            and corrupt_state_rejected
        )

    return {
        'standalone_ui_transitions_valid': standalone_ui_transitions_valid,
        'victory_idempotency_valid': victory_idempotency_valid,
        'failure_transition_valid': failure_valid,
        'abandon_transition_valid': abandon_valid,
        'permanent_purchase_window_valid': permanent_window_valid,
        'completion_transition_valid': completion_valid,
        'persistence_recovery_valid': persistence_valid,
        'upgrade_currency_compatibility_valid': (
            upgrade_currency_compatibility_valid
        ),
    }


def _phase_four_checks():
    classes = tuple(MissionEconomyClass)
    mission_pool = [
        {
            'code': f'SC_RUN_{index:02d}',
            'reward_class': classes[index % len(classes)].value,
        }
        for index in range(16)
    ]
    with TemporaryDirectory(prefix='mo-shop-run-self-check-') as temporary:
        root = Path(temporary)
        repository = ShopRepository(ShopPersistencePaths(
            profile=root / 'shop_profile.json',
            run=root / 'shop_run.json',
            transaction=root / 'shop_transaction.json',
            backup_dir=root / 'backups',
        ))
        service = ShopProgressionService(repository)
        offers = generate_mission_offers(
            mission_pool, run_seed='SHOP-FULL-RUN', stage=1
        )
        service.start_run(
            run_id='shop-full-run',
            seed='SHOP-FULL-RUN',
            mission_offers=offers,
            campaign_filter='All Campaigns',
            reward_mode='Standard',
            reward_settings={'randomize_unit_access': True},
            eligible_mission_codes=(
                mission['code'] for mission in mission_pool
            ),
            starting_unit_ids=('MOR_T1_INFANTRY',),
            starting_defense_ids=('MOR_T1_DEFENSES',),
        )
        total_meta_coins = 0
        all_stages_had_three_offers = True
        challenge_victories = 0
        for expected_stage in range(1, SHOP_CONFIG.run_length + 1):
            profile, run = repository.load()
            all_stages_had_three_offers &= len(run.mission_offers) == 3
            code = run.mission_offers[0].mission_code
            selected = service.select_mission(code)
            committed = service.commit_mission(code)
            assert selected.selected_mission_code == code
            assert not selected.mission_committed
            assert committed.mission_committed
            next_offers = generate_mission_offers(
                mission_pool,
                run_seed=run.seed,
                stage=expected_stage + 1,
                completed_codes=run.completed_missions + (code,),
            )
            if is_challenge_stage(expected_stage):
                challenge_victories += 1
            transition = service.record_victory(
                code, next_offers=next_offers
            )
            assert transition.changed
            total_meta_coins += transition.reward.meta_coins
        final_profile, final_run = repository.load()

    unit_reward_ids = [
        entry.reward_id for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
    ][:2]
    buff_reward_id = next(
        entry.reward_id for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.UNIT_BUFF
    )
    stacked = replace(
        final_run,
        selected_permanent_units=(unit_reward_ids[0],),
        run_purchases=(PurchaseRecord(unit_reward_ids[1]),),
        run_buffs=(BuffPurchase(buff_reward_id, 2),),
    )
    reward_names = [reward.get('name') for reward in active_shop_rewards(stacked)]
    drawn_challenge_buffs = sum(
        enemy_buffs_for_stage(index * SHOP_CONFIG.stage_length, SHOP_CONFIG)
        for index in range(1, challenge_victories + 1)
    )
    return {
        # A standalone run is endless: it stays active, banks Gems as it
        # goes, resets its offer history every stage, and collects two
        # permanent enemy buffs from each stage-closing challenge.
        'full_standalone_run_valid': bool(
            all_stages_had_three_offers
            and final_run.status is RunStatus.ACTIVE
            and final_run.endless
            and final_run.stage == SHOP_CONFIG.run_length + 1
            and len(final_run.completed_missions) == (
                SHOP_CONFIG.run_length % SHOP_CONFIG.stage_length
            )
            and final_profile.meta_coins == total_meta_coins
            and final_profile.lifetime_missions_completed
            == SHOP_CONFIG.run_length
        ),
        'endless_challenge_cadence_valid': bool(
            challenge_victories
            == SHOP_CONFIG.run_length // SHOP_CONFIG.stage_length
            # Bounded rather than exact: the weighted draw is exact, and the
            # hate draft adds up to enemy_hate_draft_count on top -- fewer
            # when the player left nothing on the shelf, or when the mirror
            # of what they left is locked or already at its ceiling. Asserting
            # the upper bound only would pass a hate draft that never fired.
            and drawn_challenge_buffs
            <= len(final_run.permanent_enemy_buff_ids)
            <= drawn_challenge_buffs
            + challenge_victories * SHOP_CONFIG.enemy_hate_draft_count
        ),
        'active_shop_reward_payload_valid': bool(
            reward_names.count(unit_reward_ids[0]) == 1
            and reward_names.count(unit_reward_ids[1]) == 1
            and reward_names.count(buff_reward_id) == 2
        ),
    }


def _phase_five_checks():
    catalogue = shop_catalogue()
    selection_pool = [
        entry.reward_id for entry in catalogue
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
    ][:8]
    unit_ids = selection_pool[:2]
    buff_id = next(
        entry.reward_id for entry in catalogue
        if entry.reward_type is ShopRewardType.UNIT_BUFF
    )
    records = (
        {'index': 0, 'reward_name': unit_ids[0]},
        {'index': 1, 'reward_name': unit_ids[1]},
        {'index': 2, 'reward_name': buff_id},
        {'index': 2, 'reward_name': buff_id},
        {'index': 3, 'reward_name': buff_id},
    )
    ap_reward_ids = shop_reward_ids_from_ap_ledger(records)
    ap_state = {
        'manifest_checksum': 'phase-five-manifest',
        'checkpoint': {'seed_name': 'Phase Five Room'},
        'team': 0,
        'slot': 3,
    }
    ap_identity = archipelago_shop_identity(ap_state)
    other_identity = archipelago_shop_identity({**ap_state, 'slot': 4})
    offers = (
        MissionOffer('SC_AP_1', MissionEconomyClass.ACT_1),
    )
    all_units_started = start_new_run(
        ShopProfile(),
        run_id='shop-ap-all-units-run-1',
        seed='SHOP-AP-ALL-UNITS',
        mission_offers=offers,
        ap_entitlement_ids=selection_pool,
        ap_identity=ap_identity,
        maximum_extra_units=3,
    )
    started = start_new_run(
        ShopProfile(),
        run_id='shop-ap-run-1',
        seed='SHOP-AP-RUN-1',
        mission_offers=offers,
        selected_reward_ids=(unit_ids[0],),
        ap_entitlement_ids=ap_reward_ids,
        ap_identity=ap_identity,
    )
    active_names = [
        reward.get('name') for reward in active_shop_rewards(started.run)
    ]
    replayed = merge_archipelago_entitlements(
        started.run, ap_identity, ap_reward_ids
    )
    expanded = merge_archipelago_entitlements(
        started.run, ap_identity, (*ap_reward_ids, buff_id)
    )
    wrong_slot = merge_archipelago_entitlements(
        started.run, other_identity, (*ap_reward_ids, buff_id)
    )
    failed = apply_mission_failure(
        replace(
            started.run,
            selected_mission_code=offers[0].mission_code,
            mission_committed=True,
        ),
        offers[0].mission_code,
    )
    restarted = start_new_run(
        started.profile,
        run_id='shop-ap-run-2',
        seed='SHOP-AP-RUN-2',
        mission_offers=offers,
        selected_reward_ids=(unit_ids[1],),
        ap_entitlement_ids=ap_reward_ids,
        ap_identity=ap_identity,
    )
    restored = normalize_shop_run(restarted.run.to_dict())
    restarted_names = [
        reward.get('name') for reward in active_shop_rewards(restarted.run)
    ]
    with TemporaryDirectory(prefix='mo-shop-ap-self-check-') as temporary:
        root = Path(temporary)
        repository = ShopRepository(ShopPersistencePaths(
            profile=root / 'shop_profile.json',
            run=root / 'shop_run.json',
            transaction=root / 'shop_transaction.json',
            backup_dir=root / 'backups',
        ))
        repository.commit(
            started.profile, started.run, started.transaction_id
        )
        service = ShopProgressionService(repository)
        synced = service.sync_archipelago_entitlements(
            ap_identity, (*ap_reward_ids, buff_id)
        )
        replayed_sync = service.sync_archipelago_entitlements(
            ap_identity, (*ap_reward_ids, buff_id)
        )
        persisted_sync = ShopRepository(repository.paths).load_run()
    return {
        'archipelago_ledger_replay_valid': bool(
            ap_reward_ids == (
                unit_ids[0], unit_ids[1], buff_id, buff_id
            )
            and replayed == started.run
            and expanded.ap_entitlements_snapshot.count(buff_id) == 3
            and wrong_slot == started.run
        ),
        'archipelago_loadout_merge_valid': bool(
            ap_identity
            and ap_identity != other_identity
            and not archipelago_shop_identity({
                **ap_state, 'slot': 'invalid'
            })
            and ap_unit_entitlement_ids(ap_reward_ids) == tuple(unit_ids)
            and active_names.count(unit_ids[0]) == 1
            and active_names.count(unit_ids[1]) == 1
            and active_names.count(buff_id) == 2
        ),
        'archipelago_all_units_loadout_valid': bool(
            not all_units_started.run.selected_permanent_units
            and set(selection_pool) == {
                reward.get('name')
                for reward in active_shop_rewards(all_units_started.run)
            }
            and all_units_started.run.run_coins
            == SHOP_CONFIG.starting_run_coins
        ),
        'archipelago_failure_restart_valid': bool(
            failed.run.status is RunStatus.FAILED
            and restarted.run.ap_identity == ap_identity
            and restarted.run.ap_entitlements_snapshot == ap_reward_ids
            and restarted.run.run_coins == SHOP_CONFIG.starting_run_coins
            and restarted.profile.meta_coins == started.profile.meta_coins
            and restarted_names.count(unit_ids[1]) == 1
            and restarted_names.count(unit_ids[0]) == 1
            and restarted_names.count(buff_id) == 2
            and not restarted.profile.permanent_unit_unlocks
            and not restarted.profile.archipelago_profiles
            and restored == restarted.run
        ),
        'archipelago_snapshot_persistence_valid': bool(
            synced.ap_entitlements_snapshot.count(buff_id) == 3
            and replayed_sync == synced
            and persisted_sync == synced
        ),
    }


def _phase_integrity_checks():
    """Prove the state signatures do what they claim, and only that.

    Every one of these is a claim someone could otherwise take on trust:
    that a signature is written, that changing a byte is noticed, that
    noticing it does not destroy the profile, that a profile written before
    signing existed still loads, and that the write-ahead journal -- which
    writes straight into the profile -- cannot be used to go around all of it.
    """
    import copy
    import json as _json

    with TemporaryDirectory(prefix='mo-shop-integrity-check-') as temporary:
        root = Path(temporary)
        paths = ShopPersistencePaths(
            profile=root / 'shop_profile.json',
            run=root / 'shop_run.json',
            transaction=root / 'shop_transaction.json',
            backup_dir=root / 'backups',
        )

        def read_profile_document():
            return read_opaque_object(paths.profile)

        def write_profile_document(document):
            paths.profile.write_text(_json.dumps(document), encoding='utf-8')

        ShopRepository(paths).save_profile(ShopProfile(meta_coins=88))
        signed_document = read_profile_document()
        clean = ShopRepository(paths).load_profile()
        signed_valid = bool(
            SIGNATURE_KEY in signed_document
            and verify(signed_document) is SIGNED
            and clean.meta_coins == 88
            and not clean.integrity_modified
        )

        # An edited profile still loads and still plays. It must not take the
        # corruption path, which moves the file aside and refuses to start:
        # a failing disk would then cost a player everything they had.
        tampered_document = dict(signed_document)
        tampered_document['meta_coins'] = 999999
        write_profile_document(tampered_document)
        tampered = ShopRepository(paths).load_profile()
        # And the flag is signed with the rest, so a second edit that clears
        # it is itself an edit.
        cleared = read_profile_document()
        cleared['integrity_modified'] = False
        write_profile_document(cleared)
        tamper_valid = bool(
            tampered.meta_coins == 999999
            and tampered.integrity_modified
            and ShopRepository(paths).load_profile().integrity_modified
            and paths.profile.is_file()
        )

        # Signing arrives in an update. Every profile written before it has
        # no signature, and calling those cheats would brand every existing
        # player on the day they upgraded.
        write_profile_document({'schema_version': 1, 'meta_coins': 42})
        legacy = ShopRepository(paths).load_profile()
        legacy_valid = bool(
            legacy.meta_coins == 42
            and not legacy.integrity_modified
            and verify(read_profile_document()) is SIGNED
        )

        def journal(gem):
            return copy.deepcopy({
                'schema_version': SHOP_TRANSACTION_SCHEMA_VERSION,
                'transaction_id': 'integrity-check',
                'profile': ShopProfile(meta_coins=gem).to_dict(),
                'run': None,
            })

        def write_journal(document):
            paths.transaction.write_text(
                _json.dumps(document), encoding='utf-8'
            )

        ShopRepository(paths).save_profile(ShopProfile(meta_coins=88))
        write_journal(sign(journal(90)))
        honest_journal = ShopRepository(paths).load_profile()

        # Signed, then edited: the journal writes into the profile, so an
        # unchecked one is a way around both other signatures.
        ShopRepository(paths).save_profile(ShopProfile(meta_coins=88))
        forged = sign(journal(90))
        forged['profile']['meta_coins'] = 500000
        write_journal(forged)
        after_forged = ShopRepository(paths).load_profile()

        # And an unsigned journal is discarded rather than grandfathered.
        # It is written before either state file changes, so both are still
        # consistent without it.
        ShopRepository(paths).save_profile(ShopProfile(meta_coins=88))
        write_journal(journal(500000))
        after_unsigned = ShopRepository(paths).load_profile()

        journal_valid = bool(
            honest_journal.meta_coins == 90
            and not honest_journal.integrity_modified
            and after_forged.meta_coins == 88
            and after_forged.integrity_modified
            and after_unsigned.meta_coins == 88
            and not paths.transaction.is_file()
        )

        # A modified profile keeps playing and stops buying Archipelago
        # locations, because those send items into other people's games.
        modified_profile = replace(
            ShopProfile(meta_coins=1000), integrity_modified=True
        )
        blocked = validate_archipelago_purchase(
            modified_profile, 'ap-v1:integrity', 101, cost=5,
            connected=True, available_location_ids=(101,),
        )
        allowed = validate_archipelago_purchase(
            ShopProfile(meta_coins=1000), 'ap-v1:integrity', 101, cost=5,
            connected=True, available_location_ids=(101,),
        )
        ap_gate_valid = bool(
            blocked.result is PurchaseResult.PROFILE_MODIFIED
            and not blocked.allowed
            and allowed.result is PurchaseResult.OK
        )

        # The file is stored compressed rather than as readable JSON. That is
        # a doorstep and nothing more -- it stops the edit that needs no tools
        # at all, and the signature above is what actually reports tampering.
        # Worth checking anyway, because a silent fall back to plain text
        # would look exactly the same from the outside.
        ShopRepository(paths).save_profile(ShopProfile(meta_coins=88))
        stored = paths.profile.read_bytes()
        opaque_valid = bool(
            stored.startswith(OPAQUE_MAGIC)
            and b'meta_coins' not in stored
            and ShopRepository(paths).load_profile().meta_coins == 88
        )

    # A profile written under the old readable name is renamed rather than
    # abandoned. Losing one here would read to the player as losing every Gem
    # they had.
    with TemporaryDirectory(prefix='mo-shop-legacy-name-check-') as temporary:
        root = Path(temporary)
        legacy_profile = root / 'shop_profile.json'
        paths = ShopPersistencePaths(
            profile=root / 'shop_profile.dat',
            run=root / 'shop_run.dat',
            transaction=root / 'shop_transaction.dat',
            backup_dir=root / 'backups',
        )
        atomic_write_json(
            legacy_profile, sign(ShopProfile(meta_coins=44).to_dict()),
            indent=None,
        )
        loaded = ShopRepository(paths).load_profile()
        legacy_name_valid = bool(
            loaded.meta_coins == 44
            and not loaded.integrity_modified
            and not legacy_profile.exists()
            and paths.profile.is_file()
        )

    return {
        'shop_state_signed_valid': signed_valid,
        'shop_state_tamper_flagged_valid': tamper_valid,
        'shop_state_unsigned_accepted_valid': legacy_valid,
        'shop_state_journal_signed_valid': journal_valid,
        'shop_modified_profile_ap_gate_valid': ap_gate_valid,
        'shop_state_opaque_valid': opaque_valid,
        'shop_state_legacy_name_adopted_valid': legacy_name_valid,
    }


def _run_list_checks():
    """Prove the run file holds several runs without losing any of them.

    A player keeps more than one run open and returns to whichever they feel
    like, so the file that used to hold one run holds a list. Everything here
    is a way that could go wrong quietly: the run already on disk failing to
    survive the conversion, a save on one run overwriting another, a crash
    mid-commit restoring only the run being committed, or two runs sharing an
    id and therefore sharing each other's victory keys.
    """
    def make_run(run_id, stage=1, coins=100):
        return ShopRun(
            run_id=run_id,
            seed=f'RUN-LIST-{run_id}',
            status=RunStatus.ACTIVE,
            stage=stage,
            run_length=8,
            run_coins=coins,
        )

    with TemporaryDirectory(prefix='mo-shop-run-list-check-') as temporary:
        root = Path(temporary)
        paths = ShopPersistencePaths(
            profile=root / 'shop_profile.dat',
            run=root / 'shop_run.dat',
            transaction=root / 'shop_transaction.dat',
            backup_dir=root / 'backups',
        )

        # The shape every existing player has on disk: one bare run document.
        stored = make_run('run-list-existing', stage=4, coins=777)
        atomic_write_json(paths.run, sign(stored.to_dict()), indent=None)
        stored_bytes = paths.run.read_bytes()

        repository = ShopRepository(paths)
        runs, active = repository.list_runs()
        migration_valid = bool(
            repository.load_run() == stored
            and len(runs) == 1
            and active == stored.run_id
            and 'runs' in read_opaque_object(paths.run)
            and (paths.backup_dir / 'shop_run.dat.pre-multirun').read_bytes()
            == stored_bytes
        )

        second = make_run('run-list-second', coins=50)
        repository.save_run(second)
        runs, active = repository.list_runs()
        second_run_valid = bool(
            len(runs) == 2
            and runs[0] == stored
            and active == second.run_id
            and repository.load_run() == second
        )

        resumed = repository.select_run(stored.run_id)
        advanced = make_run(stored.run_id, stage=5, coins=1)
        repository.save_run(advanced)
        runs, _active = repository.list_runs()
        selection_valid = bool(
            resumed == stored
            and runs[0] == advanced
            and runs[1] == second
        )

        repository.delete_run(stored.run_id)
        runs, active = repository.list_runs()
        # Which run to resume is the player's choice; deleting the one they
        # were in must not silently drop them into another.
        deletion_valid = bool(
            len(runs) == 1
            and active is None
            and repository.load_run() is None
        )

        repository.select_run(second.run_id)
        repository.save_run(make_run('run-list-third', stage=2))
        committed = make_run(second.run_id, stage=6, coins=9)
        repository.prepare_commit(
            ShopProfile(meta_coins=42), committed, 'run-list:victory'
        )
        reopened = ShopRepository(paths)
        recovered_profile, recovered_run = reopened.load()
        runs, active = reopened.list_runs()
        recovery_valid = bool(
            recovered_profile.meta_coins == 42
            and recovered_run == committed
            and {run.run_id for run in runs}
            == {second.run_id, 'run-list-third'}
            and active == second.run_id
            and not paths.transaction.exists()
        )

        # A journal left behind by the version that wrote one run.
        atomic_write_json(paths.transaction, sign({
            'schema_version': SHOP_TRANSACTION_SCHEMA_VERSION,
            'transaction_id': 'run-list:legacy-journal',
            'profile': ShopProfile(meta_coins=7).to_dict(),
            'run': make_run('run-list-third', stage=6).to_dict(),
        }), indent=None)
        reopened = ShopRepository(paths)
        legacy_profile, legacy_run = reopened.load()
        runs, _active = reopened.list_runs()
        legacy_journal_valid = bool(
            legacy_profile.meta_coins == 7
            and legacy_run.run_id == 'run-list-third'
            and legacy_run.stage == 6
            and len(runs) == 2
        )

        atomic_write_json(paths.run, sign({
            'schema_version': SHOP_RUN_COLLECTION_SCHEMA_VERSION,
            'active_run_id': 'run-list-twin',
            'runs': [
                make_run('run-list-twin').to_dict(),
                make_run('run-list-twin', stage=3).to_dict(),
            ],
        }), indent=None)
        try:
            ShopRepository(paths).load_run()
            duplicate_rejected = False
        except ShopPersistenceError:
            duplicate_rejected = True

    return {
        'shop_run_list_migration_valid': migration_valid,
        'shop_run_list_isolation_valid': second_run_valid and selection_valid,
        'shop_run_list_deletion_valid': deletion_valid,
        'shop_run_list_recovery_valid': recovery_valid and legacy_journal_valid,
        'shop_run_list_duplicate_rejected_valid': duplicate_rejected,
    }

def _phase_six_checks():
    identity = 'ap-v1:shop-purchase-self-check'
    other_identity = 'ap-v1:other-shop-slot'
    with TemporaryDirectory(prefix='mo-shop-ap-purchase-check-') as temporary:
        root = Path(temporary)
        paths = ShopPersistencePaths(
            profile=root / 'shop_profile.json',
            run=root / 'shop_run.json',
            transaction=root / 'shop_transaction.json',
            backup_dir=root / 'backups',
        )
        repository = ShopRepository(paths)
        repository.save_profile(ShopProfile(meta_coins=12))
        service = ShopProgressionService(repository)
        first = service.purchase_archipelago_location(
            identity,
            101,
            cost=5,
            connected=True,
            available_location_ids=(101, 102),
        )
        repeated = service.purchase_archipelago_location(
            identity,
            101,
            cost=5,
            connected=True,
            available_location_ids=(101, 102),
        )
        reopened = ShopProgressionService(ShopRepository(paths))
        pending = reopened.pending_archipelago_purchase_ids(identity)
        pending_profile = reopened.repository.load_profile()
        reconciled = reopened.reconcile_archipelago_purchases(identity, (101,))
        records = archipelago_purchase_records(reconciled, identity)
        insufficient = reopened.purchase_archipelago_location(
            identity,
            102,
            cost=8,
            connected=True,
            available_location_ids=(101, 102),
        )
        disconnected = reopened.purchase_archipelago_location(
            identity,
            102,
            cost=1,
            connected=False,
            available_location_ids=(101, 102),
        )
        final_profile = reopened.repository.load_profile()
    malformed = final_profile.to_dict()
    malformed['archipelago_profiles'][identity][
        'shop_purchase_transactions'
    ]['101']['status'] = 'charged-again'
    try:
        normalize_shop_profile(malformed)
        malformed_rejected = False
    except ShopStateError:
        malformed_rejected = True
    return {
        'archipelago_purchase_transaction_valid': bool(
            first.result is PurchaseResult.OK
            and repeated.result is PurchaseResult.AP_LOCATION_ALREADY_CHECKED
            and pending == (101,)
            and pending_profile.meta_coins == 7
            and records['101'] == {'cost': 5, 'status': 'checked'}
            and not archipelago_purchase_records(reconciled, other_identity)
            and insufficient.result is PurchaseResult.INSUFFICIENT_CURRENCY
            and disconnected.result is PurchaseResult.AP_NOT_CONNECTED
            and final_profile.meta_coins == 7
            and malformed_rejected
        ),
    }


def _phase_seven_checks():
    offers = (
        MissionOffer('SC_POLISH_1', MissionEconomyClass.ACT_1),
        MissionOffer('SC_POLISH_2', MissionEconomyClass.OPERATION),
        MissionOffer('SC_POLISH_3', MissionEconomyClass.FINALE),
    )
    run = ShopRun(
        run_id='shop-polish-run',
        seed='SHOP-POLISH',
        status=RunStatus.ACTIVE,
        stage=4,
        run_length=SHOP_CONFIG.run_length,
        run_coins=1000,
        mission_offers=offers,
        modifiers=('greedy', 'veteran_economy', 'blind_choice'),
    )
    hidden = hidden_offer_codes(run)
    adjusted = mission_reward(
        MissionEconomyClass.FINALE,
        modifiers=run.modifiers,
    )
    greedy_start = starting_run_coins(
        starting_capital_level=999,
        modifiers=('greedy', 'generous_command'),
        carried_run_coins=200,
    )
    generous_reward = mission_reward(
        MissionEconomyClass.OPERATION,
        modifiers=('generous_command',),
    )
    breakdown = reward_breakdown_lines(
        MissionEconomyClass.FINALE,
        victory_coin_bonus_level=2,
        modifiers=run.modifiers,
    )

    catalogue = shop_catalogue()
    power_buffs_by_target = {
        entry.target_id: entry
        for entry in catalogue
        if entry.reward_type is ShopRewardType.POWER_BUFF
    }
    power_access = next(
        entry for entry in catalogue
        if entry.reward_type is ShopRewardType.POWER_ACCESS
        and entry.target_id in power_buffs_by_target
    )
    power_buff = power_buffs_by_target[power_access.target_id]
    access_reward = canonical_reward_for_id(power_access.reward_id)
    access_price = run_reward_price(power_access)
    access_validation = validate_run_purchase(
        access_reward,
        price=access_price,
        run_coins=run.run_coins,
    )
    with_power = apply_validated_run_purchase(
        run, access_reward, access_validation
    )
    buff_reward = canonical_reward_for_id(power_buff.reward_id)
    buff_price = run_reward_price(power_buff)
    buff_validation = validate_run_purchase(
        buff_reward,
        price=buff_price,
        run_coins=with_power.run_coins,
        active_power_ids=active_shop_power_ids(with_power),
    )
    with_buff = apply_validated_run_purchase(
        with_power, buff_reward, buff_validation
    )

    completed = replace(
        with_buff,
        status=RunStatus.COMPLETED,
        stage=with_buff.run_length,
        mission_offers=(),
        completed_missions=tuple(
            f'SC_DONE_{index}'
            for index in range(1, SHOP_CONFIG.run_length + 1)
        ),
    )
    failed = replace(
        with_buff,
        status=RunStatus.FAILED,
        failed_mission_code='SC_FAILED',
        failed_stage=4,
    )
    completion_summary = run_summary_lines(ShopProfile(meta_coins=42), completed)
    failure_summary = run_summary_lines(ShopProfile(meta_coins=42), failed)
    restored = normalize_shop_run(run.to_dict())
    return {
        # Flat Ore/Gem effects are quoted verbatim in the modifier's own
        # description. Scaling the effects and forgetting the text left the
        # player reading last balance pass's numbers, so tie them together.
        'modifier_flat_text_valid': bool(
            all(
                str(abs(int(value))) in SHOP_CONFIG.modifiers[
                    modifier_id
                ].description
                for modifier_id, definition in SHOP_CONFIG.modifiers.items()
                for effect, value in definition.effects.items()
                if effect in {
                    'run_reward_flat', 'meta_reward_flat',
                    'shop_price_flat', 'starting_run_coins_flat',
                } and value
            )
        ),
        'modifier_polish_valid': bool(
            # Blind Choice covers the whole board now, so a visible card
            # beside a hidden one can no longer give the reward away.
            len(hidden) == len(offers)
            and hidden == hidden_offer_codes(run)
            and set(hidden) == {offer.mission_code for offer in offers}
            and adjusted.run_coins == 294
            and adjusted.meta_coins == 61
            # Greedy's empty wallet outranks a bought capital ladder, a
            # modifier that hands out starting Ore, and carried salvage.
            and greedy_start == 0
            and discounted_shop_price(
                50, modifiers=('poor_logistics',)
            ) == 37
            and generous_reward.meta_coins == 40
            and 'meta_reward_flat' not in SHOP_CONFIG.modifiers[
                'generous_command'
            ].effects
            and any('Permanent Victory Bonus: +50' in line for line in breakdown)
            and any('Total: +344 Ore' in line for line in breakdown)
            and 'Persistent Gems: 42' in completion_summary
            and restored == run
        ),
        'power_shop_purchase_valid': bool(
            access_validation.result is PurchaseResult.OK
            and power_access.target_id in active_shop_power_ids(with_power)
            and buff_validation.result is PurchaseResult.OK
            and with_buff.run_buffs == (BuffPurchase(power_buff.reward_id, 1),)
            and with_buff.run_coins
            == 1000 - access_price - buff_price
        ),
        'run_summary_valid': bool(
            completion_summary[0] == 'RUN VICTORY'
            and f'Missions won: {SHOP_CONFIG.run_length} / '
            f'{SHOP_CONFIG.run_length}' in completion_summary
            and failure_summary[0] == 'RUN OVER'
            and any('Failed at stage 4' in line for line in failure_summary)
        ),
    }


def _upgrade_reward_checks():
    """Prove upgrades are drawn onto owned targets and cannot be picked.

    The rework's whole claim is that a player can no longer pour every buff
    into one favourite unit. That rests on four things that are easy to break
    silently: the shelf only ever offers upgrades for what is owned, the four
    one-shot buff types stay rare, a victory spreads its grants across
    different targets, and the service refuses anything the shelf did not
    offer -- which is what stops a stale window from reopening the old manual
    path.
    """
    offers = tuple(
        MissionOffer(code, MissionEconomyClass.ACT_1)
        for code in ('AXX01', 'AXX02', 'AXX03')[:SHOP_CONFIG.mission_offer_count]
    )
    started = start_new_run(
        ShopProfile(),
        run_id='upgrade-rework-check',
        seed='UPGRADE-REWORK-CHECK',
        mission_offers=offers,
        eligible_mission_codes=tuple(
            offer.mission_code for offer in offers
        ) + ('AXX04', 'AXX05', 'AXX06'),
    )
    profile, run = started.profile, started.run
    # Give the run something to upgrade. Two owned units is the smallest
    # roster that can show a grant spreading rather than stacking.
    owned = tuple(
        entry.reward_id
        for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
        and entry.target_id in {'E1', 'HTNK'}
    )
    run = replace(
        run,
        run_purchases=tuple(PurchaseRecord(reward_id) for reward_id in owned),
    )
    owned_tech = set(active_shop_tech_ids(run))
    units, powers, upgrades = shop_shelf(profile, run)
    shelf_shape_valid = bool(
        len(units) == SHOP_CONFIG.unit_inventory_size
        and len(powers) == SHOP_CONFIG.power_inventory_size
        and len(upgrades) == SHOP_CONFIG.upgrade_inventory_size
        and all(
            entry.reward_type is ShopRewardType.UNIT_BUFF
            or entry.reward_type is ShopRewardType.POWER_BUFF
            for entry in upgrades
        )
    )
    upgrades_target_owned_valid = all(
        entry.target_id in owned_tech for entry in upgrades
    )
    weights = buff_draw_weights()
    weights_valid = bool(
        {
            buff_id for buff_id, weight in weights.items()
            if weight != DEFAULT_BUFF_DRAW_WEIGHT
        } == {'sight', 'cloak', 'sensors', 'veteran'}
        and all(
            weights[buff_id] * 4 == DEFAULT_BUFF_DRAW_WEIGHT
            for buff_id in ('sight', 'cloak', 'sensors', 'veteran')
        )
    )
    committed = replace(
        run,
        selected_mission_code=offers[0].mission_code,
        mission_committed=True,
    )
    next_offers = (MissionOffer('AXX04', MissionEconomyClass.ACT_1),)
    victory = apply_mission_victory(
        profile, committed, offers[0].mission_code, next_offers=next_offers
    )
    granted_upgrades = victory.reward.granted_upgrade_ids
    granted_units = victory.reward.granted_unit_ids
    granted_targets = [
        shop_catalogue_by_reward_id()[reward_id].target_id
        for reward_id in granted_upgrades
    ]
    mission_grant_valid = bool(
        len(granted_upgrades) == SHOP_CONFIG.mission_upgrade_reward_count
        and len(granted_targets) == len(set(granted_targets))
        and all(target in owned_tech for target in granted_targets)
        and len(granted_units) == SHOP_CONFIG.mission_unit_gift_count
    )
    granted_stacks = {
        item.reward_id: item.stacks for item in victory.run.run_buffs
    }
    grant_applied_valid = all(
        granted_stacks.get(reward_id) for reward_id in granted_upgrades
    ) and set(granted_units).issubset({
        item.reward_id for item in victory.run.run_purchases
    })
    # A victory reported twice must not pay twice, grants included.
    repeated = apply_mission_victory(
        profile, committed, offers[0].mission_code, next_offers=next_offers
    )
    repeat_grant_valid = bool(
        repeated.changed
        and repeated.reward.granted_upgrade_ids == granted_upgrades
        and apply_mission_victory(
            victory.profile,
            victory.run,
            offers[0].mission_code,
            next_offers=(),
        ).reward.granted_upgrade_ids == ()
    )
    # The gift climbs a tier only once the one below is spent, so a run with
    # Tier 1 stock left must never be handed a Tier 2 unit.
    gift_entries = tuple(
        shop_catalogue_by_reward_id()[reward_id]
        for reward_id in granted_units
    )
    unit_gift_tier_valid = all(
        entry.tier == 'tier_1' for entry in gift_entries
    )
    # One purchase per rotation, and the rest of the shelf must not move
    # underneath it. Both are easy to lose: the limit to a missing parameter
    # at one call site, the stability the moment anything in the draw's pool
    # is read from the live run instead of the stage's opening state.
    stocked = tuple(entry for entry in upgrades if (entry.stack_limit or 1) > 1)
    shelf_before = shop_shelf_reward_ids(profile, run)
    repeat_run = run
    repeat_results = []
    if stocked:
        repeat_entry = stocked[0]
        repeat_reward = canonical_reward_for_id(repeat_entry.reward_id)
        for _attempt in range(2):
            validation = validate_run_purchase(
                repeat_reward,
                price=0,
                run_coins=repeat_run.run_coins,
                active_tech_ids=tuple(owned_tech),
                shop_eligible=(
                    repeat_entry.reward_id
                    in shop_shelf_reward_ids(profile, repeat_run)
                ),
                stage_shelf_purchases=repeat_run.stage_shelf_purchases,
            )
            repeat_results.append(validation.result)
            if validation.allowed:
                repeat_run = apply_validated_run_purchase(
                    repeat_run, repeat_reward, validation
                )
    one_per_stock_valid = bool(
        stocked
        and repeat_results == [
            PurchaseResult.OK, PurchaseResult.ALREADY_PURCHASED_THIS_STAGE
        ]
        and shop_shelf_reward_ids(profile, repeat_run) == shelf_before
    )
    # Buying a unit is the sharpest version of the problem: it hands the
    # player a new upgrade target, so the pool the upgrade slots are drawn
    # from grows by a dozen entries and every one of them would land
    # somewhere else. The shelf has to be the one the stage opened with.
    stable_run = repeat_run
    if units:
        access_reward = canonical_reward_for_id(units[0].reward_id)
        access_purchase = validate_run_purchase(
            access_reward,
            price=0,
            run_coins=stable_run.run_coins,
            active_tech_ids=tuple(owned_tech),
            shop_eligible=(
                units[0].reward_id
                in shop_shelf_reward_ids(profile, stable_run)
            ),
            stage_shelf_purchases=stable_run.stage_shelf_purchases,
        )
        if access_purchase.allowed:
            stable_run = apply_validated_run_purchase(
                stable_run, access_reward, access_purchase
            )
    # Clearing the record is what the shelf would see without the rollback,
    # so this both proves the purchase really does move the pool and fails
    # loudly if the rollback is ever removed.
    unfrozen_pool = upgradeable_entries(
        replace(stable_run, stage_shelf_purchases=())
    )
    shelf_stable_valid = bool(
        len(unfrozen_pool) > len(upgradeable_entries(stable_run))
        and shop_shelf_reward_ids(profile, stable_run) == shelf_before
    )
    # An upgrade that is perfectly legal -- owned target, stacks to spare --
    # but was not drawn onto the shelf has to be refused.
    shelf_ids = shop_shelf_reward_ids(profile, run)
    unstocked = next(
        (
            entry for entry in upgradeable_entries(run)
            if entry.reward_id not in shelf_ids
        ),
        None,
    )
    shelf_gate_valid = unstocked is not None and not validate_run_purchase(
        canonical_reward_for_id(unstocked.reward_id),
        price=0,
        run_coins=run.run_coins,
        active_tech_ids=tuple(owned_tech),
        shop_eligible=unstocked.reward_id in shelf_ids,
    ).allowed
    return {
        'upgrade_shelf_shape_valid': shelf_shape_valid,
        'upgrade_shelf_targets_owned_valid': upgrades_target_owned_valid,
        'upgrade_draw_weights_valid': weights_valid,
        'mission_upgrade_grant_valid': mission_grant_valid,
        'mission_grant_applied_valid': grant_applied_valid,
        'mission_grant_idempotent_valid': repeat_grant_valid,
        'mission_unit_gift_tier_valid': unit_gift_tier_valid,
        'upgrade_shelf_purchase_gate_valid': shelf_gate_valid,
        'shop_one_purchase_per_stock_valid': one_per_stock_valid,
        'shop_shelf_stable_within_stage_valid': shelf_stable_valid,
        'shop_stock_record_clears_on_victory_valid': bool(
            repeat_run.stage_shelf_purchases
            and not victory.run.stage_shelf_purchases
        ),
    }


def _gem_pricing_checks():
    """Prove Gem prices follow tier and uniqueness, not the old cost table.

    Four things have to hold at once, and each of them has already been got
    wrong once: every access target must resolve a price, a tier must set the
    band, a hero must ignore the band, and a Cloning Vat must not be mistaken
    for a hero just because only one of it can be built.
    """
    # The band, the flat prices and the tier ordering are all claims about
    # what a unit is worth before the one-off premium multiplies it, so they
    # are measured on the scale with that knob at 1 and the premium is
    # asserted separately below. Measuring them on the live scale would make
    # every one-off look out of band and prove nothing about the model.
    pricing = _model_scale(SHOP_CONFIG.price_scales['permanent_gem'])
    report = unit_access_price_report(pricing)
    access_targets = {
        entry.target_id for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
    }
    coverage_valid = bool(
        report
        and set(report) == access_targets
        and all(price > 0 for price in report.values())
    )
    flat_prices = {
        pricing.unique_infantry,
        pricing.unique_unit,
        pricing.stolen_tech[0],
    }
    banded = {}
    unique_infantry = []
    unique_units = []
    limited_buildings = []
    for target, price in report.items():
        traits = unit_pricing_traits(target)
        category = traits.get('category')
        if traits.get('unique') and category in UNIQUE_INFANTRY_CATEGORIES:
            unique_infantry.append((target, price))
        elif traits.get('unique') and category in UNIQUE_UNIT_CATEGORIES:
            unique_units.append((target, price))
        elif traits.get('stolen_tech'):
            pass
        else:
            if traits.get('unique'):
                limited_buildings.append((target, price))
            banded[target] = price
    def in_band(tier, price, scale=pricing):
        low, high = scale.tier_prices[tier]
        return low <= price <= high
    band_valid = bool(
        banded
        and all(
            in_band(unit_access_tier(target), price)
            for target, price in banded.items()
        )
        and not flat_prices.intersection(banded.values())
    )
    # Tier has to be the dominant term: no tier 1 unit may cost more than the
    # cheapest tier 3 one, or cost would be deciding the price after all.
    by_tier = {}
    for target, price in banded.items():
        by_tier.setdefault(unit_access_tier(target), []).append(price)
    tier_order_valid = bool(
        len(by_tier) == 3
        and max(by_tier['tier_1']) <= min(by_tier['tier_3'])
        and max(by_tier['tier_2']) <= min(by_tier['tier_3'])
    )
    # Cost still has to do something, or the band collapses to one number.
    cost_spread_valid = all(
        len(set(prices)) > 1 for prices in by_tier.values()
    )
    unique_valid = bool(
        unique_infantry
        and unique_units
        and all(
            price == pricing.unique_infantry
            for _target, price in unique_infantry
        )
        and all(
            price == pricing.unique_unit
            for _target, price in unique_units
        )
    )
    # A build-limited building is limited for balance, not because it is a
    # hero, so it keeps its band and only the one-off premium moves it.
    limited_building_valid = bool(
        limited_buildings
        and all(
            in_band(unit_access_tier(target), price)
            for target, price in limited_buildings
        )
    )
    # The Ore scale is the same model with different numbers, so it gets the
    # same treatment rather than a second copy of the reasoning.
    ore = SHOP_CONFIG.price_scales['run_ore']
    ore_report = unit_access_price_report(ore)
    live_gem = SHOP_CONFIG.price_scales['permanent_gem']
    model_ore = _model_scale(ore)

    def multiplier(target, scale):
        factor = 1
        if one_off_target(target):
            factor *= scale.premium_target_multiplier
        if reward_pool_target(target):
            factor *= scale.reward_pool_multiplier
        return factor
    # One-offs are out of the band by design: hero units and stolen tech are
    # flat-priced, and everything premium carries a multiplier on top that
    # would put it above its tier's ceiling.
    ore_banded = {
        target: price
        for target, price in unit_access_price_report(model_ore).items()
        if not premium_target(target)
    }
    ore_band_valid = bool(
        ore_banded
        and all(
            in_band(unit_access_tier(target), price, ore)
            for target, price in ore_banded.items()
        )
    )
    # And the premium is exactly the multiplier over what the same unit would
    # cost without it -- measured against the scale with the knob turned off,
    # so this cannot pass by restating the code that computes it.
    one_offs = sorted(target for target in ore_report if one_off_target(target))
    pool_targets = sorted(
        target for target in ore_report if reward_pool_target(target)
    )
    premium_valid = bool(
        one_offs
        and pool_targets
        # Each currency charges exactly one of the two, and they are not the
        # same set: Ore prices fielding a one-off for a run, Gems price owning
        # a campaign unit forever.
        and ore.premium_target_multiplier > 1
        and ore.reward_pool_multiplier == 1
        and live_gem.reward_pool_multiplier > 1
        and live_gem.premium_target_multiplier == 1
        and all(
            unit_access_price(target, scale) == unit_access_price(
                target, _plain_scale(scale)
            ) * multiplier(target, scale)
            for scale in (ore, live_gem)
            for target in ore_report
            if not _flat_override(target, scale, SHOP_CONFIG)
        )
    )
    # A flat price replaces the band outright, and is not multiplied
    # afterwards: campaign-only units by category, and build-limited
    # buildings, which the Gem scale prices as one number rather than by
    # where a credit cost nobody pays happens to fall.
    overridden = sorted(
        target for target in ore_report
        if _flat_override(target, live_gem, SHOP_CONFIG)
    )
    flat_override_valid = bool(
        overridden
        and all(
            unit_access_price(target, live_gem)
            == _flat_override(target, live_gem, SHOP_CONFIG)
            for target in overridden
        )
        # Ore declares no flat prices, so the same targets stay derived there.
        and not any(
            _flat_override(target, ore, SHOP_CONFIG) for target in ore_report
        )
        # Campaign-only outranks build-limited: a campaign building takes the
        # campaign price, not the building one.
        and _flat_override('NACLONS', live_gem, SHOP_CONFIG)
        == live_gem.campaign_building
        and _flat_override('NACLON', live_gem, SHOP_CONFIG)
        == live_gem.build_limited_building
    )
    # An upgrade costs a floor plus a share of what its target costs, on
    # whichever scale is being asked. The floor is what stopped the early
    # shelf being nearly free: a share alone priced a cheap unit's upgrade
    # at a fraction of an expensive one's, when both are one shelf slot to
    # whoever is buying. The Ore side floors at minimum_shop_price, so it is
    # compared before the discount path rather than after.
    buff_ratio_valid = all(
        unit_buff_price(target, scale) == max(
            1,
            round(
                scale.buff_flat_price
                + unit_access_price(target, scale)
                * scale.buff_percent_of_access / 100
            ),
        )
        for scale in (ore, pricing)
        for target in sorted(ore_report)[:40]
    )
    # And the range really is compressed: the dearest upgrade is no longer
    # many times the cheapest one.
    # Only the targets that have an upgrade offer: some units are sold and
    # never improved.
    ore_buffs = []
    for target in sorted(ore_report):
        try:
            ore_buffs.append(unit_buff_price(target, ore))
        except ValueError:
            continue
    buff_ratio_valid = bool(
        buff_ratio_valid
        and ore_buffs
        # Sevenfold between the cheapest upgrade and the dearest. Without
        # the floor it was more than twelvefold, and the early shelf was
        # bought out rather than chosen from.
        and max(ore_buffs) <= min(ore_buffs) * 7
    )
    # Powers have no cost, so tier decides outright and the flagged ones --
    # superweapons and campaign-only powers -- are flat and steep.
    power_targets = {
        entry.target_id for entry in shop_catalogue()
        if entry.reward_type is ShopRewardType.POWER_ACCESS
    }
    flagged_powers = {
        target for target in power_targets if power_is_flagged(target)
    }
    power_price_valid = bool(
        flagged_powers
        and power_targets - flagged_powers
        and all(
            power_access_price(target, ore) == ore.flagged_power_price
            for target in flagged_powers
        )
        and all(
            power_access_price(target, ore)
            == ore.power_tier_prices[power_access_tier(target)]
            for target in power_targets - flagged_powers
        )
        and len(
            {power_access_price(target, ore)
             for target in power_targets - flagged_powers}
        ) == 3
    )
    return {
        'unit_cost_sources': unit_cost_sources(),
        'gem_price_coverage_valid': coverage_valid,
        'ore_price_tier_band_valid': ore_band_valid,
        'ore_price_premium_multiplier_valid': premium_valid,
        'flat_override_price_valid': flat_override_valid,
        'price_buff_ratio_valid': buff_ratio_valid,
        'power_price_tier_valid': power_price_valid,
        'gem_price_tier_band_valid': band_valid,
        'gem_price_tier_dominates_cost_valid': tier_order_valid,
        'gem_price_cost_spread_valid': cost_spread_valid,
        'gem_price_unique_flat_valid': unique_valid,
        'gem_price_limited_building_valid': limited_building_valid,
    }


def _run_setup_checks():
    """What is kept of the next run's setup, and what deliberately is not.

    Two windows read these settings and two windows write them, so the
    round trip is what matters: a choice comes back as it was made, a
    value at the baseline is never written down -- a rebalance of
    shop_mode.json has to reach a player who never moved that control --
    and a settings file somebody has edited by hand still leaves every
    control on a number the launcher would offer.

    A run is not part of this. Its pacing is snapshotted when it starts.
    """
    baseline = {
        key: getattr(SHOP_CONFIG, field)
        for key, (field, _low, _high) in RUN_PACING_SETTINGS.items()
    }
    modifier_ids = list(SHOP_CONFIG.modifiers)
    first = modifier_ids[0] if modifier_ids else ''
    kept = {
        PACING_SETTING_KEY: pacing_to_store(
            {**baseline, 'shop_stage_length': 4}
        ),
        MODIFIER_SETTING_KEY: [first],
    }
    read_back = configured_pacing(kept)
    _field, _low, highest = RUN_PACING_SETTINGS['shop_stage_length']
    edited = {
        PACING_SETTING_KEY: {'shop_stage_length': 99, 'not_a_setting': 1},
        MODIFIER_SETTING_KEY: ['not_a_modifier', first],
    }
    return {
        'shop_run_setup_round_trip_valid': bool(
            modifier_ids
            and kept[PACING_SETTING_KEY] == {'shop_stage_length': 4}
            and read_back['shop_stage_length'] == 4
            and read_back['shop_stage_income_percent']
            == baseline['shop_stage_income_percent']
            and configured_modifiers(kept) == (first,)
        ),
        'shop_run_setup_keeps_no_baseline_valid': bool(
            pacing_to_store(baseline) == {}
            and configured_pacing({}) == baseline
            and configured_pacing({PACING_SETTING_KEY: {}}) == baseline
        ),
        'shop_run_setup_survives_an_edited_file_valid': bool(
            configured_pacing(None) == baseline
            and configured_pacing({PACING_SETTING_KEY: 'nonsense'}) == baseline
            and configured_pacing(edited)['shop_stage_length'] == highest
            and configured_modifiers(edited) == (first,)
            and configured_modifiers({MODIFIER_SETTING_KEY: 'nope'}) == ()
            and configured_modifiers(None) == ()
        ),
    }


def validate_shop_domain():
    malformed_config = load_static_config('shop_mode.json')
    malformed_config['settings']['run_length'] = 0
    try:
        validate_sections('shop_mode.json', malformed_config, 'shop-self-check')
        config_validation_valid = False
    except StaticConfigError:
        config_validation_valid = True
    flat_meta_config = load_static_config('shop_mode.json')
    flat_meta_config['mission_rewards']['act_2']['meta_coins'] = 1
    try:
        validate_sections('shop_mode.json', flat_meta_config, 'shop-self-check')
        config_validation_valid = False
    except StaticConfigError:
        pass
    invalid_difficulty_config = load_static_config('shop_mode.json')
    invalid_difficulty_config['stage_difficulty_weights'][0]['weights'][
        'Normal'
    ] = -1
    try:
        validate_sections(
            'shop_mode.json', invalid_difficulty_config, 'shop-self-check'
        )
        config_validation_valid = False
    except StaticConfigError:
        pass
    invalid_price_config = load_static_config('shop_mode.json')
    invalid_price_config['price_scales']['run_ore']['tier_prices'][
        'tier_1'
    ] = [60, 40]
    try:
        validate_sections(
            'shop_mode.json', invalid_price_config, 'shop-self-check'
        )
        config_validation_valid = False
    except StaticConfigError:
        pass
    invalid_power_price_config = load_static_config('shop_mode.json')
    invalid_power_price_config['power_target_prices'][
        'NUKESPECIAL'
    ]['run_access'] = 0
    try:
        validate_sections(
            'shop_mode.json', invalid_power_price_config, 'shop-self-check'
        )
        config_validation_valid = False
    except StaticConfigError:
        pass
    hidden_offer_config = load_static_config('shop_mode.json')
    hidden_offer_config['modifiers']['blind_choice']['effects'][
        'hidden_offer_count'
    ] = -1
    try:
        validate_sections(
            'shop_mode.json', hidden_offer_config, 'shop-self-check'
        )
        config_validation_valid = False
    except StaticConfigError:
        pass
    mixed_modifier_config = load_static_config('shop_mode.json')
    mixed_modifier_config['modifiers']['greedy']['effects'][
        'meta_reward_flat'
    ] = 1
    try:
        validate_sections(
            'shop_mode.json', mixed_modifier_config, 'shop-self-check'
        )
        config_validation_valid = False
    except StaticConfigError:
        pass

    act_one = mission_reward(MissionEconomyClass.ACT_1)
    operation = mission_reward(
        MissionEconomyClass.OPERATION, victory_coin_bonus_level=3
    )
    capped_bonus = mission_reward(
        MissionEconomyClass.OPERATION, victory_coin_bonus_level=999
    )
    failed = mission_reward(MissionEconomyClass.FINALE, successful=False)
    meta_rewards_by_difficulty = [
        mission_reward(class_id).meta_coins
        for class_id in (
            MissionEconomyClass.ACT_1,
            MissionEconomyClass.ACT_2,
            MissionEconomyClass.OPERATION,
            MissionEconomyClass.FINALE,
        )
    ]
    starting_credit_upgrade = SHOP_CONFIG.permanent_upgrades[
        'mission_starting_credits'
    ]
    starting_credit_reward = canonical_reward_for_id(
        'Starting Credits +1,000'
    )
    unavailable_price_valid = True
    for price_function, target_id in (
        (run_unit_price, 'CMIN'),
        (run_buff_price, 'GAGAP'),
    ):
        try:
            price_function(target_id)
            unavailable_price_valid = False
        except ValueError:
            pass
    # A mission pays 30% less Ore than it did. What it pays in the permanent
    # currency is untouched: that ladder is a different pace and was not
    # what made a run's shopping feel like a list rather than a choice.
    economy_valid = bool(
        (act_one.run_coins, act_one.meta_coins) == (52, 20)
        and operation.run_coins == 197
        and operation.meta_coins == 50
        and operation.victory_bonus_run_coins == 75
        and capped_bonus.victory_bonus_run_coins == 125
        and len(SHOP_CONFIG.price_scales) == 2
        and len(SHOP_CONFIG.power_target_prices) == 94
        # The classic superweapons are premium powers, so they take the flat
        # price rather than any tier's.
        and all(
            power_access_price(
                target_id, SHOP_CONFIG.price_scales['run_ore']
            ) == SHOP_CONFIG.price_scales['run_ore'].flagged_power_price
            for target_id in (
                'LIGHTNINGSTORMSPECIAL',
                'NUKESPECIAL',
                'PSYCHICDOMINATORSPECIAL',
                'GREATTEMPESTSPECIAL',
            )
        )
        # Named units, asserted against their own tier's range rather than a
        # remembered number, so a retiered unit fails loudly instead of
        # quietly asserting the wrong band.
        and all(
            SHOP_CONFIG.price_scales['run_ore'].tier_prices[
                unit_access_tier(target_id)
            ][0] <= run_unit_price(target_id)
            <= SHOP_CONFIG.price_scales['run_ore'].tier_prices[
                unit_access_tier(target_id)
            ][1]
            for target_id in ('E1', 'AHMV', 'SPY')
        )
        and run_unit_price('STARDUSTB') == unit_access_price(
            'STARDUSTB', SHOP_CONFIG.price_scales['run_ore']
        )
        and run_buff_price('SPY') >= SHOP_CONFIG.minimum_shop_price
        and run_buff_price('STARDUSTB') == unit_buff_price(
            'STARDUSTB', SHOP_CONFIG.price_scales['run_ore']
        )
        and (failed.run_coins, failed.meta_coins) == (0, 0)
        and meta_rewards_by_difficulty == [20, 30, 50, 70]
        and discounted_shop_price(0, shop_discount_level=999) == 10
        and 280 <= permanent_unit_price('SPY') <= 380
        # A campaign-only superunit: 750 for being a hero, four times over
        # for being one no skirmish game offers.
        # A campaign-only superunit: Gems price owning one at a flat rate
        # for its category rather than off a credit cost nobody pays.
        and permanent_unit_price('STARDUSTB')
        == SHOP_CONFIG.price_scales['permanent_gem'].campaign_unit
        and unavailable_price_valid
        and starting_run_coins(starting_capital_level=999) == 1250
        and starting_credit_upgrade.max_level == 20
        and starting_credit_upgrade.effects['credits_per_level'] == 1000
        and starting_credit_upgrade.max_level
        * starting_credit_upgrade.effects['credits_per_level'] == 20000
        and starting_credit_reward.get('credits_per_stack') == 1000
        and starting_credit_reward.get('maximum_credits') == 20000
    )

    difficulty_samples = {
        stage: Counter(
            mission_difficulty(
                f'SHOP-DIFFICULTY-{sample}', stage, 'SAMPLE'
            )
            for sample in range(1000)
        )
        for stage in (
            _closing_mission(1), _closing_mission(3),
            _closing_mission(5), _closing_mission(8),
        )
    }
    tier_one, tier_three, tier_five, tier_eight = (
        _closing_mission(1), _closing_mission(3),
        _closing_mission(5), _closing_mission(8),
    )
    stage_game_difficulty_valid = bool(
        mission_difficulty_weights_for_stage(_closing_mission(1))
        == {'Casual': 85, 'Normal': 15, 'Mental': 0}
        and mission_difficulty_weights_for_stage(_closing_mission(2))
        == {'Casual': 55, 'Normal': 45, 'Mental': 0}
        and mission_difficulty_weights_for_stage(_closing_mission(4))
        == {'Casual': 25, 'Normal': 65, 'Mental': 10}
        and mission_difficulty_weights_for_stage(_closing_mission(7))
        == {'Casual': 10, 'Normal': 60, 'Mental': 30}
        and difficulty_samples[tier_one]['Mental'] == 0
        and difficulty_samples[tier_three]['Normal']
        > difficulty_samples[tier_three]['Casual']
        and all(difficulty_samples[tier_three][name] > 0 for name in (
            'Casual', 'Normal', 'Mental'
        ))
        and difficulty_samples[tier_five]['Mental']
        > difficulty_samples[tier_five]['Casual']
        and difficulty_samples[tier_eight]['Mental']
        > difficulty_samples[tier_eight]['Normal']
        and mission_difficulty('DETERMINISTIC', 6, 'SAMPLE')
        == mission_difficulty('DETERMINISTIC', 6, 'SAMPLE')
    )

    catalogue = shop_catalogue()
    access_entries = [
        entry for entry in catalogue
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
    ]
    buff_entries = [
        entry for entry in catalogue
        if entry.reward_type is ShopRewardType.UNIT_BUFF
        and entry.stack_limit is not None
    ]
    power_entries = [
        entry for entry in catalogue
        if entry.reward_type is ShopRewardType.POWER_ACCESS
    ]
    gi_access = _reward('GI Access')
    gi_buff_entry = next(entry for entry in buff_entries if entry.target_id == 'E1')
    gi_buff = _reward(gi_buff_entry.reward_id)
    blocked_buff = validate_run_purchase(
        gi_buff,
        price=1,
        run_coins=10,
        active_tech_ids=(),
    )
    allowed_buff = validate_run_purchase(
        gi_buff,
        price=1,
        run_coins=10,
        active_tech_ids=('E1',),
    )
    capped_buff = validate_run_purchase(
        gi_buff,
        price=1,
        run_coins=10,
        active_tech_ids=('E1',),
        current_stacks=gi_buff_entry.stack_limit,
    )
    committed_purchase = validate_run_purchase(
        gi_access,
        price=1,
        run_coins=10,
        mission_committed=True,
    )
    purchase_rules_valid = bool(
        access_entries
        and buff_entries
        and power_entries
        and blocked_buff.result is PurchaseResult.REQUIRES_UNIT_ACCESS
        and allowed_buff.result is PurchaseResult.OK
        and capped_buff.result is PurchaseResult.MAX_STACKS
        and committed_purchase.result
        is PurchaseResult.PURCHASE_LOCKED_DURING_MISSION
        and not tech_ids_for_rewards([gi_buff])
    )

    profile = ShopProfile(meta_coins=100)
    first_purchase = purchase_permanent_unit(profile, gi_access, price=10)
    repeated_purchase = purchase_permanent_unit(
        first_purchase.profile, gi_access, price=10
    )
    # A profile that bought permanent buffs before the Gem shop stopped
    # selling them still has to load and still has to apply them, so the
    # roundtrip is asserted over a profile carrying one.
    legacy_profile = replace(
        first_purchase.profile,
        permanent_buffs=(BuffPurchase(gi_buff_entry.reward_id, 1),),
    )
    restored_profile = normalize_shop_profile(legacy_profile.to_dict())
    permanent_purchase_valid = bool(
        first_purchase.validation.result is PurchaseResult.OK
        and first_purchase.profile.meta_coins == 90
        and repeated_purchase.validation.result is PurchaseResult.ALREADY_OWNED
        and repeated_purchase.profile.meta_coins == 90
        and restored_profile == legacy_profile
        and not hasattr(ShopProgressionService, 'purchase_permanent_buff')
    )

    nonstarter_entries = []
    seen_targets = {'E1'}
    for entry in access_entries:
        if entry.target_id in seen_targets:
            continue
        seen_targets.add(entry.target_id)
        nonstarter_entries.append(entry)
        if len(nonstarter_entries) == 6:
            break
    five_extras = [entry.reward_id for entry in nonstarter_entries[:5]]
    six_extras = [entry.reward_id for entry in nonstarter_entries]
    entitlements = ['GI Access', *six_extras]
    accepted_loadout = validate_starting_loadout(
        starter_tech_ids=('E1',),
        selected_reward_ids=('GI Access', *five_extras),
        entitled_reward_ids=entitlements,
    )
    rejected_loadout = validate_starting_loadout(
        starter_tech_ids=('E1',),
        selected_reward_ids=six_extras,
        entitled_reward_ids=entitlements,
    )
    loadout_valid = bool(
        len(nonstarter_entries) == 6
        and accepted_loadout.allowed
        and accepted_loadout.extra_slots_used == 5
        and rejected_loadout.result is PurchaseResult.MAX_LOADOUT_SIZE
    )
    first_stock = rotating_unit_inventory(
        access_entries,
        run_seed='SHOP-INVENTORY-CHECK',
        stage=1,
        offer_count=SHOP_CONFIG.unit_inventory_size,
    )
    repeated_stock = rotating_unit_inventory(
        tuple(reversed(access_entries)),
        run_seed='SHOP-INVENTORY-CHECK',
        stage=1,
        offer_count=SHOP_CONFIG.unit_inventory_size,
    )
    next_stock = rotating_unit_inventory(
        access_entries,
        run_seed='SHOP-INVENTORY-CHECK',
        stage=2,
        offer_count=SHOP_CONFIG.unit_inventory_size,
    )
    rotating_inventory_valid = bool(
        len(first_stock) == SHOP_CONFIG.unit_inventory_size
        and first_stock == repeated_stock
        and {entry.reward_id for entry in first_stock}
        != {entry.reward_id for entry in next_stock}
    )
    owned_unit_target = first_stock[0].target_id
    filtered_unit_stock = rotating_unit_inventory(
        access_entries,
        run_seed='SHOP-INVENTORY-CHECK',
        stage=1,
        offer_count=SHOP_CONFIG.unit_inventory_size,
        excluded_target_ids=(owned_unit_target,),
    )
    repeated_filtered_unit_stock = rotating_unit_inventory(
        tuple(reversed(access_entries)),
        run_seed='SHOP-INVENTORY-CHECK',
        stage=1,
        offer_count=SHOP_CONFIG.unit_inventory_size,
        excluded_target_ids=(owned_unit_target,),
    )
    owned_unit_stock_excluded = bool(
        len(filtered_unit_stock) == SHOP_CONFIG.unit_inventory_size
        and filtered_unit_stock == repeated_filtered_unit_stock
        and all(
            entry.target_id != owned_unit_target
            for entry in filtered_unit_stock
        )
        and {
            entry.reward_id for entry in first_stock
            if entry.target_id != owned_unit_target
        }.issubset(entry.reward_id for entry in filtered_unit_stock)
    )
    power_entries = [
        entry for entry in catalogue
        if entry.reward_type is ShopRewardType.POWER_ACCESS
    ]
    power_stock = rotating_power_inventory(
        power_entries,
        run_seed='SHOP-INVENTORY-CHECK',
        stage=1,
        offer_count=SHOP_CONFIG.power_inventory_size,
    )
    repeated_power_stock = rotating_power_inventory(
        tuple(reversed(power_entries)),
        run_seed='SHOP-INVENTORY-CHECK',
        stage=1,
        offer_count=SHOP_CONFIG.power_inventory_size,
    )
    rotating_power_inventory_valid = bool(
        len(power_stock) == SHOP_CONFIG.power_inventory_size
        and power_stock == repeated_power_stock
        and all(
            entry.reward_type is ShopRewardType.POWER_ACCESS
            for entry in power_stock
        )
    )
    owned_power_target = power_stock[0].target_id
    filtered_power_stock = rotating_power_inventory(
        power_entries,
        run_seed='SHOP-INVENTORY-CHECK',
        stage=1,
        offer_count=SHOP_CONFIG.power_inventory_size,
        excluded_target_ids=(owned_power_target,),
    )
    owned_power_stock_excluded = bool(
        len(filtered_power_stock) == SHOP_CONFIG.power_inventory_size
        and all(
            entry.target_id != owned_power_target
            for entry in filtered_power_stock
        )
        and {
            entry.reward_id for entry in power_stock
            if entry.target_id != owned_power_target
        }.issubset(entry.reward_id for entry in filtered_power_stock)
    )

    mission_pool = [
        {
            'code': 'SC_A1_HERO',
            'reward_class': 'act_1',
            'true_no_build': True,
        },
        {'code': 'SC_A1_1', 'reward_class': 'act_1'},
        {'code': 'SC_A1_2', 'reward_class': 'act_1'},
        {'code': 'SC_A1_3', 'reward_class': 'act_1'},
        {'code': 'SC_A2_1', 'reward_class': 'act_2'},
        {'code': 'SC_A2_2', 'reward_class': 'act_2'},
        {'code': 'SC_A2_3', 'reward_class': 'act_2'},
        {'code': 'SC_OP_1', 'reward_class': 'operation'},
        {'code': 'SC_OP_2', 'reward_class': 'operation'},
        {'code': 'SC_OP_3', 'reward_class': 'operation'},
        {'code': 'SC_FIN_1', 'reward_class': 'finale'},
        {'code': 'SC_FIN_2', 'reward_class': 'finale'},
        {'code': 'SC_FIN_3', 'reward_class': 'finale'},
    ]
    offers = generate_mission_offers(
        mission_pool, run_seed='SHOP-SELF-CHECK', stage=1
    )
    rerolled = generate_mission_offers(
        mission_pool,
        run_seed='SHOP-SELF-CHECK',
        stage=1,
        reroll_count=1,
        previous_offer_codes=[offer.mission_code for offer in offers],
    )
    completed_code = offers[0].mission_code
    after_completion = generate_mission_offers(
        mission_pool,
        run_seed='SHOP-SELF-CHECK',
        stage=2,
        completed_codes=(completed_code,),
    )
    mission_rules_valid = bool(
        len(offers) == 3
        and len({offer.mission_code for offer in offers}) == 3
        and {
            offer.economy_class for offer in offers
        } == {MissionEconomyClass.ACT_1}
        and 'SC_A1_HERO' in {
            offer.mission_code for offer in offers
        }
        and mission_classes_for_stage(1) == {
            MissionEconomyClass.ACT_1
        }
        and MissionEconomyClass.FINALE
        not in mission_classes_for_stage(_closing_mission(2))
        and MissionEconomyClass.FINALE
        in mission_classes_for_stage(_closing_mission(6))
        and offers == generate_mission_offers(
            mission_pool, run_seed='SHOP-SELF-CHECK', stage=1
        )
        and {offer.mission_code for offer in rerolled}
        != {offer.mission_code for offer in offers}
        and completed_code not in {
            offer.mission_code for offer in after_completion
        }
        and classify_mission({'code': 'AREDDAWN'})
        is MissionEconomyClass.ACT_1
        and classify_mission({'code': 'ADEMON'})
        is MissionEconomyClass.OPERATION
    )
    modifier_samples = [
        mission_modifier_for_offer(
            'SHOP-MODIFIER-CHECK',
            1,
            MissionOffer(f'SC_MOD_{index}', MissionEconomyClass.ACT_1),
        )
        for index in range(100)
    ]
    active_modifiers = [item for item in modifier_samples if item is not None]
    late_modifier_samples = [
        mission_modifier_for_offer(
            'SHOP-MODIFIER-CHECK',
            _closing_mission(1),
            MissionOffer(f'SC_MOD_{index}', MissionEconomyClass.ACT_1),
        )
        for index in range(100)
    ]
    early_challenges = sum(
        bool(item and item.challenge) for item in modifier_samples
    )
    early_boons = sum(
        bool(item and not item.challenge) for item in modifier_samples
    )
    late_challenges = sum(
        bool(item and item.challenge) for item in late_modifier_samples
    )
    late_boons = sum(
        bool(item and not item.challenge) for item in late_modifier_samples
    )
    challenge = next(
        (item for item in late_modifier_samples if item and item.challenge),
        None,
    )
    challenge_reward = mission_reward(
        MissionEconomyClass.ACT_1,
        mission_modifier=challenge,
    ) if challenge is not None else None
    mission_modifier_valid = bool(
        active_modifiers
        and challenge is not None
        and challenge_reward.mission_bonus_run_coins
        == challenge.bonus_run_coins
        and challenge_reward.mission_bonus_meta_coins
        == challenge.bonus_meta_coins
        and mission_modifier_for_offer(
            'SHOP-MODIFIER-CHECK',
            1,
            MissionOffer('SC_OPERATION', MissionEconomyClass.OPERATION),
        ) is None
    )
    # Every offer on a stage-closing mission is a challenge and no offer
    # between them ever is, so the split is all-or-nothing rather than a
    # curve. Sampling both sides proves the rule holds on every offer.
    mission_modifier_curve_valid = bool(
        early_challenges == 0
        and early_boons
        and late_boons == 0
        and late_challenges == len(late_modifier_samples)
    )
    configured_effect_reward_ids = {
        reward_id
        for modifier in MISSION_MODIFIERS
        for reward_id in (
            *modifier.player_reward_ids,
            *((modifier.enemy_reward_id,) if modifier.enemy_reward_id else ()),
        )
    }
    owned_aid_powers = {
        'Great Tempest Power',
        'Paladin Aid Power',
        'Drakuv Prison Vehicle Power',
    }
    owned_modifier_samples = [
        mission_modifier_for_offer(
            'SHOP-OWNED-MODIFIER-CHECK',
            1,
            MissionOffer(f'SC_OWNED_MOD_{index}', MissionEconomyClass.ACT_1),
            owned_reward_ids=owned_aid_powers,
        )
        for index in range(100)
    ]
    mission_modifier_variety_valid = bool(
        {
            'Lightning Storm Power',
            'Nuclear Missile Power',
            'Psychic Dominator Power',
            'Great Tempest Power',
            'Paladin Aid Power',
            'Drakuv Prison Vehicle Power',
            'Engineering Team Power',
            'Moon Reinforcements Power',
        }.issubset(
            configured_effect_reward_ids
        )
        and {'paladin_support', 'drakuv_support'}.issubset(
            modifier.id for modifier in active_modifiers
        )
        and configured_effect_reward_ids.issubset(REWARD_BY_NAME)
        and any(
            modifier is not None and not modifier.challenge
            for modifier in owned_modifier_samples
        )
    )
    mission_modifier_choices_unique = True
    for sample in range(100):
        sample_offers = tuple(
            MissionOffer(
                f'SC_UNIQUE_{sample}_{index}', MissionEconomyClass.ACT_1
            )
            for index in range(3)
        )
        for stage in (1, 6):
            sample_run = ShopRun(
                run_id=f'shop-modifier-unique-{sample}-{stage}',
                seed=f'SHOP-MODIFIER-UNIQUE-{sample}',
                status=RunStatus.ACTIVE,
                stage=stage,
                run_length=SHOP_CONFIG.run_length,
                run_coins=0,
                mission_offers=sample_offers,
            )
            resolved_ids = [
                modifier.id
                for offer in sample_offers
                if (
                    modifier := mission_modifier_for_run_offer(
                        sample_run, offer
                    )
                ) is not None
            ]
            if len(resolved_ids) != len(set(resolved_ids)):
                mission_modifier_choices_unique = False
                break
    shop_airfield_rules = {
        aircraft_family: _tier_one_airfield_rules(
            {'soviets'}, {aircraft_family}, (), (), chaos_mode=True
        )
        for aircraft_family in ('allies', 'soviets', 'epsilon', 'foehn')
    }
    shop_single_airfield_valid = bool(
        all(len(rules) <= 1 for rules in shop_airfield_rules.values())
        and all(
            len(shop_airfield_rules[family]) == 1
            for family in ('allies', 'soviets', 'epsilon')
        )
    )

    run = ShopRun(
        run_id='shop-self-check-run',
        seed='SHOP-SELF-CHECK',
        status=RunStatus.ACTIVE,
        stage=1,
        run_length=SHOP_CONFIG.run_length,
        run_coins=SHOP_CONFIG.starting_run_coins,
        rerolls_used=1,
        difficulty_assists_used=1,
        assisted_mission_code=offers[0].mission_code,
        starting_unit_ids=('MOR_T1_INFANTRY',),
        starting_defense_ids=('MOR_T1_DEFENSES',),
        permanent_buffs_snapshot=(BuffPurchase(gi_buff_entry.reward_id, 1),),
        mission_offers=offers,
    )
    restored_run = normalize_shop_run(run.to_dict())
    malformed_run = run.to_dict()
    malformed_run['modifiers'] = ['unknown_modifier']
    try:
        normalize_shop_run(malformed_run)
        invalid_state_rejected = False
    except ShopStateError:
        invalid_state_rejected = True
    kept = tuple(offers[1:])
    replacement_offer = generate_mission_offers(
        mission_pool,
        run_seed=run.seed,
        stage=run.stage,
        reroll_count=run.rerolls_used + 1,
        completed_codes=tuple(offer.mission_code for offer in kept),
        previous_offer_codes=(offers[0].mission_code,),
        offer_count=1,
    )
    targeted_reroll = reroll_missions(
        replace(run, assisted_mission_code=None),
        (replacement_offer[0], *kept),
        maximum_rerolls=3,
        replaced_mission_code=offers[0].mission_code,
    )
    assisted = apply_mission_difficulty_assist(
        replace(run, difficulty_assists_used=0, assisted_mission_code=None),
        offers[1].mission_code,
        maximum_assists=1,
    )
    mission_actions_valid = bool(
        targeted_reroll.mission_offers[1:] == kept
        and targeted_reroll.mission_offers[0] != offers[0]
        and targeted_reroll.rerolls_used == 2
        and assisted.assisted_mission_code == offers[1].mission_code
        and assisted.difficulty_assists_used == 1
    )
    state_round_trip_valid = bool(
        restored_run == run
        and restored_run.mission_offers == offers
        and restored_run.rerolls_used == 1
        and restored_run.difficulty_assists_used == 1
        and restored_run.permanent_buffs_snapshot
        == (BuffPurchase(gi_buff_entry.reward_id, 1),)
        and restored_run.starting_unit_ids == ('MOR_T1_INFANTRY',)
        and normalize_shop_run(None) is None
        and invalid_state_rejected
    )

    # Exclusion groups are measured against the whole catalogue, so the
    # count proves each one also removes the buffs that target its units,
    # not just the access entry a reader would notice missing.
    def visible_entries(settings):
        excluded = run_excluded_target_ids(settings)
        return sum(
            1 for entry in shop_catalogue()
            if shop_entry_available(
                entry,
                campaign_filter='All Campaigns',
                reward_mode=SHOP_ACCESS_REWARD_MODE,
                strict_faction=True,
                excluded_target_ids=excluded,
            )
        )

    _all_visible = visible_entries({})
    # Every surcharged target the permanent shop actually sells, which is
    # the campaign-unit group; the power groups name superweapons, which the
    # permanent shop has no offer for.
    gem_scale = SHOP_CONFIG.price_scales['permanent_gem']
    ore_scale = SHOP_CONFIG.price_scales['run_ore']
    surcharge_targets = sorted({
        entry.target_id for entry in catalogue
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
        and permanent_target_surcharged(entry.target_id)
    })
    hidden_by_group = {
        group.id: _all_visible - visible_entries({group.setting_key: True})
        for group in SHOP_CONFIG.reward_exclusion_groups
    }

    details = {
        'config_validation_valid': config_validation_valid,
        'economy_valid': economy_valid,
        'stage_game_difficulty_valid': stage_game_difficulty_valid,
        'catalogue_valid': len(catalogue) > 100,
        'archipelago_cameo_asset_valid': bool(
            ARCHIPELAGO_CAMEO_PATH.is_file()
            and ARCHIPELAGO_CAMEO_PATH.read_bytes().startswith(
                b'\x89PNG\r\n\x1a\n'
            )
        ),
        'archipelago_purchase_display_valid': bool(
            archipelago_purchase_placement_text({
                'item_name': 'Progressive Sword',
                'item': 42,
                'recipient_player': 'Link',
                'player': 3,
                'recipient_game': 'A Link to the Past',
            }) == (
                'Progressive Sword',
                'Link (A Link to the Past)',
            )
            and archipelago_purchase_placement_text({}) == (
                'Awaiting server details', '—'
            )
        ),
        'shop_reward_exclusions_valid': bool(
            'Foehn Blast Trench Access' in SHOP_CONFIG.excluded_reward_ids
            and all(
                entry.reward_id != 'Foehn Blast Trench Access'
                for entry in catalogue
            )
        ),
        # A group whose ids match nothing would leave the checkbox claiming
        # to hide rewards it never touches, and a group that only hides the
        # access entry would leave the unit's buffs on the shelf.
        'shop_exclusion_groups_valid': bool(
            SHOP_CONFIG.reward_exclusion_groups
            and all(
                group.target_ids
                and hidden_by_group[group.id] > len(group.target_ids)
                and not run_excluded_target_ids({}).intersection(
                    group.target_ids
                )
                and run_excluded_target_ids(
                    {group.setting_key: True}
                ) == group.target_ids
                for group in SHOP_CONFIG.reward_exclusion_groups
            )
            and sum(hidden_by_group.values()) == visible_entries({}) - (
                visible_entries({
                    group.setting_key: True
                    for group in SHOP_CONFIG.reward_exclusion_groups
                })
            )
        ),
        # One rule, two numbers. Every one-off costs its scale's multiple on
        # both currencies, and an ordinary unit costs list price on both. The
        # named three are the three ways in: a build-limited hero, a
        # build-limited building, and a defense limited to two rather than one
        # -- that last is what the old 'BuildLimit == 1' reading missed.
        'shop_exclusion_gem_surcharge_valid': bool(
            surcharge_targets
            and gem_scale.reward_pool_multiplier > 1
            and all(
                permanent_unit_price(target) == (
                    _flat_override(target, gem_scale, SHOP_CONFIG)
                    or unit_access_price(target, _plain_scale(gem_scale))
                    * gem_scale.reward_pool_multiplier
                )
                and permanent_target_surcharged(target)
                for target in surcharge_targets
            )
            # Build limits come from the installed rules, so any number of
            # them counts and a Cloning Vat capped at two is a one-off just
            # as a hero capped at one is. Tanya is the control: build-limited
            # but not campaign-only, so Ore charges her and Gems do not.
            and all(one_off_target(target) for target in ('TANY', 'NACLON'))
            and unit_pricing_traits('NACLON').get('build_limit') == 2
            and not reward_pool_target('TANY')
            and not permanent_target_surcharged('E1')
            and permanent_unit_price('E1') == unit_access_price(
                'E1', gem_scale
            )
            and run_unit_price('E1') == unit_access_price('E1', ore_scale)
        ),
        'shop_exact_access_mode_valid': SHOP_ACCESS_REWARD_MODE == 'Chaos',
        'shop_single_airfield_valid': shop_single_airfield_valid,
        'purchase_rules_valid': purchase_rules_valid,
        'permanent_purchase_valid': permanent_purchase_valid,
        'loadout_valid': loadout_valid,
        'rotating_inventory_valid': rotating_inventory_valid,
        'rotating_power_inventory_valid': rotating_power_inventory_valid,
        'owned_access_stock_excluded_valid': bool(
            owned_unit_stock_excluded and owned_power_stock_excluded
        ),
        'mission_rules_valid': mission_rules_valid,
        'mission_modifier_valid': mission_modifier_valid,
        'mission_modifier_curve_valid': mission_modifier_curve_valid,
        'mission_modifier_variety_valid': mission_modifier_variety_valid,
        'mission_modifier_choices_unique_valid': (
            mission_modifier_choices_unique
        ),
        'mission_actions_valid': mission_actions_valid,
        'state_round_trip_valid': state_round_trip_valid,
        'catalogue_entries': len(catalogue),
    }
    details.update(_phase_two_checks(mission_pool))
    details.update(_phase_integrity_checks())
    details.update(_run_list_checks())
    details.update(_phase_four_checks())
    details.update(_phase_five_checks())
    details.update(_phase_six_checks())
    details.update(_phase_seven_checks())
    details.update(_permanent_feature_checks(mission_pool))
    details.update(_requested_upgrade_modifier_checks())
    details.update(_upgrade_reward_checks())
    details.update(_gem_pricing_checks())
    details.update(_run_setup_checks())
    details['valid'] = all(
        value for key, value in details.items()
        if key.endswith('_valid')
    )
    return details
