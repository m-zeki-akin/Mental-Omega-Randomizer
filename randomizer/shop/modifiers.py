"""Pure aggregation of configured Shop Mode modifier effects."""

from fractions import Fraction
from hashlib import sha256

from fractions import Fraction

from .config import SHOP_CONFIG
from .model import ShopModeConfig


def modifier_effects(modifier_ids, config: ShopModeConfig = SHOP_CONFIG):
    """Combine selected modifier fields in stable input order.

    Percent effects multiply. Flat effects add. Unknown IDs fail instead of
    silently changing a saved run's balance.
    """
    effects = {
        'starting_run_coins_flat': 0,
        'run_reward_percent': Fraction(1, 1),
        'run_reward_flat': 0,
        'meta_reward_percent': Fraction(1, 1),
        'meta_reward_flat': 0,
        'shop_price_percent': Fraction(1, 1),
        'shop_price_flat': 0,
        'hidden_offer_count': 0,
        'player_damage_percent': Fraction(1, 1),
        'player_armor_percent': Fraction(1, 1),
        'production_time_percent': Fraction(1, 1),
        'combat_production_time_percent': Fraction(1, 1),
        'player_cost_percent': Fraction(1, 1),
        'support_recharge_percent': Fraction(1, 1),
        'unit_inventory_flat': 0,
        'power_inventory_flat': 0,
        'starter_veteran': 0,
        'starter_unit_count_flat': 0,
        'disable_rerolls': 0,
        'disable_assists': 0,
        'disable_revivals': 0,
        'mission_starting_credits_flat': 0,
        'mission_offer_count_flat': 0,
        'liquidate_ore_after_victory': 0,
        'challenge_meta_reward_percent': Fraction(1, 1),
        'normal_run_reward_percent': Fraction(1, 1),
    }
    seen = set()
    for modifier_id in modifier_ids or ():
        modifier_id = str(modifier_id)
        if modifier_id in seen:
            continue
        seen.add(modifier_id)
        definition = config.modifiers.get(modifier_id)
        if definition is None:
            raise ValueError(f'Unknown Shop Mode modifier: {modifier_id!r}')
        for key, value in definition.effects.items():
            if key.endswith('_percent'):
                effects[key] *= Fraction(int(value), 100)
            else:
                effects[key] += int(value)
    return effects


def modifier_difficulty(modifier_ids):
    """Return one visible difficulty point per distinct modifier."""
    return len(tuple(dict.fromkeys(str(item) for item in modifier_ids or ())))


# How far each pacing choice moves the run's difficulty score, per step away
# from the configured baseline. Signs are chosen so a harder run scores higher:
# fewer lives, slower income, more permanent enemy buffs, and shorter stages
# (which means more challenges) all raise it.
# Difficulty points per step away from the configured baseline, signed so a
# harder run scores higher. Head starts are worth noticeably less than the
# rules that shape the whole run: opening resources are spent once, while
# lives, escalation, and stage length are felt for its entire length.
PACING_DIFFICULTY_WEIGHTS = {
    'starting_lives': Fraction(-2),
    'stage_income_percent_per_stage': Fraction(-1),
    'permanent_enemy_buffs_per_challenge': Fraction(3),
    'stage_length': Fraction(-2),
    'starting_run_coins': Fraction(-3, 10),
    'starting_meta_coins': Fraction(-1, 2),
    'starting_rerolls': Fraction(-7, 10),
}
# Currencies move in larger units than the counts, so score them per five.
PACING_DIFFICULTY_STEPS = {
    'stage_income_percent_per_stage': 10,
    'starting_run_coins': 5,
    'starting_meta_coins': 5,
}
GEM_SCALE_PER_DIFFICULTY_PERCENT = 10
MINIMUM_GEM_SCALE_PERCENT = 0
MAXIMUM_GEM_SCALE_PERCENT = 200
# Easing past this stops paying Gems at all, so there is nothing further to
# give up. Clamping the score here keeps the readout honest instead of showing
# a number that no longer changes anything.
MINIMUM_PACING_DIFFICULTY = Fraction(
    MINIMUM_GEM_SCALE_PERCENT - 100, GEM_SCALE_PER_DIFFICULTY_PERCENT
)


def pacing_difficulty(reward_settings, config: ShopModeConfig = SHOP_CONFIG):
    """Return the difficulty points a run's pacing choices are worth.

    Zero means the configured baseline. Positive means the player made the run
    harder than default and negative means easier. Easing is floored where
    Gems stop paying entirely; past that there is nothing left to trade away.
    """
    from .config import run_pacing_overrides

    score = Fraction(0)
    overrides = run_pacing_overrides(reward_settings, config)
    for field, value in overrides.items():
        weight = PACING_DIFFICULTY_WEIGHTS.get(field, Fraction(0))
        step = PACING_DIFFICULTY_STEPS.get(field, 1)
        score += weight * Fraction(value - getattr(config, field), step)
    return max(MINIMUM_PACING_DIFFICULTY, score)


def format_difficulty(score):
    """Render a difficulty score with a sign and no trailing noise."""
    return f'{float(score):+.4g}'


def run_difficulty(modifier_ids, reward_settings=None, config=SHOP_CONFIG):
    """Return the run's difficulty, which is its pacing alone.

    Optional run modifiers deliberately do not count. Each one pairs an
    advantage with a drawback and is meant to read as a trade rather than a
    difficulty step, so folding them in here would overstate how hard a run
    with several balanced modifiers actually is. modifier_difficulty() remains
    for the per-modifier count shown beside the modifier list itself.
    """
    del modifier_ids
    return pacing_difficulty(reward_settings, config)


def pacing_gem_scale_percent(reward_settings, config: ShopModeConfig = SHOP_CONFIG):
    """Return the Gem payout scale a run's pacing choices earn.

    Making a run harder pays more and making it easier pays less, so a player
    cannot farm permanent upgrades by turning the difficulty down. Clamped so
    neither direction can trivialise or erase progression.
    """
    percent = 100 + GEM_SCALE_PER_DIFFICULTY_PERCENT * pacing_difficulty(
        reward_settings, config
    )
    return int(max(
        MINIMUM_GEM_SCALE_PERCENT, min(MAXIMUM_GEM_SCALE_PERCENT, percent)
    ))


def modifier_mission_offer_count(
    modifier_ids, config: ShopModeConfig = SHOP_CONFIG
):
    effects = modifier_effects(modifier_ids, config)
    return max(
        1,
        min(
            config.mission_offer_count,
            config.mission_offer_count + effects['mission_offer_count_flat'],
        ),
    )


def hidden_offer_codes(run, config: ShopModeConfig = SHOP_CONFIG):
    """Choose reward-hidden offers without consuming gameplay RNG."""
    count = max(0, int(modifier_effects(
        run.modifiers, config
    )['hidden_offer_count']))
    offers = tuple(run.mission_offers)
    if not count or not offers:
        return ()
    ranked = sorted(
        offers,
        key=lambda offer: sha256(
            f'{run.seed}:{run.stage}:{run.rerolls_used}:'
            f'{offer.mission_code}:blind-choice'.encode('utf-8')
        ).digest(),
    )
    return tuple(offer.mission_code for offer in ranked[:count])
