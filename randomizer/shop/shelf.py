"""The one description of what a run's shop is offering right now.

The shelf used to live in the screen that drew it, which was harmless while a
player could only buy what a row showed. Upgrades changed that: they are no
longer chosen from a list of everything a unit could ever take, they are drawn,
so the draw itself is the rule about what may be bought. A shelf computed in
the widget layer would leave the service accepting any upgrade for any owned
unit, and the manual path would survive the removal of its button.

So the shelf is computed here, from the saved profile and run alone, and both
the screen and the purchase service ask this module rather than each other.
"""

from .active import active_shop_power_ids, active_shop_tech_ids
from .catalogue import (
    buff_draw_weights,
    run_excluded_target_ids,
    shop_catalogue,
    shop_catalogue_by_reward_id,
    shop_entry_available,
)
from .config import SHOP_CONFIG
from .inventory import (
    guarantee_premium_offer,
    preserve_locked_offer,
    rotating_power_inventory,
    rotating_unit_inventory,
    rotating_upgrade_inventory,
    weighted_upgrade_draw,
)
from .model import RunStatus, ShopModeConfig, ShopRewardType
from .modifiers import modifier_effects

# Standalone Shop runs always price and filter as this mode; the reward mode
# picker belongs to seed generation, not to the shop.
SHOP_REWARD_MODE = 'Standard'


def run_buff_stacks(run):
    """Return how many stacks of each upgrade a run currently holds."""
    if run is None:
        return {}
    stacks = {}
    for group in (
        run.run_buffs, run.permanent_buffs_snapshot, run.starting_draft_buffs
    ):
        for item in group:
            stacks[item.reward_id] = stacks.get(item.reward_id, 0) + item.stacks
    return stacks


def run_faction_filter(run):
    if run is None:
        return 'All Campaigns'
    return str(
        run.reward_settings.get('shop_faction_filter') or run.campaign_filter
    )


def entry_available_for_run(run, entry):
    return shop_entry_available(
        entry,
        campaign_filter=run_faction_filter(run),
        reward_mode=SHOP_REWARD_MODE,
        strict_faction=True,
        excluded_target_ids=run_excluded_target_ids(run.reward_settings),
    )


