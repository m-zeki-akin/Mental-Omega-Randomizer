"""The campaign mission the launcher started, while it is up and once it is not.

The same problem the skirmish session solves, and mostly the same shape:
a page cannot watch a process, so it asks on a timer, and what it asks
has to answer before a mission, during one, and on the first read after
the game closed -- which is the read that has to write down what happened.

What is different is how much is being watched. A battle is one number in
the game's own log, read once at the end. A mission is a running
conversation: the map was written with trigger names in it, the engine
prints them as they fire, and each one is an objective to be paid out
while the game is still up. So the ticket carries a place in the log, and
every poll reads from there and hands what it finds to the recorder --
the same recorder the classic window uses, doing the same unlocking.

The ticket outlives the launcher that wrote it, and that is the point of
writing it down. A mission left running while the launcher was closed is
found again by the next one: still being played if the game is up, and
otherwise a mission to be settled exactly as if nobody had gone away.
"""

from pathlib import Path

from randomizer.core.diagnostics import event as log_event
from randomizer.core.integrity import sign
from randomizer.core.paths import CAMPAIGN_LAUNCH_PATH
from randomizer.core.storage import atomic_write_opaque, read_opaque_object


# The mission this launcher started, and the process playing it. As with a
# battle, the process is not part of the ticket: a handle cannot be
# written down, and a launcher that did not start the game has none.
_PLAYING = None
_PROCESS = None
LAUNCH_SCHEMA_VERSION = 1
# How long after a victory the game is closed, matching the window. Left
# alone it walks on into the next mission of its own campaign.
VICTORY_CLOSE_DELAY_S = 2.5


def _plain(hook):
    """Return the hook as something that can be written down.

    Two values on it are not data: the markers already seen are a set,
    and the map that was hooked is a path. Everything else the pipeline
    and the watcher put there is a string, a number, a flag, or the
    marker table -- and it is all kept, because a key dropped here is an
    objective the next launcher stops counting.
    """
    plain = {}
    for key, value in (hook or {}).items():
        if key == 'seen':
            plain['seen'] = sorted(str(item) for item in (value or ()))
        elif isinstance(value, Path):
            plain[key] = str(value)
        elif isinstance(value, dict):
            plain[key] = {
                str(name): str(check) for name, check in value.items()
            }
        elif value is None or isinstance(value, (str, int, float, bool)):
            plain[key] = value
        else:
            # Nothing reaches here today. If something does, it is a new
            # key on the hook, and losing it quietly is how a mission
            # would stop being watched properly with nobody told.
            log_event(
                'campaign_launch_key_not_kept',
                key=str(key),
                kind=type(value).__name__,
            )
    return plain


def _hook_from(ticket):
    """Return the watcher's hook, as the recorder expects to be handed it."""
    hook = dict(ticket.get('hook') or {})
    hook['seen'] = set(hook.get('seen') or ())
    if hook.get('root_map'):
        hook['root_map'] = Path(hook['root_map'])
    return hook


def _ticket(hook, seed, pid):
    """Return what a mission has to leave behind to be recorded later."""
    import time

    return {
        'seed': str(seed or ''),
        'hook': _plain(hook),
        # Which process was playing it, so a later launcher can tell this
        # mission from any other game the player has since opened.
        'pid': int(pid or 0),
        'started_at': time.time(),
    }


def _keep(ticket):
    """Write the ticket where the next launcher will find it."""
    try:
        atomic_write_opaque(CAMPAIGN_LAUNCH_PATH, sign({
            'schema_version': LAUNCH_SCHEMA_VERSION,
            'launch': dict(ticket),
        }))
    except OSError as exc:
        # Worth saying and not worth stopping for: the mission is still
        # watched by this launcher, just not by the next one.
        log_event('campaign_launch_not_kept', error=str(exc))


def _drop():
    try:
        CAMPAIGN_LAUNCH_PATH.unlink(missing_ok=True)
    except OSError as exc:
        log_event('campaign_launch_not_cleared', error=str(exc))


def _kept():
    """Return the mission a launcher left behind, if there is one."""
    try:
        if not CAMPAIGN_LAUNCH_PATH.is_file():
            return None
        stored = read_opaque_object(CAMPAIGN_LAUNCH_PATH)
    except (OSError, ValueError):
        return None
    document = stored.get('document', stored) if isinstance(stored, dict) else {}
    ticket = document.get('launch') if isinstance(document, dict) else None
    if not isinstance(ticket, dict):
        return None
    hook = ticket.get('hook')
    if not isinstance(hook, dict) or not hook.get('mission_code'):
        return None
    return {
        'seed': str(ticket.get('seed') or ''),
        'hook': hook,
        'pid': int(ticket.get('pid') or 0),
        'started_at': float(ticket.get('started_at') or 0.0),
    }


def _adopt():
    """Take up a mission this launcher did not start.

    Returns the ticket and whether the game is still up. Asked of the
    machine rather than a handle, because there is no handle to ask.

    Unlike a battle there is no score block to look for first: a mission
    says what it did through its own trigger names, and those are read
    out of the log by whoever is polling, from a place the ticket keeps.
    So the only question here is whether the process that was playing it
    is still there -- and by pid, because a game the player opened
    themselves is not this mission.
    """
    from randomizer.launch.running import game_is_running, pid_is_running

    ticket = _kept()
    if ticket is None:
        return None, False
    if ticket.get('pid'):
        return ticket, pid_is_running(ticket['pid'])
    return ticket, game_is_running()


