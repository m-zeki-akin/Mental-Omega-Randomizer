"""The game the launcher started, while it is up and once it is not.

A window with an event loop can watch a process. A page cannot: it asks,
on a timer, and what it asks has to be able to answer at any moment --
before a battle, during one, and on the first read after the game closed,
which is the read that has to record what happened.

So the whole of it is one small piece of state and one poll. The battle is
kept because the result needs it: which run it belonged to, which offer was
committed, and where in the game's log to start reading.
"""

import subprocess
import sys

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import DEBUG_LOG, GAME_ROOT

from randomizer.skirmish.results import last_game_result, read_debug_log_tail


_PLAYING = None


def running():
    """Whether the launcher's own game is still up."""
    return bool(
        _PLAYING is not None
        and _PLAYING['process'].poll() is None
    )


def start(battle):
    """Start the game on a prepared battle, and remember which one it is."""
    from randomizer.launch.game import game_command
    from randomizer.launch.syringe import windows_syringe_command_line

    global _PLAYING
    argv = game_command()
    command = argv
    options = {}
    if sys.platform == 'win32':
        # Syringe parses its own raw command line and refuses to start
        # unless the host executable is quoted, which a list cannot carry.
        command = windows_syringe_command_line(argv)
        options['executable'] = argv[0]
    # Where the log already ends, so the score block this battle writes is
    # the one that is read rather than the one before it.
    try:
        offset = DEBUG_LOG.stat().st_size if DEBUG_LOG.exists() else 0
    except OSError:
        offset = 0
    process = subprocess.Popen(command, cwd=str(GAME_ROOT), **options)
    _PLAYING = {
        'battle': battle,
        'process': process,
        'log_offset': offset,
    }
    log_event(
        'skirmish_process_started',
        run_id=battle['run_id'],
        battle=battle['battle'],
        map=battle['map'].path.name,
        pid=process.pid,
    )
    return process.pid


def poll(repository):
    """Say what the game is doing, and record it the moment it stops."""
    global _PLAYING
    if _PLAYING is None:
        return {'playing': False, 'finished': None}
    if _PLAYING['process'].poll() is None:
        battle = _PLAYING['battle']
        return {
            'playing': True,
            'finished': None,
            'map_name': battle['map'].name,
            'battle': battle['battle'],
        }
    playing, _PLAYING = _PLAYING, None
    return _record(playing, repository)


def _record(playing, repository):
    """Read the game's own score block and write the outcome into the run."""
    from randomizer.skirmish.ai import remove_staged_ai_file
    from randomizer.skirmish.leaderboard import record_finished_run
    from randomizer.skirmish.model import RunStatus
    from randomizer.skirmish.table import deal
    from randomizer.skirmish.transitions import (
        SkirmishTransitionError,
        record_defeat,
        record_victory,
    )

    # The staged AI file belongs to the battle that just ended.
    remove_staged_ai_file()
    battle = playing['battle']
    result = last_game_result(
        read_debug_log_tail(DEBUG_LOG, playing['log_offset']),
        player_name=battle['player_name'],
    )
    run = repository.load_run()
    if run is None or run.run_id != battle['run_id']:
        # The player switched runs while the game was up. The battle
        # stands for nothing.
        return {
            'playing': False,
            'finished': {'won': False, 'recorded': False,
                         'message': 'That battle belonged to another run.'},
        }
    # A game closed before it finished is a defeat. It cannot be anything
    # else: a battle going badly could otherwise be thrown away from the
    # menu at no cost, which is the whole of the difficulty.
    won = bool(result is not None and result.won)
    ally = None
    from randomizer.skirmish.factions import country_by_index

    ally_country = country_by_index(run.ally_country)
    if ally_country is not None:
        ally = ally_country.country_id
    try:
        if won:
            run = record_victory(run, ally_country=ally, result=result)
        else:
            run = record_defeat(run, result=result)
    except SkirmishTransitionError as exc:
        return {
            'playing': False,
            'finished': {'won': won, 'recorded': False, 'message': str(exc)},
        }
    dealt = True
    if run.status is RunStatus.ACTIVE:
        # A victory clears the table, and so does the walk into Nightmare
        # behind it. Dealing here rather than when a screen next reads is
        # what lets a screen read without writing.
        try:
            run = deal(run)
        except (SkirmishTransitionError, OSError):
            dealt = False
    else:
        # Out of lives. What it did outlives it on the board.
        try:
            record_finished_run(run, 'Out of lives')
        except OSError as exc:
            log_event('skirmish_board_write_failed', error=str(exc))
    saved = repository.save_run(run)
    log_event(
        'skirmish_finished',
        run_id=battle['run_id'],
        battle=battle['battle'],
        map=battle['map'].path.name,
        finished=result is not None,
        won=won,
        result=result.to_dict() if result else None,
    )
    return {
        'playing': False,
        'finished': {
            'won': won,
            'recorded': True,
            'unfinished': result is None,
            'battle': saved.battle,
            'lives_left': saved.lives_left,
            'status': saved.status.value,
            'dealt': dealt,
            'message': _outcome_text(won, result, saved),
        },
    }


def _outcome_text(won, result, run):
    if won:
        return (
            f'Victory. {result.kills} kills, {result.lost} lost. '
            f'Battle {run.battle} is ready.'
        )
    how = (
        'Closed before it finished, which counts as a defeat'
        if result is None else 'Defeat'
    )
    if run.status.name == 'ACTIVE':
        lives = run.lives_left
        return (
            f'{how}. {lives} {"life" if lives == 1 else "lives"} left; '
            'the same battle stands.'
        )
    return f'{how}. The run ends at battle {run.battle}.'
