"""Turning what the player asked for into one exact generation request.

This was a method on the classic window's seed controller, and every
value in it came out of a Tk variable -- so the only way to generate a
run was to have a window open with those variables in it. The rules were
never about a window: they are about what a run may be, and they refuse
for reasons a player needs to hear whichever interface asked.

So the reading of the controls is separated from the deciding. What a
player asked for is a plain dict -- from the live controls in one window,
from the settings file in the other -- and everything after that is one
body with two callers.

The refusals are exceptions rather than a logged line and a bare
``return``. A window catches one and writes it in its log; a page catches
one and sends it back as the reason the button did nothing. Both say the
same sentence, which is the point.
"""

import random

from randomizer.missions.catalogue import (
    filter_missions_by_build_settings,
    normalize_faction,
)
from randomizer.launch.game import clear_generated_rules
from randomizer.rewards.arsenal import ARSENAL_MODE
from randomizer.rewards.definitions import (
    DEFAULT_REWARDS_PER_CHECK,
    MAX_REWARDS_PER_CHECK,
)
from randomizer.ui.config import CAMPAIGN_FILTERS


class GenerationRefused(Exception):
    """A run that cannot be generated, and the reason a player gets."""


# What a run is asked for with, whatever is doing the asking. Everything
# else -- the reward settings, the missions, the arsenal -- is looked up
# from these or handed in beside them.
CONTROL_KEYS = (
    'campaign_filter',
    'seed',
    'mission_goal',
    'rewards_per_check',
    'progression_mode',
    'reward_mode',
    'rewards_on_victory_only',
    'use_act_based_reward_multipliers',
    'unlock_all_grid_rewards',
    'two_start_positions',
    'include_no_build_missions',
    'include_no_build_production_missions',
    'include_operation_missions',
    'prioritize_no_build_missions',
)
# The three the generated run is stamped with, so that what it was made
# from can be read back off it.
CONTEXT_KEYS = (
    'campaign_filter', 'reward_mode', 'use_act_based_reward_multipliers',
)
SHOP_MODE = 'Shop Mode'
# The filter that lets every campaign through, which is the first one the
# launcher offers rather than a word this module gets to decide.
ALL_CAMPAIGNS = CAMPAIGN_FILTERS[0]


def missions_for(missions, controls, excluded):
    """Return the missions a run may be dealt from, filtered as asked."""
    wanted = str(controls.get('campaign_filter') or '')
    listed = list(missions) if wanted == ALL_CAMPAIGNS else [
        mission for mission in missions
        if normalize_faction(mission.get('side', '')) == wanted
    ]
    barred = {str(code).upper() for code in (excluded or ())}
    listed = [
        mission for mission in listed
        if str(mission.get('code', '')).upper() not in barred
    ]
    return filter_missions_by_build_settings(
        listed,
        include_true_no_build=bool(controls.get('include_no_build_missions')),
        include_no_build_production=bool(
            controls.get('include_no_build_production_missions')
        ),
        include_operation_missions=bool(
            controls.get('include_operation_missions')
        ),
    )


def _goal(controls, available):
    """Return how many missions a run is, never more than it can deal."""
    try:
        wanted = int(controls.get('mission_goal'))
    except (TypeError, ValueError):
        wanted = available
    return max(1, min(wanted, available))


def _refuse(reason):
    raise GenerationRefused(f'Cannot generate seed: {reason}')


