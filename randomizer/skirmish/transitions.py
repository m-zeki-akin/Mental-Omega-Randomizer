"""What a battle does to the run it was fought in.

Pure rules: every function takes a run and returns the run it becomes, so
what a victory or a defeat means can be read and checked without a game, a
launcher, or a file.

A defeat costs a life and leaves the battle standing. The same battle is
fought again -- the offers were drawn from the run's seed and its battle
number, so it is the same battle, not a new one -- which is how Shop Mode
treats a lost stage and what makes a life worth something.
"""

from dataclasses import replace

from randomizer.shop.model import RunStatus

from .model import (
    BATTLES_PER_TIER,
    DEFAULT_LIVES,
    TIER_COUNT,
    WARMUP_BATTLE,
    SkirmishRun,
)
from .progression import is_challenge_battle, is_warmup
from .shop import (
    ally_shopping,
    battle_reward,
    owned_stacks,
    purchase_stacks,
    STARTING_ORE,
)


class SkirmishTransitionError(RuntimeError):
    """Raised when a battle cannot do what it was asked to do."""


def start_run(
    *,
    run_id,
    seed,
    player_country,
    ally_country,
    created='',
    lives=DEFAULT_LIVES,
    ally_roster='',
):
    run_id = str(run_id or '')
    seed = str(seed or '')
    if not run_id or not seed:
        raise SkirmishTransitionError('A skirmish run needs a run_id and a seed')
    run = SkirmishRun(
        run_id=run_id,
        seed=seed,
        created=str(created or ''),
        player_country=int(player_country),
        ally_country=int(ally_country),
        lives=max(1, int(lives)),
        coins=STARTING_ORE,
        ally_coins=STARTING_ORE,
    )
    if not ally_roster:
        return run
    # The ally does its first shopping before the run's first shot. It had
    # none in the opening battle otherwise: it shops out of what a victory
    # pays, and at the start nothing has been won.
    purchases, left = ally_shopping(run, ally_roster, run.ally_coins)
    return replace(run, ally_purchases=purchases, ally_coins=left)


def offer_battles(run, offers, *, shelf=None):
    """Put this battle's offers on the table, replacing what stood there.

    The shop's six are offers too, and are drawn at the same moment for the
    same reason: what a battle offers should not change while the player is
    looking at it.
    """
    offers = tuple(offers)
    if not offers:
        raise SkirmishTransitionError('A battle needs at least one offer')
    return replace(
        run,
        offers=offers,
        shelf=tuple(shelf) if shelf is not None else run.shelf,
        committed_offer=None,
    )


def commit_offer(run, index):
    """Take one offer. Committing is what a launch does, and it is final."""
    index = int(index)
    if not 0 <= index < len(run.offers):
        raise SkirmishTransitionError(f'No offer {index} in this battle')
    if run.status is not RunStatus.ACTIVE:
        raise SkirmishTransitionError('This run is over')
    if run.committed_offer is not None and run.committed_offer != index:
        raise SkirmishTransitionError(
            'This battle is already committed to another offer'
        )
    return replace(run, committed_offer=index)


def record_victory(run, *, ally_country=None):
    """Advance to the next battle, paying for it and letting the ally shop.

    What a battle pays is decided by the tier it was fought in and nothing
    else. Paying by score would make a won battle worth dragging out, and a
    run's difficulty is not something to grind around.
    """
    offer = run.committed()
    if offer is None:
        raise SkirmishTransitionError('No battle was committed')
    if run.status is not RunStatus.ACTIVE:
        raise SkirmishTransitionError('This run is over')
    used = run.used_challenge_maps
    if offer.challenge and offer.map_path not in used:
        used = used + (offer.map_path,)
    reward = battle_reward(
        run.battle,
        challenge=offer.challenge,
        bonus_percent=offer.bonus_percent,
    )
    ally_purchases, ally_coins = (
        (run.ally_purchases, run.ally_coins + reward) if not ally_country
        else ally_shopping(run, ally_country, run.ally_coins + reward)
    )
    won = replace(
        run,
        battle=run.battle + 1,
        won_battles=run.won_battles + 1,
        coins=run.coins + reward,
        ally_coins=ally_coins,
        ally_purchases=ally_purchases,
        offers=(),
        shelf=(),
        committed_offer=None,
        used_challenge_maps=used,
    )
    if won.battle <= TIER_COUNT * BATTLES_PER_TIER:
        return won
    return enter_nightmare(won, ally_country=ally_country)


