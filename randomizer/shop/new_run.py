"""What a new Shop run is started with.

Deciding it was the first half of a method on the window's Shop
controller: which units the seed opens with, which of the permanently
bought ones the player is taking, which of the profile's buffs follow
them, and which missions are on offer. None of it needed a window -- it
is the profile, the settings and the seed -- but it read them through Tk
variables, so a run could only be started from one.

It is arguments here, and the controller passes them in. The two lists
of starting markers come from the caller because working *those* out is
the campaign generator's job, and both windows have one; everything else
is decided from the run's own inputs.
"""

from .active import shop_starter_defense_ids, shop_starter_unit_ids
from .archipelago import ap_unit_entitlement_ids
from .catalogue import shop_catalogue_by_reward_id
from .config import SHOP_CONFIG
from .missions import generate_mission_offers
from .modifiers import modifier_effects, modifier_mission_offer_count
from .transitions import ShopTransitionError


# What the second starter-unit reduction leaves standing. The modifier
# that takes two units away removes an infantry and a vehicle and keeps
# the aircraft and the naval role, which are what a run cannot replace.
TRIMMED_STARTERS = (0, 2)


def maximum_loadout(profile, config=SHOP_CONFIG):
    """Return how many permanently bought units a run may take with it."""
    definition = config.permanent_upgrades['expanded_loadout']
    return (
        config.max_selected_permanent_units
        + profile.upgrade_level('expanded_loadout')
        * int(definition['slots_per_level'] if isinstance(definition, dict)
              else definition.effects['slots_per_level'])
    )


def starting_army(seed, settings, faction_filter, *, unit_markers,
                  defense_markers, effects):
    """Return the units and defences a run opens with."""
    excluded = settings.get('excluded_unit_access_ids', ())
    units = shop_starter_unit_ids(
        seed=seed,
        starting_unit_ids=unit_markers,
        faction_filter=faction_filter,
        excluded_unit_ids=excluded,
    )
    if effects['starter_unit_count_flat'] == -2 and len(units) >= 5:
        units = (*(units[index] for index in TRIMMED_STARTERS), *units[4:])
    defenses = shop_starter_defense_ids(
        seed=seed,
        starting_defense_ids=defense_markers,
        faction_filter=faction_filter,
        excluded_unit_ids=excluded,
    )
    return units, defenses


def _permanent_buffs(profile, entries, targets):
    """Return the profile's buffs that follow the units taking the field."""
    return tuple(
        item for item in profile.permanent_buffs
        if (entry := entries.get(item.reward_id)) is not None
        and entry.target_id in targets
    )


def plan_new_run(
    *,
    run_id,
    seed,
    profile,
    settings,
    mission_pool,
    faction_filter,
    starting_unit_markers,
    starting_defense_markers,
    selected_loadout=(),
    modifiers=(),
    ap_identity=None,
    ap_reward_ids=(),
    reward_mode,
    config=SHOP_CONFIG,
):
    """Return the arguments a new Shop run is started with.

    Refuses the same two ways the window did: too few missions to make a
    run of, and too few Act 1 missions to fill the opening offer. Both
    are refusals about the player's filters rather than about the run, so
    they are raised where the filters are read.
    """
    if len(mission_pool) < config.run_length:
        raise ShopTransitionError(
            f'Shop Mode needs at least {config.run_length} eligible '
            'missions under current filters'
        )
    wanted = modifier_mission_offer_count(modifiers)
    offers = generate_mission_offers(
        mission_pool, run_seed=seed, stage=1, offer_count=wanted,
    )
    if len(offers) != wanted:
        raise ShopTransitionError(
            f'Shop Mode needs at least {wanted} eligible Act 1 missions '
            'for its protected opening'
        )

    effects = modifier_effects(modifiers)
    units, defenses = starting_army(
        seed, settings, faction_filter,
        unit_markers=starting_unit_markers,
        defense_markers=starting_defense_markers,
        effects=effects,
    )
    entries = shop_catalogue_by_reward_id()
    # Only what the profile actually owns. A loadout is chosen before the
    # run and the list outlives the profile it was chosen against.
    entitled = set(profile.permanent_unit_unlocks)
    selected = tuple(
        reward_id for reward_id in selected_loadout if reward_id in entitled
    )
    # What the run opens with, and then everything a buff bought before
    # this run could follow onto the field.
    starter_tech_ids = set(units) | set(defenses)
    targets = set(starter_tech_ids)
    targets.update(
        entry.target_id
        for reward_id in (*selected, *ap_unit_entitlement_ids(ap_reward_ids))
        if (entry := entries.get(reward_id)) is not None and entry.target_id
    )
    return {
        'run_id': run_id,
        'seed': seed,
        'mission_offers': offers,
        'campaign_filter': 'All Campaigns',
        'reward_mode': reward_mode,
        'reward_settings': settings,
        'eligible_mission_codes': tuple(
            mission.get('code') for mission in mission_pool
        ),
        'starter_tech_ids': tuple(sorted(starter_tech_ids)),
        'starting_unit_ids': units,
        'starting_defense_ids': defenses,
        'selected_reward_ids': selected,
        'permanent_entitlement_ids': tuple(profile.permanent_unit_unlocks),
        'permanent_buffs': _permanent_buffs(profile, entries, targets),
        'maximum_extra_units': maximum_loadout(profile, config),
        'ap_entitlement_ids': tuple(ap_reward_ids),
        'ap_identity': ap_identity,
        'modifiers': tuple(modifiers),
    }
