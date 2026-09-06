"""Assert the boundary is a boundary.

Four things have to stay true or the interface it was drawn for will grow
through it again: what crosses it survives being written as JSON, a failure
comes back as a reply rather than as an exception nobody catches, nothing on
this side imports a widget toolkit, and asking every action what it does
leaves the player's own runs exactly as they were.

That last one is here because it was not. Checking that a command refuses
cleanly means calling it, and every command was being called against the
player's saved runs -- so a check meant to prove the launcher safe was
skipping a warmup and giving up a run every time it ran. The commands are
called against a store of their own now, and the row after them says the
real one never moved.
"""

import json
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from .contract import ApiError, actions, call, describe_actions


TOOLKIT_NAMES = ('tkinter', 'import tk', 'ttk.', 'webview')
# Readings that are about one named thing and cannot be asked in
# general. The screens that use them are where they are checked.
ARGUMENT_REQUIRED = frozenset({'skirmish.upgrades'})


def _package_files():
    """Return the boundary's own modules, minus the one checking them.

    This file names the toolkits it is looking for, so reading itself
    would always find one.
    """
    here = Path(__file__).resolve()
    return sorted(
        path for path in here.parent.glob('*.py') if path != here
    )


def _stored_runs():
    """Return what the player has, as something comparable.

    Both stores: the runs being played and the board of the ones that
    ended. A command sweep can reach either -- ending a run writes to both.
    """
    from randomizer.skirmish.leaderboard import load_board
    from randomizer.skirmish.persistence import (
        SkirmishPersistenceError,
        SkirmishRepository,
    )

    try:
        runs, active = SkirmishRepository().list_runs()
    except SkirmishPersistenceError as exc:
        return ('unreadable', str(exc))
    return (
        active,
        tuple(sorted(
            (run.run_id, run.battle, run.status.value, len(run.purchases))
            for run in runs
        )),
        tuple(sorted(entry.run_id for entry in load_board())),
    )


@contextmanager
def _store_of_its_own():
    """Point every command at a run store that is thrown away afterwards.

    A command has to be called to find out whether it refuses cleanly, and
    a command called for that reason must not be able to touch a run
    somebody is playing.
    """
    from randomizer.skirmish import leaderboard
    from randomizer.skirmish.persistence import (
        SkirmishPersistencePaths,
        SkirmishRepository,
    )

    from . import skirmish as actions_module

    original = actions_module._repository
    # The board is the other thing a command can write: a run given up is
    # a run recorded. It goes to the same temporary folder.
    board = leaderboard.LEADERBOARD_PATH
    with TemporaryDirectory(prefix='mo-api-check-') as folder:
        paths = SkirmishPersistencePaths(
            runs=Path(folder) / 'runs.dat',
            backup_dir=Path(folder) / 'backups',
        )
        actions_module._repository = lambda: SkirmishRepository(paths)
        leaderboard.LEADERBOARD_PATH = Path(folder) / 'board.dat'
        try:
            yield
        finally:
            actions_module._repository = original
            leaderboard.LEADERBOARD_PATH = board


def validate_api_contract():
    """Return one row per promise the boundary makes."""
    registered = actions()
    described = describe_actions()

    reads = {
        name for name, entry in registered.items()
        if entry.kind == 'read' and name not in ARGUMENT_REQUIRED
    }
    commands = {
        name for name, entry in registered.items()
        if entry.kind == 'command'
    }

    # Every action answers, and what it answers is plain data. The ones
    # that need a game folder are read here too: an action that only works
    # on a developer's machine is not an action a launcher can offer.
    before = _stored_runs()
    replies = {}
    for name in registered:
        if name in commands:
            continue
        try:
            replies[name] = call(name)
        except Exception as exc:  # noqa: BLE001 - that is the failure
            replies[name] = {'ok': False, 'error': repr(exc), 'kind': 'raised'}
    with _store_of_its_own():
        for name in commands:
            try:
                replies[name] = call(name)
            except Exception as exc:  # noqa: BLE001 - that is the failure
                replies[name] = {
                    'ok': False, 'error': repr(exc), 'kind': 'raised',
                }
    after = _stored_runs()

    json_safe = True
    for reply in replies.values():
        try:
            json.dumps(reply)
        except (TypeError, ValueError):
            json_safe = False

    # Two failures a screen has to be able to survive.
    unknown = call('no.such.action')
    bad_argument = call('skirmish.upgrades')

    toolkit_free = True
    for path in _package_files():
        text = path.read_text(encoding='utf-8', errors='ignore')
        if any(name in text for name in TOOLKIT_NAMES):
            toolkit_free = False

    return {
        'api_actions': len(registered),
        'api_actions_described_valid': bool(
            described
            and len(described) == len(registered)
            and all(entry['summary'] for entry in described)
        ),
        'api_replies_json_safe_valid': bool(json_safe and replies),
        'api_failures_are_replies_valid': bool(
            unknown.get('ok') is False
            and unknown.get('kind') == 'UnknownAction'
            and bad_argument.get('ok') is False
            and bad_argument.get('kind') == 'ApiError'
            and bad_argument.get('error')
        ),
        # A reading answers whenever it is asked. This is the row that
        # catches one which only works on the machine it was written on --
        # one that needs a run to exist, or a file, or an argument nobody
        # will always have.
        'api_readings_answer_valid': bool(
            reads and all(replies[name].get('ok') for name in reads)
        ),
        # A command may refuse: there may be no run to buy for. What it
        # may not do is crash -- it refuses with something a screen can
        # put in front of a player.
        'api_commands_refuse_cleanly_valid': bool(
            commands
            and all(
                replies[name].get('ok')
                or replies[name].get('kind') == 'ApiError'
                for name in commands
            )
        ),
        # The point of the boundary: the launcher's rules never learn what
        # is drawing them, and this side never learns either.
        'api_toolkit_free_valid': toolkit_free,
        # Asking the launcher what it can do is not playing it. Every
        # command was called above; the player's own runs are where they
        # were, down to which one was being played.
        'api_asking_changes_nothing_valid': before == after,
        'api_contract_valid': bool(
            json_safe
            and toolkit_free
            and before == after
            and unknown.get('ok') is False
            and described
            and all(replies[name].get('ok') for name in reads)
        ),
    }
