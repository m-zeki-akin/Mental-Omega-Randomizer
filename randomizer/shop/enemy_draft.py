"""Let the enemy's escalation answer the arsenal it is escalating against.

A stage-closing challenge hands the enemy permanent buffs. Those were drawn
uniformly, so what the enemy became had nothing to do with what the player had
built. That makes the run a puzzle rather than a game: every purchase has one
correct answer, and nothing on the other side of the table reacts.

The vocabulary to react with already existed -- the enemy catalogue mirrors
the player's own eleven buff types across three tiers -- so this only changes
which of them the draw reaches for. Buy Tier 3 armour and the enemy starts
buying the firepower to get through it. Buy cloak and it starts fielding
detectors, which are worth nothing to it until you do.

**The point is to remove the dominant strategy, not to punish.** Two things
keep it a game rather than a treadmill:

* The draw is a *mix*. ``enemy_adaptive_draft_percent`` of the weight answers
  the player and the rest stays uniform, so no branch is ever closed off and a
  reactive enemy never becomes a predictable one.
* It reads what the player *owns*, not what they field in the mission, which
  the launcher cannot see anyway. That is the more interesting rule: buying a
  branch and never using it is a real feint, and the counter it draws is the
  price of the bluff.

Determinism is unchanged. The weights come from run state and the choice from
the same seeded digest, so a replayed run still escalates identically.
"""

from hashlib import sha256

from randomizer.shop.config import SHOP_CONFIG

# What answers what. The left side is a buff type the player bought; the right
# side is the enemy stat that makes it matter less. These are deliberately
# asymmetric -- armour answers firepower by soaking it, firepower answers
# armour by out-scaling it -- so a player who commits to one pole is pushed
# toward the other rather than into a wall.
ARSENAL_COUNTERS = {
    'damage': ('health', 'armor'),
    'health': ('damage', 'reload'),
    'armor': ('damage', 'reload'),
    'reload': ('health', 'armor'),
    'range': ('speed', 'range'),
    'speed': ('speed', 'sight'),
    'sight': ('sight',),
    # The one hard counter in the catalogue: enemy Sensors reveal cloaked and
    # submerged units and are worth exactly nothing against a player who never
    # bought stealth. Under a uniform draw it was a dead card.
    'cloak': ('sensors',),
    'sensors': ('cloak',),
    'self_healing': ('damage',),
    'ammo': ('armor',),
    'cost': ('health',),
    'production': ('health',),
}

# Which category effect a player unit of each catalogue category argues for.
CATEGORY_EFFECTS = {
    'infantry': 'infantry',
    'units': 'vehicle',
    'aircraft': 'aircraft',
    'defenses': 'defense',
    'special_buildings': 'defense',
}

TIER_NAMES = ('tier_1', 'tier_2', 'tier_3')


def _reward_by_id(reward_id):
    from randomizer.rewards.catalogue import REWARD_BY_NAME, canonical_reward

    reward = REWARD_BY_NAME.get(str(reward_id))
    return canonical_reward(reward) if reward else None


def arsenal_profile(run):
    """Return what the player has committed to, as weights the draw can read.

    ``units`` counts owned access by arsenal tier and by category; ``buffs``
    counts bought stacks by buff type. Starting units and permanent unlocks
    count the same as anything bought this run: the enemy is answering the
    army that will show up, not the receipt.
    """
    from randomizer.rewards.catalogue import BUFF_TARGETS
    from randomizer.shop.catalogue import unit_access_tier

    tiers = {name: 0 for name in TIER_NAMES}
    categories = {}
    buffs = {}
    if run is None:
        return {'tiers': tiers, 'categories': categories, 'buffs': buffs}

    def add_unit(unit_id, weight=1):
        unit_id = str(unit_id or '').upper()
        if not unit_id or unit_id not in BUFF_TARGETS:
            return
        tier = unit_access_tier(unit_id)
        if tier in tiers:
            tiers[tier] += weight
        category = CATEGORY_EFFECTS.get(
            str(BUFF_TARGETS[unit_id].get('category') or '')
        )
        if category:
            categories[category] = categories.get(category, 0) + weight

    for unit_id in (
        tuple(run.starting_unit_ids or ())
        + tuple(run.starting_defense_ids or ())
        + tuple(run.selected_permanent_units or ())
    ):
        add_unit(unit_id)
    for record in run.run_purchases or ():
        reward = _reward_by_id(getattr(record, 'reward_id', ''))
        if reward and reward.get('kind') != 'buff':
            add_unit(reward.get('unit'), max(1, int(
                getattr(record, 'quantity', 1) or 1
            )))
    for purchase in (
        tuple(run.run_buffs or ())
        + tuple(run.permanent_buffs_snapshot or ())
        + tuple(run.starting_draft_buffs or ())
    ):
        reward = _reward_by_id(getattr(purchase, 'reward_id', ''))
        if not reward or reward.get('kind') != 'buff':
            continue
        buff_type = str(reward.get('buff_type') or '')
        if not buff_type:
            continue
        stacks = max(1, int(getattr(purchase, 'stacks', 1) or 1))
        buffs[buff_type] = buffs.get(buff_type, 0) + stacks
        add_unit(reward.get('unit'), 0)
    return {'tiers': tiers, 'categories': categories, 'buffs': buffs}