def options_from(source, controls, *, missions, reward_settings,
                 progress=None):
    """Return one frozen generation request, or refuse with a reason.

    ``source`` is whatever knows the rest of the run -- which mission
    codes are left out, which starting units a seed opens with, which
    names the installed rules still know. Both windows have one; it is
    handed in rather than reached for so that this body belongs to
    neither of them.

    It is also written back to. The starting rewards are worked out by
    code that reads what the run is being generated as, so the context
    and the settings have to be standing before they are asked for --
    which is the one ordering in here that is not obvious and cannot be
    moved.
    """
    if not missions:
        _refuse('no missions loaded.')
    seed_missions = missions_for(
        missions, controls, getattr(source, 'excluded_mission_codes', ())
    )
    if not seed_missions:
        _refuse(f'no missions match {controls.get("campaign_filter")}.')

    requested_seed = str(controls.get('seed') or '').strip()
    seed = requested_seed or f'MO-{random.randrange(0x10000000):08X}'
    mode = str(controls.get('progression_mode') or '')
    mission_goal = (
        len(seed_missions) if mode == SHOP_MODE
        else _goal(controls, len(seed_missions))
    )
    try:
        rewards_per_check = int(controls.get('rewards_per_check'))
    except (TypeError, ValueError):
        rewards_per_check = DEFAULT_REWARDS_PER_CHECK
    rewards_per_check = max(1, min(rewards_per_check, MAX_REWARDS_PER_CHECK))

    # A run is generated with the names this install can actually find.
    # What the player typed is kept in the settings file whether the name
    # is known here or not -- a submod may be off today and on tomorrow
    # -- but the run's own record of itself should say what it really got.
    reward_settings = dict(reward_settings)
    reward_settings['starting_unlock_rewards'] = (
        source.filter_permanent_starting_unlock_names(
            reward_settings.get('starting_unlock_rewards')
        )
    )
    arsenal_mode = str(controls.get('reward_mode') or '') == ARSENAL_MODE
    if arsenal_mode:
        reward_settings = dict(reward_settings)
        reward_settings.update({
            'randomize_unit_access': True,
            'start_with_tier_one_units': False,
            'start_with_tier_one_defenses': False,
            'starting_reward_count': 0,
            'starting_unlock_rewards': [],
        })
        arsenal_settings = reward_settings['arsenal']
        if not arsenal_settings['factions']:
            _refuse('Randomizer Arsenal needs at least one faction.')
        if not any(
            count
            for tier in arsenal_settings['roster_sizes'].values()
            for count in tier.values()
        ) and not any(arsenal_settings['power_counts'].values()):
            _refuse('Randomizer Arsenal roster sizes are all zero.')
        if not (
            reward_settings['include_buff_rewards']
            or reward_settings['include_power_buff_rewards']
        ):
            _refuse(
                'Randomizer Arsenal rewards must enable unit or power buffs.'
            )

    power_sources_enabled = any((
        reward_settings['include_superweapon_rewards'],
        reward_settings['include_secondary_superweapon_rewards'],
        reward_settings['include_aid_power_rewards'],
    ))
    if not any((
        reward_settings['randomize_unit_access'],
        reward_settings['include_buff_rewards'],
        reward_settings['include_superweapon_rewards'],
        reward_settings['include_secondary_superweapon_rewards'],
        reward_settings['include_aid_power_rewards'],
        (
            reward_settings['include_power_buff_rewards']
            and power_sources_enabled
        ),
    )):
        _refuse('enable at least one reward-pool option.')
    if (
        reward_settings['include_buff_rewards']
        and not reward_settings['enabled_buff_types']
    ):
        _refuse('buff rewards are enabled but no buff types are selected.')
    if (
        reward_settings['include_power_buff_rewards']
        and power_sources_enabled
        and not reward_settings['enabled_power_buff_types']
    ):
        _refuse(
            'power buffs are enabled but no power buff types are selected.'
        )
    if not any(reward_settings['reward_weights']['main'].values()):
        _refuse('enable at least one main reward weight.')
    if (
        reward_settings['starting_reward_count'] > 0
        and not reward_settings['starting_reward_types']
    ):
        _refuse('Starting Rewards has no allowed reward types.')

    generation_context = {
        key: controls.get(key) for key in CONTEXT_KEYS
    }
    generation_context['use_act_based_reward_multipliers'] = bool(
        controls.get('use_act_based_reward_multipliers')
    )
    source._seed_generation_context = generation_context
    source._reward_settings_override = reward_settings
    starting_unit_ids = source.starting_tier_one_unit_ids_for_seed(
        seed, reward_settings
    )
    starting_defense_ids = source.starting_tier_one_defense_ids_for_seed(
        reward_settings, seed=seed,
    )
    source._starting_unit_ids_override = starting_unit_ids
    source._starting_defense_ids_override = starting_defense_ids
    return {
        **generation_context,
        'seed': seed,
        'seed_was_explicit': bool(requested_seed),
        'seed_missions': list(seed_missions),
        'mission_goal': mission_goal,
        'rewards_per_check': rewards_per_check,
        'rewards_on_victory_only': bool(
            controls.get('rewards_on_victory_only')
        ),
        'use_act_based_reward_multipliers': bool(
            controls.get('use_act_based_reward_multipliers')
        ),
        'unlock_all_grid_rewards': bool(
            controls.get('unlock_all_grid_rewards')
        ),
        'reward_settings': reward_settings,
        'starting_defense_ids': starting_defense_ids,
        'starting_unit_ids': starting_unit_ids,
        'progression_mode': mode,
        'two_start_positions': bool(controls.get('two_start_positions')),
        'mission_pool_settings': {
            key: bool(controls.get(key)) for key in (
                'include_no_build_missions',
                'include_no_build_production_missions',
                'include_operation_missions',
                'prioritize_no_build_missions',
            )
        },
        '_progress': progress,
    }


# Where each control is kept in the settings file. Most sit at the top,
# beside the other things a run is set up with; the four about which
# missions may be dealt are in the generation block with the rest of what
# the reward pool is made of, and `rewards_per_objective` is what the
# file has always called the count this asks for as `rewards_per_check`.
_TOP = {
    'campaign_filter': 'campaign_filter',
    'seed': 'seed',
    'mission_goal': 'mission_goal',
    'rewards_per_check': 'rewards_per_objective',
    'progression_mode': 'progression_mode',
    'rewards_on_victory_only': 'rewards_on_victory_only',
    'use_act_based_reward_multipliers': 'use_act_based_reward_multipliers',
    'unlock_all_grid_rewards': 'unlock_all_rewards_after_final_grid_mission',
    'two_start_positions': 'grid_two_start_positions',
}
_GENERATED = {
    'reward_mode': 'reward_mode',
    'include_no_build_missions': 'include_no_build_missions',
    'include_no_build_production_missions':
        'include_no_build_production_missions',
    'include_operation_missions': 'include_operation_missions',
    'prioritize_no_build_missions': 'prioritize_no_build_missions',
}


def controls_from_config(config):
    """Return what the settings file asks for, in the same words.

    The other half of the pair: one window reads its widgets, the other
    reads the file both windows write. What comes out is the same dict,
    which is what makes the deciding shared.
    """
    generated = (config or {}).get('generation')
    generated = generated if isinstance(generated, dict) else {}
    controls = {
        key: (config or {}).get(where) for key, where in _TOP.items()
    }
    controls.update({
        key: generated.get(where) for key, where in _GENERATED.items()
    })
    return controls


def settle(state, config):
    """Keep a generated run, and put back what a new run makes stale.

    The classic window does this and a great deal besides -- its own
    labels, its log, its tree of missions. What is here is only the part
    that outlives a window: the run itself, the ruleset the game would
    otherwise still load, and the Archipelago connection, which belonged
    to the run this one replaces.
    """
    from . import store

    store.keep(state)
    config.setdefault('archipelago', {})['enabled'] = False
    clear_generated_rules()
    return state