def enter_nightmare(run, *, ally_country=None):
    """Start the nine tiers again, with both your armies stripped.

    What the enemies have they keep -- their tiers do not reset, they
    begin again from the top with everything the last walk taught them.
    What you have goes: the Ore, the upgrades, and the ally's too. A
    Nightmare run is the same nine tiers fought by an army that has to be
    built again.
    """
    stripped = replace(
        run,
        battle=WARMUP_BATTLE + 1,
        nightmare=run.nightmare + 1,
        coins=STARTING_ORE,
        purchases=(),
        ally_coins=STARTING_ORE,
        ally_purchases=(),
        offers=(),
        shelf=(),
        committed_offer=None,
    )
    if not ally_country:
        return stripped
    # The ally is equipped again before the first shot, the way it was at
    # the start of the run.
    purchases, left = ally_shopping(
        stripped, ally_country, stripped.ally_coins
    )
    return replace(stripped, ally_purchases=purchases, ally_coins=left)


def buy_upgrade(run, upgrade):
    """Spend Ore on one more stack of an upgrade."""
    if run.status is not RunStatus.ACTIVE:
        raise SkirmishTransitionError('This run is over')
    if is_warmup(run.battle):
        raise SkirmishTransitionError(
            'The warmup is fought with what you have'
        )
    owned = owned_stacks(run.purchases, upgrade.unit, upgrade.buff_type)
    if owned >= upgrade.limit:
        raise SkirmishTransitionError(
            f'{upgrade.name} is already at its limit'
        )
    if run.coins < upgrade.price:
        raise SkirmishTransitionError(
            f'{upgrade.name} costs {upgrade.price} Ore; you have {run.coins}'
        )
    return replace(
        run,
        coins=run.coins - upgrade.price,
        purchases=purchase_stacks(run.purchases, upgrade),
    )


def record_defeat(run):
    """Spend a life. The battle stands; the run ends when none are left.

    Except in the warmup, which costs nothing: it is the fight before the
    run starts counting, and a run that can be lost before it has begun is
    not a warmup.
    """
    if run.committed() is None:
        raise SkirmishTransitionError('No battle was committed')
    if run.status is not RunStatus.ACTIVE:
        raise SkirmishTransitionError('This run is over')
    if is_warmup(run.battle):
        return replace(run, committed_offer=None)
    revivals = run.revivals_used + 1
    out_of_lives = revivals >= run.lives
    return replace(
        run,
        revivals_used=revivals,
        status=RunStatus.FAILED if out_of_lives else run.status,
        committed_offer=None,
    )


def skip_warmup(run):
    """Step past the warmup without fighting it, and without being paid."""
    if run.status is not RunStatus.ACTIVE:
        raise SkirmishTransitionError('This run is over')
    if not is_warmup(run.battle):
        raise SkirmishTransitionError('The warmup is already behind you')
    return replace(
        run,
        battle=WARMUP_BATTLE + 1,
        offers=(),
        shelf=(),
        committed_offer=None,
    )


def give_up(run):
    if run.status is not RunStatus.ACTIVE:
        return run
    return replace(run, status=RunStatus.FAILED, committed_offer=None)


def run_progress_text(run):
    """The headline: where the run is and what it has left."""
    lives = run.lives_left
    round_name = f'Nightmare {run.nightmare} — ' if run.nightmare else ''
    if is_warmup(run.battle):
        return (
            f'{round_name}Warmup — '
            f'{lives} {"life" if lives == 1 else "lives"} in hand'
        )
    challenge = ' — challenge' if is_challenge_battle(run.battle) else ''
    return (
        f'{round_name}Battle {run.battle} — tier {run.tier}{challenge} — '
        f'{lives} {"life" if lives == 1 else "lives"}'
    )