def upgradeable_entries(run, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return every upgrade a run could still be given.

    Restricted to targets the player already owns, which is the whole point of
    the redesign: an upgrade is a reward for the roster in play, never a
    voucher for something not yet bought. Upgrades already at their stack
    limit are dropped so a draw cannot spend a slot on nothing.
    """
    if run is None:
        return ()
    owned_tech = set(active_shop_tech_ids(run))
    owned_powers = set(active_shop_power_ids(run))
    stacks = run_buff_stacks(run)
    candidates = []
    for entry in shop_catalogue():
        if entry.reward_type is ShopRewardType.UNIT_BUFF:
            if entry.target_id not in owned_tech:
                continue
        elif entry.reward_type is ShopRewardType.POWER_BUFF:
            if entry.target_id not in owned_powers:
                continue
        else:
            continue
        if (
            entry.stack_limit is not None
            and stacks.get(entry.reward_id, 0) >= entry.stack_limit
        ):
            continue
        if not entry_available_for_run(run, entry):
            continue
        candidates.append(entry)
    return tuple(candidates)


def _access_offer_counts(profile, run, config):
    definition = config.permanent_upgrades['extra_shop_stock']
    level = profile.upgrade_level('extra_shop_stock') if profile else 0
    effects = modifier_effects(run.modifiers, config) if run else None
    units = (
        config.unit_inventory_size
        + level * int(definition.effects['units_per_level'])
        + (effects['unit_inventory_flat'] if effects else 0)
    )
    powers = (
        config.power_inventory_size
        + level * int(definition.effects['powers_per_level'])
        + (effects['power_inventory_flat'] if effects else 0)
    )
    return max(0, units), max(0, powers)


def shop_shelf(profile, run, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return the (units, powers, upgrades) offered for the open stage.

    Empty for a run that is not open for business, which keeps "there is
    nothing on the shelf" and "you may not buy right now" as one answer
    instead of two that can disagree.
    """
    empty = ((), (), ())
    if run is None or run.status is not RunStatus.ACTIVE:
        return empty
    owned_tech = set(active_shop_tech_ids(run))
    owned_powers = set(active_shop_power_ids(run))
    unit_count, power_count = _access_offer_counts(profile, run, config)
    unit_candidates = []
    power_candidates = []
    for entry in shop_catalogue():
        if entry.reward_type is ShopRewardType.UNIT_ACCESS:
            bucket = unit_candidates
        elif entry.reward_type is ShopRewardType.POWER_ACCESS:
            bucket = power_candidates
        else:
            continue
        if entry_available_for_run(run, entry):
            bucket.append(entry)
    units = rotating_unit_inventory(
        tuple(unit_candidates),
        run_seed=run.seed,
        stage=run.stage,
        offer_count=unit_count,
        excluded_target_ids=owned_tech,
    )
    powers = rotating_power_inventory(
        tuple(power_candidates),
        run_seed=run.seed,
        stage=run.stage,
        offer_count=power_count,
        excluded_target_ids=owned_powers,
    )
    units, powers = _apply_access_perks(
        profile,
        run,
        units,
        powers,
        access_candidates=(*unit_candidates, *power_candidates),
        owned_tech=owned_tech,
        owned_powers=owned_powers,
        config=config,
    )
    upgrades = rotating_upgrade_inventory(
        upgradeable_entries(run, config=config),
        run_seed=run.seed,
        stage=run.stage,
        offer_count=config.upgrade_inventory_size,
        weights=buff_draw_weights(),
    )
    return units, powers, upgrades


def _apply_access_perks(
    profile,
    run,
    units,
    powers,
    *,
    access_candidates,
    owned_tech,
    owned_powers,
    config,
):
    """Fold Stock Lock and Premium Supplier into the access stock.

    Both perks replace an offer rather than add one, and both only ever act on
    units and powers -- an upgrade shelf drawn from what the player owns has
    nothing for either of them to hold or to upgrade the tier of.
    """
    if profile is None:
        return units, powers
    stock = (*units, *powers)
    locked_entry = shop_catalogue_by_reward_id().get(
        run.stock_lock_reward_id or ''
    )
    if (
        locked_entry is not None
        and run.stock_lock_stage is not None
        and run.stage <= run.stock_lock_stage + 1
        and entry_available_for_run(run, locked_entry)
        and locked_entry.target_id not in owned_tech
        and locked_entry.target_id not in owned_powers
    ):
        stock = preserve_locked_offer(stock, locked_entry)
    else:
        locked_entry = None
    if profile.upgrade_level('premium_supplier'):
        premium = config.permanent_upgrades['premium_supplier']
        eligible = tuple(
            entry for entry in access_candidates
            if entry.target_id not in owned_tech
            and entry.target_id not in owned_powers
        )
        stock = guarantee_premium_offer(
            stock,
            eligible,
            run_seed=run.seed,
            stage=run.stage,
            minimum_stage=int(premium.effects['minimum_stage']),
            protected_reward_ids=(
                (locked_entry.reward_id,) if locked_entry is not None else ()
            ),
        )
    return (
        tuple(
            entry for entry in stock
            if entry.reward_type is ShopRewardType.UNIT_ACCESS
        ),
        tuple(
            entry for entry in stock
            if entry.reward_type is ShopRewardType.POWER_ACCESS
        ),
    )


def shop_shelf_reward_ids(profile, run, *, config: ShopModeConfig = SHOP_CONFIG):
    """Return every reward id the open shelf will sell."""
    return frozenset(
        entry.reward_id
        for group in shop_shelf(profile, run, config=config)
        for entry in group
    )


def mission_upgrade_rewards(
    run, mission_code, *, config: ShopModeConfig = SHOP_CONFIG
):
    """Return the upgrades a mission victory hands out.

    Spread one per target, so a victory strengthens two parts of the roster
    rather than doubling down on one -- the habit the redesign exists to
    break. Keyed on the mission as well as the stage: the draw has to be the
    same every time a given victory is reported, and a run can legitimately
    replay a stage after a loss.
    """
    count = max(0, int(config.mission_upgrade_reward_count))
    if not count:
        return ()
    return weighted_upgrade_draw(
        upgradeable_entries(run, config=config),
        run_seed=f'{run.seed}\0{str(mission_code or "").upper()}',
        stage=run.stage,
        offer_count=count,
        stream_name='shop_mission_upgrade_reward',
        weights=buff_draw_weights(),
        one_per_target=True,
    )


# Lowest first: a gift climbs a tier only once the one below is exhausted.
_GIFT_TIER_ORDER = ('tier_1', 'tier_2', 'tier_3', None)


def mission_unit_gift(
    run, mission_code, *, config: ShopModeConfig = SHOP_CONFIG
):
    """Return the units a mission victory hands over.

    Always from the lowest tier that still has something the player does not
    own. Keeping a deliberately narrow roster used to be the strong play --
    fewer units meant every upgrade landed on the same one -- so the gift
    refuses to skip ahead: a Tier 2 unit only arrives once Tier 1 has nothing
    left to give, and what counts as "nothing left" respects the run's own
    faction filter and reward-pool exclusions.
    """
    count = max(0, int(config.mission_unit_gift_count))
    if not count or run is None:
        return ()
    owned = set(active_shop_tech_ids(run))
    by_tier = {}
    for entry in shop_catalogue():
        if entry.reward_type is not ShopRewardType.UNIT_ACCESS:
            continue
        if entry.target_id in owned:
            continue
        if not entry_available_for_run(run, entry):
            continue
        by_tier.setdefault(entry.tier, []).append(entry)
    candidates = next(
        (by_tier[tier] for tier in _GIFT_TIER_ORDER if by_tier.get(tier)),
        (),
    )
    if not candidates:
        return ()
    return weighted_upgrade_draw(
        tuple(candidates),
        run_seed=f'{run.seed}\0{str(mission_code or "").upper()}',
        stage=run.stage,
        offer_count=count,
        stream_name='shop_mission_unit_gift',
        one_per_target=True,
    )