def _tier_index(buff_id):
    for index, name in enumerate(TIER_NAMES, start=1):
        if buff_id.startswith(f'tier{index}_'):
            return index, name
    return None, None


def adaptive_weights(profile, buff_ids):
    """Return ``{buff_id: weight}`` scoring how well each answers the player.

    Powers and superweapons score zero here on purpose: nothing about them is
    a response, so they ride entirely on the uniform half of the draw.
    """
    tiers = profile['tiers']
    categories = profile['categories']
    buffs = profile['buffs']
    counter_scores = {}
    for buff_type, stacks in buffs.items():
        for answer in ARSENAL_COUNTERS.get(buff_type, ()):
            counter_scores[answer] = counter_scores.get(answer, 0) + stacks

    weights = {}
    for buff_id in buff_ids:
        index, tier_name = _tier_index(buff_id)
        if index is not None:
            stat = buff_id[len(f'tier{index}_'):]
            owned = tiers.get(tier_name, 0)
            # A tier the player has nothing in is not worth answering, and a
            # stat nobody bought is not worth countering. Their product is the
            # score, so both have to be true.
            weights[buff_id] = owned * counter_scores.get(stat, 0)
            continue
        for category, count in categories.items():
            if buff_id.startswith(f'{category}_'):
                weights[buff_id] = count
                break
        else:
            weights[buff_id] = 0
    return weights


def draw_weights(profile, buff_ids, adaptive_percent):
    """Blend the adaptive scores with a uniform floor.

    Returns integer weights so the seeded pick stays exact -- floats would
    make a replayed run depend on rounding.
    """
    buff_ids = tuple(buff_ids)
    if not buff_ids:
        return {}
    share = max(0, min(100, int(adaptive_percent)))
    uniform = 100 - share
    scores = adaptive_weights(profile, buff_ids)
    total = sum(scores.values())
    if not total or not share:
        return {buff_id: 100 for buff_id in buff_ids}
    count = len(buff_ids)
    return {
        buff_id: (
            uniform * total
            + share * scores[buff_id] * count
        )
        for buff_id in buff_ids
    }


def weighted_choice(buff_ids, weights, digest):
    """Pick one id from a seeded digest, proportional to its weight."""
    buff_ids = tuple(buff_ids)
    ordered = sorted(buff_ids)
    total = sum(max(0, int(weights.get(buff_id, 0))) for buff_id in ordered)
    if total <= 0:
        return ordered[int.from_bytes(digest[:4], 'big') % len(ordered)]
    position = int.from_bytes(digest[:8], 'big') % total
    for buff_id in ordered:
        position -= max(0, int(weights.get(buff_id, 0)))
        if position < 0:
            return buff_id
    return ordered[-1]


def draft_reason(profile, buff_id):
    """Return one clause saying why the enemy took this, or ``''``.

    An adaptation nobody can see is indistinguishable from the difficulty
    quietly rising, which is the failure mode this whole mechanic has.
    """
    from randomizer.rewards.catalogue import BUFF_TARGETS

    del BUFF_TARGETS
    index, tier_name = _tier_index(buff_id)
    if index is not None:
        stat = buff_id[len(f'tier{index}_'):]
        owned = profile['tiers'].get(tier_name, 0)
        provoked = sorted(
            buff_type
            for buff_type, answers in ARSENAL_COUNTERS.items()
            if stat in answers and profile['buffs'].get(buff_type)
        )
        if owned and provoked:
            return (
                f'answering your {owned} Tier {index} unit(s) and '
                f'{"/".join(provoked)} upgrades'
            )
        return ''
    for category, count in sorted(profile['categories'].items()):
        if buff_id.startswith(f'{category}_') and count:
            return f'answering your {count} {category} unit(s)'
    return ''


