"""What a Shop Mode mission is launched with.

A Shop run's rewards are not the campaign's. What the player carries is
what they bought -- off the shelf this run, and permanently across every
run before it -- plus what the run's modifiers and the mission's own
challenge add on top. Working that out was four methods on the window's
Shop controller, which meant a mission could only be launched from a
window: the answers were computed from widgets' neighbours rather than
from the run.

They are computed from the run here, and the controller calls these. The
window keeps deciding when to launch and this decides what with, which is
the split that lets a page launch one too.
"""

from collections import Counter

from randomizer.rewards.catalogue import BUFF_TARGETS

from .active import (
    active_shop_rewards,
    active_shop_starter_unit_ids,
    active_shop_tech_ids,
)
from .catalogue import canonical_reward_for_id, shop_catalogue_by_reward_id
from .mission_modifiers import active_mission_modifier
from .modifiers import modifier_effects


# What the run's own pacing settings are called once they reach the
# reward pipeline, which reads them under a shop_ prefix.
MODIFIER_SETTINGS = (
    'player_damage_percent',
    'player_armor_percent',
    'production_time_percent',
    'combat_production_time_percent',
    'player_cost_percent',
    'mission_starting_credits_flat',
)


def modifier_clone_seed_plan(run):
    """Return how many stacks of armour and firepower each unit already has.

    A run modifier that raises everything the player fields is written as
    a buff on each unit, and a unit that has already been bought that buff
    has to keep its own stacks: seeding from zero would hand back an
    upgrade the run paid for.
    """
    existing = Counter(
        (
            str(reward.get('unit') or '').upper(),
            str(reward.get('buff_type') or ''),
        )
        for reward in active_shop_rewards(run)
        if reward.get('kind') == 'buff'
    )
    armor = {}
    damage = {}
    for target_id in active_shop_tech_ids(run):
        target = BUFF_TARGETS.get(target_id, {})
        label = target.get('label', target_id)
        armor_reward = canonical_reward_for_id(f'{label} Armor Plating I')
        if armor_reward.get('buff_type') == 'armor':
            armor[target_id] = existing[(target_id, 'armor')]
        if not target.get('weapons'):
            continue
        damage_reward = canonical_reward_for_id(f'{label} Firepower I')
        if damage_reward.get('buff_type') == 'damage':
            damage[target_id] = existing[(target_id, 'damage')]
    return armor, damage


def reward_settings(run):
    """Return the settings a Shop mission's rewards are written under."""
    settings = dict(run.reward_settings)
    settings['start_with_tier_one_units'] = True
    settings['start_with_tier_one_defenses'] = True
    settings['failure_assistance'] = False
    effects = modifier_effects(run.modifiers)
    for key in MODIFIER_SETTINGS:
        value = effects[key]
        settings[f'shop_{key}'] = (
            float(value) if key.endswith('_percent') else int(value)
        )
    armor_seeds, damage_seeds = modifier_clone_seed_plan(run)
    settings['shop_modifier_armor_seed_stacks'] = armor_seeds
    settings['shop_modifier_damage_seed_stacks'] = damage_seeds
    modifier = active_mission_modifier(run)
    if modifier is not None and modifier.buffs_allied_helpers:
        settings['buff_allied_helpers'] = True
    return settings


def _veteran_targets(run, profile, effects, entries):
    """Return the units that take the field already promoted."""
    targets = set()
    if profile is not None and profile.upgrade_level('veteran_academy'):
        for reward_id in run.selected_permanent_units:
            entry = entries.get(reward_id)
            if entry is not None and entry.target_id:
                targets.add(entry.target_id.upper())
    if effects['starter_veteran']:
        targets.update(active_shop_starter_unit_ids(run))
    return targets


def _seeded(target_id, name):
    """Return one modifier's buff, written straight onto the unit."""
    reward = dict(canonical_reward_for_id(name))
    # Written on the unit rather than through a copy: a modifier raises
    # what the player already fields, and a copy would be a second unit.
    reward['force_direct_unit_buff'] = True
    reward['_shop_modifier_clone_seed'] = True
    return reward


def launch_rewards(run, profile=None, entries=None):
    """Return every reward one Shop mission is played with.

    What the run bought, then what the profile's permanent upgrades add,
    then the mission's own challenge, then the run modifiers -- veterancy,
    the armour and firepower they raise, and the recharge they hurry.
    """
    entries = (
        shop_catalogue_by_reward_id() if entries is None else entries
    )
    effects = modifier_effects(run.modifiers)
    rewards = [dict(item) for item in active_shop_rewards(run)]
    if profile is not None:
        for _index in range(profile.upgrade_level('mission_starting_credits')):
            rewards.append(canonical_reward_for_id('Starting Credits +1,000'))
    modifier = active_mission_modifier(run)
    if modifier is not None:
        for reward_id in modifier.player_reward_ids:
            reward = dict(canonical_reward_for_id(reward_id))
            if reward.get('kind') == 'superweapon':
                reward['superweapon_ignore_foreign_tech_gate'] = True
            rewards.append(reward)
    for target_id in sorted(_veteran_targets(run, profile, effects, entries)):
        target = BUFF_TARGETS.get(target_id, {})
        try:
            reward = dict(canonical_reward_for_id(
                f'{target.get("label", target_id)} Veteran Training I'
            ))
        except KeyError:
            continue
        if reward.get('buff_type') == 'veteran':
            rewards.append(reward)
    if effects['player_armor_percent'] != 1:
        armor_seeds, _damage = modifier_clone_seed_plan(run)
        for target_id in armor_seeds:
            target = BUFF_TARGETS.get(target_id, {})
            rewards.append(_seeded(
                target_id,
                f'{target.get("label", target_id)} Armor Plating I',
            ))
    if effects['player_damage_percent'] != 1:
        _armor, damage_seeds = modifier_clone_seed_plan(run)
        for target_id in damage_seeds:
            target = BUFF_TARGETS.get(target_id, {})
            rewards.append(_seeded(
                target_id, f'{target.get("label", target_id)} Firepower I',
            ))
    support = float(effects['support_recharge_percent'])
    if support != 1.0:
        for index, reward in enumerate(rewards):
            if (
                reward.get('kind') == 'superweapon'
                and reward.get('power_category') == 'aid'
            ):
                updated = dict(reward)
                updated['superweapon_recharge_multiplier'] = float(
                    updated.get('superweapon_recharge_multiplier', 1.0)
                ) * support
                rewards[index] = updated
    return rewards


def enemy_scaling_entries(run):
    """Return what the mission's own challenge gives the enemy."""
    modifier = active_mission_modifier(run)
    if modifier is None or not modifier.enemy_reward_id:
        return []
    return [{
        'reward': canonical_reward_for_id(modifier.enemy_reward_id),
        'source': 'Shop mission challenge',
        'earned_from': modifier.title,
    }]
