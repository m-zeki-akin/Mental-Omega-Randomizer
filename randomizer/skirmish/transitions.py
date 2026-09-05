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

from .model import DEFAULT_LIVES, SkirmishRun
from .progression import is_challenge_battle


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
):
    run_id = str(run_id or '')
    seed = str(seed or '')
    if not run_id or not seed:
        raise SkirmishTransitionError('A skirmish run needs a run_id and a seed')
    return SkirmishRun(
        run_id=run_id,
        seed=seed,
        created=str(created or ''),
        player_country=int(player_country),
        ally_country=int(ally_country),
        lives=max(1, int(lives)),
    )


def offer_battles(run, offers):
    """Put this battle's offers on the table, replacing what stood there."""
    offers = tuple(offers)
    if not offers:
        raise SkirmishTransitionError('A battle needs at least one offer')
    return replace(run, offers=offers, committed_offer=None)


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


def record_victory(run, *, coins=0):
    """Advance to the next battle, keeping what the challenge pool has seen."""
    offer = run.committed()
    if offer is None:
        raise SkirmishTransitionError('No battle was committed')
    if run.status is not RunStatus.ACTIVE:
        raise SkirmishTransitionError('This run is over')
    used = run.used_challenge_maps
    if offer.challenge and offer.map_path not in used:
        used = used + (offer.map_path,)
    return replace(
        run,
        battle=run.battle + 1,
        won_battles=run.won_battles + 1,
        coins=run.coins + max(0, int(coins)),
        offers=(),
        committed_offer=None,
        used_challenge_maps=used,
    )


def record_defeat(run):
    """Spend a life. The battle stands; the run ends when none are left."""
    if run.committed() is None:
        raise SkirmishTransitionError('No battle was committed')
    if run.status is not RunStatus.ACTIVE:
        raise SkirmishTransitionError('This run is over')
    revivals = run.revivals_used + 1
    out_of_lives = revivals >= run.lives
    return replace(
        run,
        revivals_used=revivals,
        status=RunStatus.FAILED if out_of_lives else run.status,
        committed_offer=None,
    )


def give_up(run):
    if run.status is not RunStatus.ACTIVE:
        return run
    return replace(run, status=RunStatus.FAILED, committed_offer=None)


def run_progress_text(run):
    """The headline: where the run is and what it has left."""
    lives = run.lives_left
    challenge = ' — challenge' if is_challenge_battle(run.battle) else ''
    return (
        f'Battle {run.battle} — tier {run.tier}{challenge} — '
        f'{lives} {"life" if lives == 1 else "lives"}'
    )