def draw_enemy_buff_ids(
    run, mission_code, unlocked, wanted, counts, stack_limits,
    config=SHOP_CONFIG,
):
    """Return the buffs one challenge hands the enemy, and why.

    ``counts`` is what the enemy already holds and is updated in place, so a
    saturated buff is skipped rather than silently wasted.
    """
    profile = arsenal_profile(run)
    weights = draw_weights(
        profile, unlocked, getattr(config, 'enemy_adaptive_draft_percent', 0)
    )
    drawn = []
    reasons = {}
    for index in range(max(1, wanted) * 8):
        if len(drawn) >= wanted:
            break
        available = [
            buff_id for buff_id in unlocked
            if counts.get(buff_id, 0) < stack_limits.get(buff_id, 1)
        ]
        if not available:
            break
        digest = sha256(
            f'shop_permanent_enemy_buff\0{run.seed}\0{run.stage}\0'
            f'{mission_code}\0{index}'.encode('utf-8')
        ).digest()
        choice = weighted_choice(available, weights, digest)
        counts[choice] = counts.get(choice, 0) + 1
        drawn.append(choice)
        reason = draft_reason(profile, choice)
        if reason:
            reasons[choice] = reason
    return tuple(drawn), reasons


def validate_enemy_draft_contract():
    """Prove the draw answers the player rather than only appearing to.

    A weighting that quietly degenerated to uniform would look identical from
    outside -- same ids, same counts, same determinism -- so every claim here
    is made against a pair of players who differ in exactly one thing.
    """
    stats = ('health', 'armor', 'speed', 'sight', 'damage')
    unlocked = tuple(
        f'tier{tier}_{stat}' for tier in (1, 2) for stat in stats
    ) + ('tier1_sensors', 'tier1_cloak', 'infantry_armor', 'ai_nuclear_missile')

    def profile(tier1_units, buffs):
        return {
            'tiers': {'tier_1': tier1_units, 'tier_2': 0, 'tier_3': 0},
            'categories': {'infantry': tier1_units},
            'buffs': dict(buffs),
        }

    cloaked = profile(4, {'cloak': 5})
    armoured = profile(4, {'armor': 5})
    nothing = profile(0, {})

    cloak_weights = draw_weights(cloaked, unlocked, 60)
    armour_weights = draw_weights(armoured, unlocked, 60)
    empty_weights = draw_weights(nothing, unlocked, 60)
    uniform_weights = draw_weights(cloaked, unlocked, 0)

    def share(weights, buff_id):
        total = sum(weights.values())
        return weights[buff_id] / total if total else 0.0

    # The one hard counter: enemy detectors are worth nothing until the player
    # buys stealth, and the draw has to know that.
    sensors_answered = share(cloak_weights, 'tier1_sensors')
    sensors_ignored = share(armour_weights, 'tier1_sensors')
    # Armour is answered with firepower, not with more armour.
    damage_answered = share(armour_weights, 'tier1_damage')
    damage_ignored = share(cloak_weights, 'tier1_damage')
    # A tier the player owns nothing in is not worth answering, however many
    # upgrades they bought.
    wrong_tier = share(cloak_weights, 'tier2_health')
    right_tier = share(armour_weights, 'tier1_damage')

    digest = sha256(b'contract').digest()
    repeated = {
        weighted_choice(unlocked, cloak_weights, digest)
        for _attempt in range(4)
    }
    reason = draft_reason(cloaked, 'tier1_sensors')

    return {
        # Every claim is comparative: the same effect, two players.
        'enemy_draft_counters_cloak_valid': (
            sensors_answered > sensors_ignored * 2
        ),
        'enemy_draft_counters_armor_valid': (
            damage_answered > damage_ignored * 2
        ),
        'enemy_draft_ignores_empty_tier_valid': wrong_tier < right_tier,
        # A player who has committed to nothing gets no adaptation at all,
        # which is what keeps an early run from feeling targeted.
        'enemy_draft_neutral_without_arsenal_valid': (
            len(set(empty_weights.values())) <= 2
        ),
        # Zero percent has to reproduce the uniform draw exactly, or the
        # setting is not the escape hatch it claims to be.
        'enemy_draft_uniform_at_zero_valid': (
            len(set(uniform_weights.values())) == 1
        ),
        # Nothing is ever closed off: the uniform half keeps every unlocked
        # id reachable no matter how lopsided the arsenal.
        'enemy_draft_leaves_nothing_unreachable_valid': all(
            weight > 0 for weight in cloak_weights.values()
        ),
        'enemy_draft_deterministic_valid': len(repeated) == 1,
        'enemy_draft_explains_itself_valid': (
            'cloak' in reason and not draft_reason(nothing, 'tier1_sensors')
        ),
    }
