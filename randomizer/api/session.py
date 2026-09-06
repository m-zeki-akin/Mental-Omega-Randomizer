"""The game the launcher started, while it is up and once it is not.

A window with an event loop can watch a process. A page cannot: it asks,
on a timer, and what it asks has to be able to answer at any moment --
before a battle, during one, and on the first read after the game closed,
which is the read that has to record what happened.

So the whole of it is one small piece of state and one poll. What is kept
is a ticket: which run the battle belonged to, which battle it was, and
where in the game's log to start reading. Everything on it is plain data,
because the ticket is written to disk as well as held in memory.

That is the second thing here. A battle used to be remembered only for as
long as the launcher was open, so closing the launcher while a game was up
meant nothing ever recorded it -- no life charged, and the same offer
still there to fight again. The ticket outlives the process that wrote it,
and the first poll of the next launcher finds it: still being played if
the game is up, and otherwise a battle to be recorded exactly as if the
launcher had never been closed.
"""

import subprocess
import sys

from randomizer.core.diagnostics import event as log_event
from randomizer.core.integrity import sign
from randomizer.core.paths import DEBUG_LOG, GAME_ROOT, SKIRMISH_LAUNCH_PATH
from randomizer.core.storage import atomic_write_opaque, read_opaque_object

from randomizer.skirmish.results import last_game_result, read_debug_log_tail


# The battle this launcher started, and the process playing it. The
# process is not part of the ticket: a handle cannot be written down, and
# a launcher that did not start the game has none to hold.
_PLAYING = None
_PROCESS = None
LAUNCH_SCHEMA_VERSION = 1


def _ticket(battle, offset):
    """Return what a battle has to leave behind to be recorded later."""
    return {
        'run_id': battle['run_id'],
        'battle': battle['battle'],
        'map_name': battle['map'].name,
        'map_file': battle['map'].path.name,
        'player_name': battle['player_name'],
        'log_offset': int(offset),
    }


def _keep(ticket):
    """Write the ticket where the next launcher will find it."""
    try:
        atomic_write_opaque(SKIRMISH_LAUNCH_PATH, sign({
            'schema_version': LAUNCH_SCHEMA_VERSION,
            'launch': dict(ticket),
        }))
    except OSError as exc:
        # Worth saying and not worth stopping for: the battle is still
        # watched by this launcher, just not by the next one.
        log_event('skirmish_launch_not_kept', error=str(exc))


def _drop():
    try:
        SKIRMISH_LAUNCH_PATH.unlink(missing_ok=True)
    except OSError as exc:
        log_event('skirmish_launch_not_cleared', error=str(exc))


def _kept():
    """Return the battle a launcher left behind, if there is one."""
    try:
        if not SKIRMISH_LAUNCH_PATH.is_file():
            return None
        stored = read_opaque_object(SKIRMISH_LAUNCH_PATH)
    except (OSError, ValueError):
        return None
    document = stored.get('document', stored) if isinstance(stored, dict) else {}
    ticket = document.get('launch') if isinstance(document, dict) else None
    if not isinstance(ticket, dict) or not ticket.get('run_id'):
        return None
    return {
        'run_id': str(ticket.get('run_id') or ''),
        'battle': int(ticket.get('battle') or 0),
        'map_name': str(ticket.get('map_name') or 'a battle'),
        'map_file': str(ticket.get('map_file') or ''),
        'player_name': str(ticket.get('player_name') or 'Commander'),
        'log_offset': int(ticket.get('log_offset') or 0),
    }


def _adopt():
    """Take up a battle this launcher did not start.

    Returns the ticket and whether the game is still up. Only reached when
    nothing is being played here, which is why the process table is asked:
    there is no handle to ask instead.
    """
    from randomizer.launch.running import game_is_running

    ticket = _kept()
    if ticket is None:
        return None, False
    return ticket, game_is_running()


def running():
    """Whether a battle is being played, by this launcher or before it."""
    if _PROCESS is not None:
        return _PROCESS.poll() is None
    _left, up = _adopt()
    return bool(up)


def start(battle):
    """Start the game on a prepared battle, and remember which one it is."""
    from randomizer.launch.game import game_command
    from randomizer.launch.syringe import windows_syringe_command_line

    global _PLAYING, _PROCESS
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
    _PLAYING = _ticket(battle, offset)
    _PROCESS = process
    _keep(_PLAYING)
    log_event(
        'skirmish_process_started',
        run_id=_PLAYING['run_id'],
        battle=_PLAYING['battle'],
        map=_PLAYING['map_file'],
        pid=process.pid,
    )
    return process.pid


def poll(repository):
    """Say what the game is doing, and record it the moment it stops."""
    global _PLAYING, _PROCESS
    if _PROCESS is None:
        # Nothing was started here. There may still be a battle to finish.
        ticket, up = _adopt()
        if ticket is None:
            return {'playing': False, 'finished': None}
        if up:
            return {
                'playing': True,
                'finished': None,
                'map_name': ticket['map_name'],
                'battle': ticket['battle'],
                'adopted': True,
            }
        log_event(
            'skirmish_launch_adopted',
            run_id=ticket['run_id'],
            battle=ticket['battle'],
            map=ticket['map_file'],
        )
        return _record(ticket, repository)
    if _PROCESS.poll() is None:
        return {
            'playing': True,
            'finished': None,
            'map_name': _PLAYING['map_name'],
            'battle': _PLAYING['battle'],
        }
    ticket, _PLAYING, _PROCESS = _PLAYING, None, None
    return _record(ticket, repository)


def _record(ticket, repository):
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

    # The battle is over however this ends: recorded, refused, or
    # belonging to a run that is no longer there. Leaving the ticket behind
    # would offer the same battle to the next launcher again.
    _drop()
    # The staged AI file belongs to the battle that just ended.
    remove_staged_ai_file()
    result = last_game_result(
        read_debug_log_tail(DEBUG_LOG, ticket['log_offset']),
        player_name=ticket['player_name'],
    )
    run = repository.load_run()
    if run is None or run.run_id != ticket['run_id']:
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
        run_id=ticket['run_id'],
        battle=ticket['battle'],
        map=ticket['map_file'],
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
