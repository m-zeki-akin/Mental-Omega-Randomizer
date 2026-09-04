"""Deterministic rotating Shop inventory selection."""

from hashlib import sha256
import random

from .catalogue import DEFAULT_BUFF_DRAW_WEIGHT


_TIER_RANK = {None: 0, 'tier_1': 1, 'tier_2': 2, 'tier_3': 3}


def _rotating_inventory(
    entries,
    *,
    run_seed,
    stage,
    offer_count,
    stream_name,
    excluded_target_ids=(),
):
    """Return stable stock for one run stage.

    Baseline membership changes only when seed or stage changes. Active targets
    are removed and replaced without disturbing remaining baseline offers.
    Input order cannot affect the result.
    """
    ordered = tuple(sorted(entries, key=lambda entry: entry.reward_id.casefold()))
    count = max(0, min(int(offer_count), len(ordered)))
    if count == len(ordered):
        selected = ordered
    else:
        stream = f'{stream_name}\0{run_seed}\0{int(stage)}'.encode('utf-8')
        seed = int.from_bytes(sha256(stream).digest()[:16], 'big')
        selected = tuple(random.Random(seed).sample(ordered, count))
    excluded = {
        str(target_id).upper()
        for target_id in excluded_target_ids
        if str(target_id)
    }
    if not excluded:
        return selected
    visible = [
        entry for entry in selected
        if str(entry.target_id).upper() not in excluded
    ]
    selected_reward_ids = {entry.reward_id for entry in selected}
    replacements = sorted(
        (
            entry for entry in ordered
            if entry.reward_id not in selected_reward_ids
            and str(entry.target_id).upper() not in excluded
        ),
        key=lambda entry: (
            sha256(
                f'{stream_name}_refill\0{run_seed}\0{int(stage)}\0'
                f'{entry.reward_id}'.encode('utf-8')
            ).digest(),
            entry.reward_id.casefold(),
        ),
    )
    visible.extend(replacements[:count - len(visible)])
    return tuple(visible)


def rotating_unit_inventory(
    entries, *, run_seed, stage, offer_count, excluded_target_ids=()
):
    return _rotating_inventory(
        entries,
        run_seed=run_seed,
        stage=stage,
        offer_count=offer_count,
        stream_name='shop_unit_inventory',
        excluded_target_ids=excluded_target_ids,
    )


def rotating_power_inventory(
    entries, *, run_seed, stage, offer_count, excluded_target_ids=()
):
    """Return deterministic superweapon and aid-power stock for one stage."""
    return _rotating_inventory(
        entries,
        run_seed=run_seed,
        stage=stage,
        offer_count=offer_count,
        stream_name='shop_power_inventory',
        excluded_target_ids=excluded_target_ids,
    )


def weighted_upgrade_draw(
    entries,
    *,
    run_seed,
    stage,
    offer_count,
    stream_name,
    weights=None,
    one_per_target=False,
):
    """Return a deterministic weighted sample of upgrade offers.

    Upgrades are no longer picked off a target selector, so the draw itself is
    what decides which of a unit's dozen possible upgrades a player is ever
    offered. Weighting is what keeps the one-shot kinds -- veteran start,
    cloaking, sensors, vision -- from crowding out the stacking ones simply by
    being as numerous.

    ``one_per_target`` spreads a small draw across different units, which is
    what a mission reward wants: two upgrades on two units beats two stacks on
    one, since concentrating buffs on a single unit is the habit this is meant
    to break. A shop shelf leaves it off, so a unit with several good upgrades
    can still show more than one.
    """
    ordered = tuple(sorted(entries, key=lambda entry: entry.reward_id.casefold()))
    count = max(0, min(int(offer_count), len(ordered)))
    if not count:
        return ()
    weights = dict(weights or {})
    pool = list(ordered)
    pool_weights = [
        max(1, int(weights.get(entry.buff_type, DEFAULT_BUFF_DRAW_WEIGHT)))
        for entry in pool
    ]
    stream = f'{stream_name}\0{run_seed}\0{int(stage)}'.encode('utf-8')
    rng = random.Random(int.from_bytes(sha256(stream).digest()[:16], 'big'))
    drawn = []
    used_targets = set()
    while pool and len(drawn) < count:
        total = sum(pool_weights)
        threshold = rng.random() * total
        running = 0.0
        index = len(pool) - 1
        for position, weight in enumerate(pool_weights):
            running += weight
            if running > threshold:
                index = position
                break
        entry = pool.pop(index)
        pool_weights.pop(index)
        if one_per_target and entry.target_id in used_targets:
            continue
        used_targets.add(entry.target_id)
        drawn.append(entry)
    return tuple(drawn)


def rotating_upgrade_inventory(
    entries, *, run_seed, stage, offer_count, weights=None
):
    """Return deterministic upgrade stock for one stage of the run shop."""
    return weighted_upgrade_draw(
        entries,
        run_seed=run_seed,
        stage=stage,
        offer_count=offer_count,
        stream_name='shop_upgrade_inventory',
        weights=weights,
    )


def preserve_locked_offer(stock, locked_entry, *, protected_reward_ids=()):
    """Keep one selected access offer without increasing stock size."""
    stock = list(stock)
    if locked_entry is None or any(
        entry.reward_id == locked_entry.reward_id for entry in stock
    ):
        return tuple(stock)
    protected = set(protected_reward_ids)
    replacement = next(
        (
            index for index in range(len(stock) - 1, -1, -1)
            if stock[index].reward_type is locked_entry.reward_type
            and stock[index].reward_id not in protected
        ),
        next(
            (
                index for index in range(len(stock) - 1, -1, -1)
                if stock[index].reward_id not in protected
            ),
            None,
        ),
    )
    if replacement is not None:
        stock[replacement] = locked_entry
    return tuple(stock)


def guarantee_premium_offer(
    stock,
    eligible_entries,
    *,
    run_seed,
    stage,
    minimum_stage,
    protected_reward_ids=(),
):
    """Guarantee one deterministic Tier 2/3 access offer in later stages."""
    stock = list(stock)
    if int(stage) < int(minimum_stage) or not stock:
        return tuple(stock)
    minimum_rank = 3 if int(stage) >= 7 else 2
    if any(_TIER_RANK.get(entry.tier, 0) >= minimum_rank for entry in stock):
        return tuple(stock)
    selected_ids = {entry.reward_id for entry in stock}
    candidates = [
        entry for entry in eligible_entries
        if entry.reward_id not in selected_ids
        and _TIER_RANK.get(entry.tier, 0) >= minimum_rank
    ]
    if not candidates:
        return tuple(stock)
    candidates.sort(key=lambda entry: (
        sha256(
            f'premium_supplier\0{run_seed}\0{int(stage)}\0'
            f'{entry.reward_id}'.encode('utf-8')
        ).digest(),
        entry.reward_id.casefold(),
    ))
    protected = set(protected_reward_ids)
    replacement = next(
        (
            index for index in range(len(stock) - 1, -1, -1)
            if stock[index].reward_id not in protected
        ),
        None,
    )
    if replacement is not None:
        stock[replacement] = candidates[0]
    return tuple(stock)
