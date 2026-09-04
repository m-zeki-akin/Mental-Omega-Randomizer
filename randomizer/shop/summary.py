"""Pure player-facing Shop reward and run summaries."""

from .config import SHOP_CONFIG
from .economy import mission_reward
from .model import RunStatus
from .modifiers import format_difficulty, run_difficulty
from .text import gem_text


def reward_breakdown_lines(
    mission_class,
    *,
    victory_coin_bonus_level=0,
    modifiers=(),
    mission_modifier=None,
    challenge_hunter_level=0,
    stage=1,
    gem_scale_percent=100,
    config=SHOP_CONFIG,
):
    """Itemise what a mission pays at the tier it is actually played.

    Stage and pacing scale are part of the payout, so a breakdown that omits
    them reports the tier 1 value for a mission the player is winning at tier
    4. They are passed through rather than defaulted at every call site.
    """
    definition = config.mission_rewards[mission_class]
    reward = mission_reward(
        mission_class,
        victory_coin_bonus_level=victory_coin_bonus_level,
        modifiers=modifiers,
        mission_modifier=mission_modifier,
        challenge_hunter_level=challenge_hunter_level,
        stage=stage,
        gem_scale_percent=gem_scale_percent,
        config=config,
    )
    lines = [
        f'{definition.display_name} base: +{definition.run_coins} Ore, '
        f'+{gem_text(definition.meta_coins)}',
    ]
    if reward.base_run_coins != definition.run_coins:
        lines.append(
            f'Modified mission Ore: +{reward.base_run_coins}'
        )
    modified_meta = (
        reward.meta_coins
        - reward.mission_bonus_meta_coins
        - reward.challenge_hunter_meta_coins
    )
    if modified_meta != definition.meta_coins:
        lines.append(f'Modified Gems: +{gem_text(modified_meta)}')
    if reward.victory_bonus_run_coins:
        lines.append(
            'Permanent Victory Bonus: '
            f'+{reward.victory_bonus_run_coins} Ore'
        )
    if mission_modifier is not None:
        lines.append(
            f'{mission_modifier.title}: '
            f'+{reward.mission_bonus_run_coins} Ore, '
            f'+{gem_text(reward.mission_bonus_meta_coins)}'
        )
    if reward.challenge_hunter_run_coins or reward.challenge_hunter_meta_coins:
        lines.append(
            'Challenge Hunter: '
            f'+{reward.challenge_hunter_run_coins} Ore, '
            f'+{gem_text(reward.challenge_hunter_meta_coins)}'
        )
    lines.append(
        f'Total: +{reward.run_coins} Ore, '
        f'+{gem_text(reward.meta_coins)}'
    )
    return tuple(lines)


def shop_run_progress_text(run, profile=None, config=SHOP_CONFIG):
    """Return the run's headline progress label.

    An endless run has no denominator to count towards, so it reports the
    stage it is on, the tier that paces its difficulty, and the lives left.
    """
    from .missions import difficulty_stage
    from .transitions import maximum_run_lives

    tier = difficulty_stage(run.stage, config)
    if not run.endless:
        return f'Run {run.stage} / {run.run_length}'
    from .config import run_shop_config

    lives = max(0, maximum_run_lives(
        profile, run_shop_config(run, config)
    ) - run.emergency_revivals_used)
    return (
        f'Mission {run.stage} — Stage {tier} — '
        f'{lives} {"life" if lives == 1 else "lives"}'
    )


def _missions_won_line(run, config=SHOP_CONFIG):
    if not run.endless:
        return (
            f'Missions won: {len(run.completed_missions)} / {run.run_length}'
        )
    # completed_missions is the per-stage offer history in an endless run, so
    # the paid victories are what actually counts progress.
    return f'Missions won: {len(run.rewarded_victories)}'


def _lives_line(run, profile, config=SHOP_CONFIG):
    from .config import run_shop_config
    from .transitions import maximum_run_lives

    total = maximum_run_lives(profile, run_shop_config(run, config))
    return (
        f'Lives: {max(0, total - run.emergency_revivals_used)} / {total}'
    )


def _permanent_enemy_buff_line(run):
    """Summarise the escalation this run's challenges handed the enemy."""
    from randomizer.rewards.enemy_scaling import ENEMY_BUFF_BY_ID

    if not run.permanent_enemy_buff_ids:
        return 'Enemy challenge buffs: none'
    counts = {}
    for buff_id in run.permanent_enemy_buff_ids:
        counts[buff_id] = counts.get(buff_id, 0) + 1
    rendered = ', '.join(
        f'{ENEMY_BUFF_BY_ID.get(buff_id, {}).get("name", buff_id)}'
        + (f' x{count}' if count > 1 else '')
        for buff_id, count in sorted(counts.items())
    )
    return f'Enemy challenge buffs: {rendered}'


def run_summary_lines(profile, run, mission_titles=None, config=SHOP_CONFIG):
    if run is None:
        return ('No Shop run exists.',)
    mission_titles = mission_titles or {}
    status_heading = {
        RunStatus.ACTIVE: 'RUN ACTIVE',
        RunStatus.FAILED: 'RUN OVER',
        RunStatus.COMPLETED: 'RUN VICTORY',
    }[run.status]
    lines = [
        status_heading,
        f'Seed: {run.seed}',
        _missions_won_line(run),
        f'Ore remaining: {run.run_coins}',
        f'Persistent Gems: {profile.meta_coins}',
        # Bought and won land in the same place, so the wording says
        # "gained" rather than claiming every one of them was paid for.
        f'Units gained this run: '
        f'{sum(item.quantity for item in run.run_purchases)}',
        f'Upgrade stacks gained: {sum(item.stacks for item in run.run_buffs)}',
        f'Free starting draft buffs: '
        f'{sum(item.stacks for item in run.starting_draft_buffs)}',
        f'Free Buff Tokens used: {run.free_buff_tokens_used}',
        _lives_line(run, profile),
        _permanent_enemy_buff_line(run),
        'Run difficulty: ' + format_difficulty(
            run_difficulty(run.modifiers, run.reward_settings)
        ),
        'Modifiers: ' + (
            ', '.join(
                config.modifiers[item].display_name for item in run.modifiers
            )
            if run.modifiers else 'None'
        ),
    ]
    if run.status is RunStatus.FAILED:
        if run.failed_mission_code == 'GAVE_UP':
            lines.append(f'Run given up at stage {run.failed_stage}.')
        else:
            title = mission_titles.get(
                run.failed_mission_code, run.failed_mission_code
            )
            lines.append(f'Failed at stage {run.failed_stage}: {title}')
        if profile.salvaged_run_coins:
            lines.append(
                f'Recovery Salvage banked: {profile.salvaged_run_coins} Ore '
                'for the next run.'
            )
    if run.completed_missions:
        lines.append('Completed missions:')
        lines.extend(
            f'  {index}. {mission_titles.get(code, code)}'
            for index, code in enumerate(run.completed_missions, start=1)
        )
    return tuple(lines)