def running():
    """Whether a mission is being played, by this launcher or before it."""
    if _PROCESS is not None:
        return _PROCESS.poll() is None
    _left, up = _adopt()
    return bool(up)


def start(hook, seed, process):
    """Remember the mission a launcher has just opened the game on."""
    global _PLAYING, _PROCESS

    _PLAYING = _ticket(hook, seed, getattr(process, 'pid', 0))
    _PROCESS = process
    _keep(_PLAYING)
    log_event(
        'campaign_process_started',
        seed=_PLAYING['seed'],
        code=_PLAYING['hook'].get('mission_code'),
        scenario=_PLAYING['hook'].get('scenario'),
        markers=len(_PLAYING['hook'].get('markers') or {}),
        pid=_PLAYING['pid'],
    )
    return _PLAYING['pid']


class _Adopted:
    """A process this launcher did not start, asked about by pid.

    Enough of a handle for the closing path to work on: it can say
    whether the game is still up, and it can be asked to stop.
    """

    def __init__(self, pid):
        self.pid = int(pid or 0)

    def poll(self):
        from randomizer.launch.running import pid_is_running

        return None if self.pid and pid_is_running(self.pid) else 0

    def terminate(self):
        import os
        import signal

        if not self.pid:
            raise OSError('There is no process to close')
        os.kill(self.pid, getattr(signal, 'SIGTERM', 15))


def poll(maker):
    """Read what the game has said since the last ask, and record it.

    ``maker`` is a recorder built on the run as it now stands. Everything
    that decides anything happens inside it -- which marker is which
    objective, what an objective pays, which mission that opens. This
    reads the log, hands it over, and writes the ticket back.
    """
    global _PLAYING, _PROCESS

    if _PROCESS is None:
        ticket, up = _adopt()
        if ticket is None:
            return {'playing': False, 'finished': None}
        process, adopted = _Adopted(ticket['pid']), True
    else:
        ticket, process, adopted = _PLAYING, _PROCESS, False
        up = process.poll() is None

    maker.active_hook = _hook_from(ticket)
    maker.active_game_process = process
    maker.active_mission_attempt = {
        'mission_code': maker.active_hook.get('mission_code'),
        'scenario': maker.active_hook.get('scenario'),
    }
    maker.read_hook_log_once()
    maker.process_pending_restart_failure()
    code = maker.active_hook.get('mission_code')
    ticket['hook'] = _plain(maker.active_hook)

    if up:
        if not adopted:
            _PLAYING = ticket
        _keep(ticket)
        _close_if_won(maker, process, ticket)
        done, total = maker.mission_check_counts(code)
        return {
            'playing': True,
            'finished': None,
            'code': code,
            'scenario': maker.active_hook.get('scenario'),
            'adopted': adopted,
            'done': done,
            'total': total,
            'won': bool(maker.active_hook.get('won')),
        }
    return _record(maker, ticket, adopted)


def _close_if_won(maker, process, ticket):
    """Close the game a couple of seconds after a victory, once."""
    import time

    hook = maker.active_hook
    if not hook.get('won') or hook.get('victory_close_scheduled'):
        return
    won_at = float(hook.get('won_at') or 0.0)
    if won_at and time.time() - won_at < VICTORY_CLOSE_DELAY_S:
        return
    hook['victory_close_scheduled'] = True
    ticket['hook'] = _plain(hook)
    _keep(ticket)
    maker.close_game_after_victory(process, hook)


def _record(maker, ticket, adopted):
    """Settle a mission whose game has stopped."""
    global _PLAYING, _PROCESS

    hook = maker.active_hook
    code = hook.get('mission_code')
    # The mission is over however this ends. Leaving the ticket behind
    # would hand the same finished mission to the next launcher.
    _drop()
    _PLAYING, _PROCESS = None, None
    complete = maker.is_mission_complete(code)
    if code and not complete:
        # A mission closed without victory is an attempt spent. Same rule
        # the window applies, and for the same reason: a mission going
        # badly could otherwise be thrown away at no cost.
        maker.record_failed_mission_attempt(
            code, 'Mission closed without victory',
        )
    maker.cleanup_generated_root_maps()
    maker.disable_generated_rules_for_client()
    done, total = maker.mission_check_counts(code)
    log_event(
        'campaign_process_finished',
        seed=ticket.get('seed'),
        code=code,
        scenario=hook.get('scenario'),
        markers_seen=len(hook.get('seen') or ()),
        markers_expected=len(hook.get('markers') or {}),
        completed=complete,
        adopted=adopted,
    )
    maker.active_hook = None
    maker.active_game_process = None
    maker.active_mission_attempt = None
    return {
        'playing': False,
        'finished': {
            'code': code,
            'won': bool(complete),
            'recorded': True,
            'done': done,
            'total': total,
            'adopted': adopted,
            'message': (
                f'{code} complete. {done} of {total} recorded.'
                if complete
                else f'{code} closed without victory. {done} of {total} recorded.'
            ),
        },
    }
