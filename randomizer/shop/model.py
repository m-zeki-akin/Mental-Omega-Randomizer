"""Data structures shared by pure Shop Mode rules."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


SHOP_PROFILE_SCHEMA_VERSION = 1
SHOP_RUN_SCHEMA_VERSION = 2
SHOP_ACCESS_REWARD_MODE = 'Chaos'


class MissionEconomyClass(str, Enum):
    ACT_1 = 'act_1'
    ACT_2 = 'act_2'
    OPERATION = 'operation'
    FINALE = 'finale'


class RunStatus(str, Enum):
    ACTIVE = 'active'
    FAILED = 'failed'
    COMPLETED = 'completed'


class PurchaseResult(str, Enum):
    OK = 'ok'
    INSUFFICIENT_CURRENCY = 'insufficient_currency'
    ALREADY_OWNED = 'already_owned'
    REQUIRES_UNIT_ACCESS = 'requires_unit_access'
    MAX_STACKS = 'max_stacks'
    NOT_SHOP_ELIGIBLE = 'not_shop_eligible'
    RUN_NOT_ACTIVE = 'run_not_active'
    PURCHASE_LOCKED_DURING_MISSION = 'purchase_locked_during_mission'
    AP_NOT_CONNECTED = 'ap_not_connected'
    AP_LOCATION_ALREADY_CHECKED = 'ap_location_already_checked'
    MAX_LOADOUT_SIZE = 'max_loadout_size'
    NOT_ENTITLED = 'not_entitled'
    MAX_UPGRADE_LEVEL = 'max_upgrade_level'
    ALREADY_PURCHASED_THIS_STAGE = 'already_purchased_this_stage'


class ShopRewardType(str, Enum):
    UNIT_ACCESS = 'unit_access'
    UNIT_BUFF = 'unit_buff'
    POWER_ACCESS = 'power_access'
    POWER_BUFF = 'power_buff'


@dataclass(frozen=True)
class CurrencyReward:
    run_coins: int = 0
    meta_coins: int = 0
    base_run_coins: int = 0
    victory_bonus_run_coins: int = 0
    mission_bonus_run_coins: int = 0
    mission_bonus_meta_coins: int = 0
    challenge_hunter_run_coins: int = 0
    challenge_hunter_meta_coins: int = 0
    # What the victory handed over on top of the currency. Named rather than
    # counted so the victory line can say which units and upgrades arrived.
    granted_upgrade_ids: tuple[str, ...] = ()
    granted_unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MissionRewardDefinition:
    class_id: MissionEconomyClass
    display_name: str
    difficulty: int
    run_coins: int
    meta_coins: int


@dataclass(frozen=True)
class StageWeightProfile:
    # A through_stage of 0 marks the saturating final profile: it applies
    # to every stage past the last numbered one.
    through_stage: int
    weights: Mapping[MissionEconomyClass, int]


@dataclass(frozen=True)
class StageDifficultyProfile:
    through_stage: int
    weights: Mapping[str, int]


@dataclass(frozen=True)
class StageScoreCeiling:
    """Hardest mission that may be offered at a stage.

    Economy class decides the payout, not the difficulty: eleven of the
    twenty-five "operation" missions let the player build a base while
    others are late-campaign no-build set pieces. Gate offers on the
    reviewed stage score so an early operation roll cannot hand out a
    mission the run is not ready for. A maximum of 0 means no ceiling.
    """

    through_stage: int
    maximum_stage_score: int


@dataclass(frozen=True)
class EnemyBuffTier:
    """Permanent enemy buffs unlocked for challenge draws from a stage."""

    minimum_stage: int
    buff_ids: tuple[str, ...]


@dataclass(frozen=True)
class PermanentUpgradeDefinition:
    id: str
    display_name: str
    max_level: int
    prices: tuple[int, ...]
    effects: Mapping[str, int]
    purchasable: bool = True


@dataclass(frozen=True)
class ModifierDefinition:
    id: str
    display_name: str
    description: str
    effects: Mapping[str, int]


@dataclass(frozen=True)
class RewardExclusionGroup:
    """One optional shelf filter the player ticks before a run starts."""

    id: str
    setting_key: str
    display_name: str
    description: str
    target_ids: frozenset[str]


@dataclass(frozen=True)
class ShopTargetPriceDefinition:
    run_access: int | None
    run_buff: int | None
    permanent_buff: int | None


@dataclass(frozen=True)
class UnitAccessGemPricing:
    """How much owning a unit outright costs in Gems.

    Tier sets the band and cost only decides where inside it a unit sits.
    Unique and stolen-tech units ignore the band for a flat price, because
    what makes them worth having is that no one else can field one.
    """
    tier_gems: Mapping[str, int]
    cost_adjustment_minimum: int
    cost_adjustment_maximum: int
    cost_window_trim_percent: int
    unique_infantry_gems: int
    unique_unit_gems: int
    stolen_tech_gems: int
    rounding_step: int


@dataclass(frozen=True)
class ShopPowerPriceDefinition:
    run_access: int | None
    run_buff: int | None


@dataclass(frozen=True)
class ShopModeConfig:
    # Archipelago only. An AP slot needs a finite location count and a
    # goal, so AP runs still end after this many stages. Standalone runs
    # are endless and paced by stage_length.
    run_length: int
    stage_length: int
    starting_lives: int
    stage_income_percent_per_stage: int
    stage_gem_income_percent_per_stage: int
    challenge_reward_multiplier_percent: int
    permanent_enemy_buffs_per_challenge: int
    enemy_buff_escalation_stages: int
    mission_offer_count: int
    unit_inventory_size: int
    power_inventory_size: int
    upgrade_inventory_size: int
    mission_upgrade_reward_count: int
    mission_unit_gift_count: int
    max_selected_permanent_units: int
    starting_run_coins: int
    starting_rerolls: int
    maximum_starting_ore: int
    minimum_shop_price: int
    excluded_target_gem_price_multiplier: int
    reroll_policy: str
    archipelago_purchase_locations: int
    archipelago_purchase_meta_coin_cost: int
    archipelago_mission_victories_are_locations: bool
    excluded_reward_ids: tuple[str, ...]
    reward_exclusion_groups: tuple[RewardExclusionGroup, ...]
    mission_rewards: Mapping[MissionEconomyClass, MissionRewardDefinition]
    stage_class_weights: tuple[StageWeightProfile, ...]
    stage_difficulty_weights: tuple[StageDifficultyProfile, ...]
    stage_score_ceilings: tuple[StageScoreCeiling, ...]
    enemy_buff_stage_tiers: tuple[EnemyBuffTier, ...]
    power_target_prices: Mapping[str, ShopPowerPriceDefinition]
    unit_target_prices: Mapping[str, ShopTargetPriceDefinition]
    unit_access_gem_pricing: UnitAccessGemPricing
    permanent_upgrades: Mapping[str, PermanentUpgradeDefinition]
    modifiers: Mapping[str, ModifierDefinition]


@dataclass(frozen=True)
class MissionOffer:
    mission_code: str
    economy_class: MissionEconomyClass

    def to_dict(self) -> dict[str, str]:
        return {
            'mission_code': self.mission_code,
            'class': self.economy_class.value,
        }


@dataclass(frozen=True)
class PurchaseRecord:
    reward_id: str
    quantity: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {'reward_id': self.reward_id, 'quantity': self.quantity}


@dataclass(frozen=True)
class BuffPurchase:
    reward_id: str
    stacks: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {'reward_id': self.reward_id, 'stacks': self.stacks}


@dataclass(frozen=True)
class ShopProfile:
    schema_version: int = SHOP_PROFILE_SCHEMA_VERSION
    meta_coins: int = 0
    lifetime_meta_coins_earned: int = 0
    lifetime_runs_started: int = 0
    lifetime_runs_completed: int = 0
    lifetime_missions_completed: int = 0
    permanent_unit_unlocks: tuple[str, ...] = ()
    permanent_buffs: tuple[BuffPurchase, ...] = ()
    permanent_upgrades: Mapping[str, int] = field(default_factory=dict)
    salvaged_run_coins: int = 0
    archipelago_profiles: Mapping[str, Any] = field(default_factory=dict)

    def upgrade_level(self, upgrade_id: str) -> int:
        return int(self.permanent_upgrades.get(upgrade_id, 0))

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'meta_coins': self.meta_coins,
            'lifetime_meta_coins_earned': self.lifetime_meta_coins_earned,
            'lifetime_runs_started': self.lifetime_runs_started,
            'lifetime_runs_completed': self.lifetime_runs_completed,
            'lifetime_missions_completed': self.lifetime_missions_completed,
            'permanent_unit_unlocks': list(self.permanent_unit_unlocks),
            'permanent_buffs': [item.to_dict() for item in self.permanent_buffs],
            'permanent_upgrades': dict(self.permanent_upgrades),
            'salvaged_run_coins': self.salvaged_run_coins,
            'archipelago_profiles': deepcopy(dict(self.archipelago_profiles)),
        }


@dataclass(frozen=True)
class ShopRun:
    run_id: str
    seed: str
    status: RunStatus
    stage: int
    run_length: int
    run_coins: int
    # Endless runs ignore run_length and end only when lives run out.
    # Persisted at creation rather than inferred from ap_identity, which can
    # be cleared while a run is still in progress. Defaults to the bounded
    # behaviour so a run restored from an older document stays bounded.
    endless: bool = False
    permanent_enemy_buff_ids: tuple[str, ...] = ()
    schema_version: int = SHOP_RUN_SCHEMA_VERSION
    campaign_filter: str = 'All Campaigns'
    reward_mode: str = 'Standard'
    reward_settings: Mapping[str, Any] = field(default_factory=dict)
    eligible_mission_codes: tuple[str, ...] = ()
    rerolls_used: int = 0
    difficulty_assists_used: int = 0
    assisted_mission_code: str | None = None
    starting_unit_ids: tuple[str, ...] = ()
    starting_defense_ids: tuple[str, ...] = ()
    selected_permanent_units: tuple[str, ...] = ()
    permanent_buffs_snapshot: tuple[BuffPurchase, ...] = ()
    ap_identity: str | None = None
    ap_entitlements_snapshot: tuple[str, ...] = ()
    run_purchases: tuple[PurchaseRecord, ...] = ()
    run_buffs: tuple[BuffPurchase, ...] = ()
    starting_draft_buffs: tuple[BuffPurchase, ...] = ()
    # What has already been taken off the shelf standing in front of the
    # player. An upgrade stacks, so nothing else stopped a player from
    # emptying their Ore into the same offer four times over -- which is the
    # concentration the drawn-upgrade design exists to prevent. Cleared when
    # the stage advances and the stock rotates, and only then: a defeat
    # replays the same stage against the same shelf.
    stage_shelf_purchases: tuple[str, ...] = ()
    free_buff_tokens_used: int = 0
    emergency_revivals_used: int = 0
    mission_offers: tuple[MissionOffer, ...] = ()
    selected_mission_code: str | None = None
    mission_committed: bool = False
    completed_missions: tuple[str, ...] = ()
    rewarded_victories: tuple[str, ...] = ()
    modifiers: tuple[str, ...] = ()
    coupon_used_stage: int | None = None
    stock_lock_reward_id: str | None = None
    stock_lock_stage: int | None = None
    failed_mission_code: str | None = None
    failed_stage: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'run_id': self.run_id,
            'seed': self.seed,
            'status': self.status.value,
            'stage': self.stage,
            'run_length': self.run_length,
            'run_coins': self.run_coins,
            'endless': self.endless,
            'permanent_enemy_buff_ids': list(
                self.permanent_enemy_buff_ids
            ),
            'campaign_filter': self.campaign_filter,
            'reward_mode': self.reward_mode,
            'reward_settings': deepcopy(dict(self.reward_settings)),
            'eligible_mission_codes': list(self.eligible_mission_codes),
            'rerolls_used': self.rerolls_used,
            'difficulty_assists_used': self.difficulty_assists_used,
            'assisted_mission_code': self.assisted_mission_code,
            'starting_unit_ids': list(self.starting_unit_ids),
            'starting_defense_ids': list(self.starting_defense_ids),
            'selected_permanent_units': list(self.selected_permanent_units),
            'permanent_buffs_snapshot': [
                item.to_dict() for item in self.permanent_buffs_snapshot
            ],
            'ap_identity': self.ap_identity,
            'ap_entitlements_snapshot': list(self.ap_entitlements_snapshot),
            'run_purchases': [item.to_dict() for item in self.run_purchases],
            'run_buffs': [item.to_dict() for item in self.run_buffs],
            'starting_draft_buffs': [
                item.to_dict() for item in self.starting_draft_buffs
            ],
            'stage_shelf_purchases': list(self.stage_shelf_purchases),
            'free_buff_tokens_used': self.free_buff_tokens_used,
            'emergency_revivals_used': self.emergency_revivals_used,
            'mission_offers': [item.to_dict() for item in self.mission_offers],
            'selected_mission_code': self.selected_mission_code,
            'mission_committed': self.mission_committed,
            'completed_missions': list(self.completed_missions),
            'rewarded_victories': list(self.rewarded_victories),
            'modifiers': list(self.modifiers),
            'coupon_used_stage': self.coupon_used_stage,
            'stock_lock_reward_id': self.stock_lock_reward_id,
            'stock_lock_stage': self.stock_lock_stage,
            'failed_mission_code': self.failed_mission_code,
            'failed_stage': self.failed_stage,
        }


@dataclass(frozen=True)
class ShopCatalogueEntry:
    reward_id: str
    reward_type: ShopRewardType
    target_id: str
    tier: str | None
    stack_limit: int | None
    factions: tuple[str, ...]
    # Which kind of upgrade this is, for buff entries only. The rotating
    # upgrade shelf draws by type, so it has to be readable off the entry
    # rather than fetched back out of the reward catalogue per candidate.
    buff_type: str | None = None


@dataclass(frozen=True)
class PurchaseValidation:
    result: PurchaseResult
    reward_id: str = ''
    cost: int = 0

    @property
    def allowed(self) -> bool:
        return self.result is PurchaseResult.OK


@dataclass(frozen=True)
class LoadoutValidation:
    result: PurchaseResult
    selected_reward_ids: tuple[str, ...]
    active_tech_ids: tuple[str, ...]
    extra_slots_used: int

    @property
    def allowed(self) -> bool:
        return self.result is PurchaseResult.OK
