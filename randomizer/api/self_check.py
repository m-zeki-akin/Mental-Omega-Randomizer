"""Assert the boundary is a boundary.

Some things have to stay true or the interface it was drawn for will grow
through it again: what crosses it survives being written as JSON, a failure
comes back as a reply rather than as an exception nobody catches, an
action's own arguments reach it whatever they are called, nothing on this
side imports a widget toolkit, and asking every action what it does leaves
the player's own runs exactly as they were.

That last one is here because it was not. Checking that a command refuses
cleanly means calling it, and every command was being called against the
player's saved runs -- so a check meant to prove the launcher safe was
skipping a warmup and giving up a run every time it ran.

Worse followed. Once one command could start a run, the sweep could reach
a launch with a run standing in front of it, and starting a battle is
exactly what a launch does: the check opened the game. A set has no order,
so it did that on some runs and not others.

So each command is called against a store built for that one call and
thrown away after it, in a fixed order, and starting a game is taken away
from the boundary for the length of the sweep. The row after them says the
player's runs, their board, and the files a battle is written into are all
where they were.
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


def _touched():
    """Return everything a sweep must leave alone, as something comparable.

    The runs being played, the board of the ones that ended, whether a
    battle is up, the three files a battle is written into, and the
    player's own settings. Each of the first four has been written by a
    check that was only supposed to be asking; the settings are here
    because a command that writes one now exists.
    """
    from randomizer.config.player import load_config
    from randomizer.core.paths import GAME_ROOT, SPAWN_INI
    from randomizer.skirmish.launch import SPAWN_MAP_INI
    from randomizer.skirmish.leaderboard import load_board
    from randomizer.skirmish.persistence import (
        SkirmishPersistenceError,
        SkirmishRepository,
    )

    from . import session

    def stamp(path):
        try:
            return (path.name, path.stat().st_mtime_ns, path.stat().st_size)
        except OSError:
            return (path.name, None, None)

    try:
        runs, active = SkirmishRepository().list_runs()
        stored = tuple(sorted(
            (run.run_id, run.battle, run.status.value, len(run.purchases))
            for run in runs
        ))
    except SkirmishPersistenceError as exc:
        active, stored = 'unreadable', (str(exc),)
    return (
        active,
        stored,
        tuple(sorted(entry.run_id for entry in load_board())),
        # A check that leaves a game running is a check that started one.
        session.running(),
        tuple(stamp(path) for path in (
            SPAWN_INI, SPAWN_MAP_INI, GAME_ROOT / 'aimo.ini',
            session.SKIRMISH_LAUNCH_PATH,
        )),
        tuple(sorted(
            (key, repr(value)) for key, value in load_config().items()
        )),
    )


def _arguments_arrive_valid():
    """An action's own argument names reach it, whatever they are called.

    Several actions take an argument called ``name`` -- a mode's, a
    theme's, an interface's. Dispatch used to take that word too, so every
    one of those calls arrived as two values for one parameter and failed
    before the action saw them. Nothing in the reply said so: it read as
    the action refusing.

    Checked across the bridge rather than at the registry, because the
    bridge is the caller that cannot pass anything positionally.
    """
    from randomizer.shell.host import Bridge

    bridge = Bridge()
    # A value nothing could mistake for a real one, so an action that
    # quotes it back proves it received what was sent.
    sent = 'nowhere-in-particular'

    def asked(action, arguments):
        # A collision raises rather than replying, and a row that raises
        # takes every other row with it.
        try:
            return bridge.call(action, arguments)
        except Exception as exc:  # noqa: BLE001 - that is the failure
            return {'ok': False, 'error': repr(exc), 'kind': 'raised'}

    echoes = [
        asked('launcher.use_mode', {'name': sent}),
        asked('launcher.use_theme', {'name': sent}),
    ]
    # And one whose argument is not called name, so the row says something
    # about arguments rather than about one word.
    other = asked('skirmish.buy', {'key': sent})
    return bool(
        all(reply.get('ok') is False for reply in echoes)
        and all(sent in reply.get('error', '') for reply in echoes)
        # The action's own refusal, not a dispatch error wearing its name.
        and all(reply.get('kind') == 'ApiError' for reply in echoes)
        and other.get('kind') == 'ApiError'
    )


def _battle_outlives_the_launcher_valid():
    """A battle started by one launcher is recorded by the next.

    It used to be remembered only in memory, so closing the launcher while
    a game was up meant nothing recorded it: no life charged, and the same
    offer there to fight again. What is checked is the whole of that path
    -- a ticket written, a launcher that never saw the game finding it,
    the game still being up meaning wait, and the game being gone meaning
    the battle is recorded and the ticket taken away.

    And what a ticket must never do: mistake somebody else's game for its
    own. A player who opens Mental Omega themselves is a running
    ``gamemd.exe`` that has nothing to do with the ticket, so the question
    is asked of the process that was playing the battle. A battle whose
    result is already in the log is over whatever is running now.
    """
    from randomizer.api import session

    class Repository:
        """A store with nothing in it. What is checked here is the path."""

        def load_run(self):
            return None

    class Score:
        """Stands in for the game's own score block."""

        won = True

        def to_dict(self):
            return {'won': True}

    import randomizer.launch.running as machine

    def ticket_for(pid):
        return {
            'run_id': 'gone-with-the-launcher', 'battle': 3,
            'map_name': 'Somewhere', 'map_file': 'somewhere.map',
            'player_name': 'Commander', 'log_offset': 0, 'pid': pid,
        }

    with _store_of_its_own():
        kept = session.SKIRMISH_LAUNCH_PATH
        playing, process = session._PLAYING, session._PROCESS
        by_name, by_pid = machine.game_is_running, machine.pid_is_running
        reading, scoring = session.read_debug_log_tail, session.last_game_result
        with TemporaryDirectory(prefix='mo-ticket-check-') as folder:
            session.SKIRMISH_LAUNCH_PATH = Path(folder) / 'launch.dat'
            session._PLAYING = session._PROCESS = None
            # The player's own log has nothing to say about a battle that
            # never happened, and is not read for one.
            session.read_debug_log_tail = lambda *_a, **_k: ''
            session.last_game_result = lambda *_a, **_k: None
            try:
                # Nothing left behind: nothing is being played.
                empty = session.poll(Repository())
                ticket = ticket_for(4321)
                session._keep(ticket)
                read_back = session._kept()
                # The battle's own process is still up, and nothing else
                # by that name is: the battle is still being played, by a
                # launcher that never started it.
                machine.game_is_running = lambda name=None: False
                machine.pid_is_running = lambda pid: pid == 4321
                waiting = session.poll(Repository())
                held = session.running()
                # The result is in the log. The battle is over whatever
                # the process table says.
                session.last_game_result = lambda *_a, **_k: Score()
                scored = session.poll(Repository())
                session.last_game_result = lambda *_a, **_k: None
                # Somebody else's game: a copy running under the same name
                # while the battle's own process is gone. Not this battle.
                session._keep(ticket)
                machine.game_is_running = lambda name=None: True
                machine.pid_is_running = lambda pid: False
                stranger = session.poll(Repository())
                left = session.SKIRMISH_LAUNCH_PATH.exists()
            finally:
                machine.game_is_running, machine.pid_is_running = by_name, by_pid
                session.read_debug_log_tail = reading
                session.last_game_result = scoring
                session.SKIRMISH_LAUNCH_PATH = kept
                session._PLAYING, session._PROCESS = playing, process
    # A run belonging to nobody is the one outcome that needs no store
    # behind it, which is why every recording here is a refused one.
    return bool(
        empty == {'playing': False, 'finished': None}
        and read_back == ticket
        and waiting.get('playing') is True
        and waiting.get('adopted') is True
        and waiting.get('battle') == 3
        and held is True
        and scored.get('playing') is False
        and scored.get('finished', {}).get('recorded') is False
        and stranger.get('playing') is False
        and stranger.get('finished', {}).get('recorded') is False
        and not left
    )


def _finished_battle_settled_first_valid():
    """A battle nobody recorded is settled before another one starts.

    Nothing is being played once a battle's result is in the log -- which
    is right, and is exactly the moment a launch would have written its
    own ticket over the old one. The battle before it would then have been
    fought for nothing: no life charged, no victory kept, and the run
    quietly one battle behind where the player left it.

    So a launch settles what it finds first, and having settled it,
    refuses: the table it was about to commit an offer from has just been
    dealt again underneath it.
    """
    from randomizer.api import session
    from randomizer.api import skirmish as actions_module
    from randomizer.skirmish.factions import skirmish_countries
    from randomizer.skirmish.maps import STANDARD_POOL_DIR
    from randomizer.skirmish.results import HouseResult
    from randomizer.skirmish.table import deal
    from randomizer.skirmish.transitions import (
        commit_offer,
        skip_warmup,
        start_run,
    )

    countries = skirmish_countries()
    if len(countries) < 2 or not STANDARD_POOL_DIR.is_dir():
        # No maps to deal a battle from, so no battle to leave unsettled.
        return True
    with _store_of_its_own():
        repository = actions_module._repository()
        reading = session.read_debug_log_tail
        scoring = session.last_game_result
        try:
            run = commit_offer(deal(skip_warmup(start_run(
                run_id='settled-check', seed='SETTLED', created='2026-01-01',
                player_country=countries[0].index,
                ally_country=countries[1].index,
            ))), 0)
            repository.save_run(run)
            # The game wrote a win and closed while nobody was watching.
            session.read_debug_log_tail = lambda *_a, **_k: 'a battle that ended'
            session.last_game_result = lambda *_a, **_k: HouseResult(
                name='Commander', won=True, kills=7, built=12, lost=3,
                score=900,
            )
            session._keep({
                'run_id': run.run_id, 'battle': run.battle,
                'map_name': 'Somewhere', 'map_file': 'somewhere.map',
                'player_name': 'Commander', 'log_offset': 0, 'pid': 999999,
            })
            reply = call('skirmish.launch', index=0)
            settled = repository.load_run()
            left = session.SKIRMISH_LAUNCH_PATH.exists()
        finally:
            session.read_debug_log_tail = reading
            session.last_game_result = scoring
    return bool(
        reply.get('ok') is False
        and reply.get('kind') == 'ApiError'
        and 'recorded' in (reply.get('error') or '')
        # The win is the run's, the next table is dealt, and the ticket
        # that was about to be written over is gone.
        and settled is not None
        and settled.battle == run.battle + 1
        and settled.stats.won == 1
        and settled.offers
        and not left
    )


def _refuse_to_start(*_args, **_kwargs):
    raise ApiError('The self-check does not start games')


@contextmanager
def _store_of_its_own():
    """Point every command at a run store that is thrown away afterwards.

    A command has to be called to find out whether it refuses cleanly, and
    a command called for that reason must not be able to touch a run
    somebody is playing.
    """
    from randomizer.skirmish import ai, launch, leaderboard
    from randomizer.skirmish.persistence import (
        SkirmishPersistencePaths,
        SkirmishRepository,
    )

    from . import skirmish as actions_module

    from . import session

    original = actions_module._repository
    # The board is the other thing a command can write: a run given up is
    # a run recorded. It goes to the same temporary folder.
    board = leaderboard.LEADERBOARD_PATH
    # And the two things no check may do at all. A launch that found a run
    # in front of it wrote a battle into the game folder and opened the
    # game, and every command after it then refused politely because a game
    # was up -- so the sweep read as clean while a match was running.
    # Refusing both means it cannot happen whatever order they are called
    # in, and writing the battle is refused first because it comes first.
    starter = session.start
    preparer = launch.prepare_battle
    # The other two things a command can now reach past its store. A
    # battle the player is in the middle of leaves a ticket behind, and
    # anything that settles a battle takes that ticket away and clears the
    # AI file staged for it -- both in the player's own folders, neither
    # belonging to a sweep. So the ticket is written somewhere temporary,
    # and clearing the AI file is taken away for the length of the sweep.
    ticket_path = session.SKIRMISH_LAUNCH_PATH
    staged = ai.remove_staged_ai_file
    with TemporaryDirectory(prefix='mo-api-check-') as folder:
        paths = SkirmishPersistencePaths(
            runs=Path(folder) / 'runs.dat',
            backup_dir=Path(folder) / 'backups',
        )
        actions_module._repository = lambda: SkirmishRepository(paths)
        leaderboard.LEADERBOARD_PATH = Path(folder) / 'board.dat'
        session.SKIRMISH_LAUNCH_PATH = Path(folder) / 'launch.dat'
        session.start = _refuse_to_start
        launch.prepare_battle = _refuse_to_start
        ai.remove_staged_ai_file = lambda *_a, **_k: None
        try:
            yield
        finally:
            actions_module._repository = original
            leaderboard.LEADERBOARD_PATH = board
            session.SKIRMISH_LAUNCH_PATH = ticket_path
            session.start = starter
            launch.prepare_battle = preparer
            ai.remove_staged_ai_file = staged


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
    before = _touched()
    replies = {}
    for name in registered:
        if name in commands:
            continue
        try:
            replies[name] = call(name)
        except Exception as exc:  # noqa: BLE001 - that is the failure
            replies[name] = {'ok': False, 'error': repr(exc), 'kind': 'raised'}
    # One store each, in a fixed order. Sharing one meant a command could
    # meet what the command before it left, which is how a check that
    # starts a run and a check that starts a battle became the same sweep.
    for name in sorted(commands):
        with _store_of_its_own():
            try:
                replies[name] = call(name)
            except Exception as exc:  # noqa: BLE001 - that is the failure
                replies[name] = {
                    'ok': False, 'error': repr(exc), 'kind': 'raised',
                }
    # Called once, not once per row that reads it: it deals a table.
    settled_first = _finished_battle_settled_first_valid()
    after = _touched()

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
        'api_arguments_arrive_valid': _arguments_arrive_valid(),
        'api_battle_outlives_the_launcher_valid':
            _battle_outlives_the_launcher_valid(),
        'api_finished_battle_settled_first_valid': settled_first,
        # Asking the launcher what it can do is not playing it. Every
        # command was called above; the runs, the board, the battle files
        # and the game itself are all where they were.
        'api_asking_changes_nothing_valid': before == after,
        'api_contract_valid': bool(
            json_safe
            and toolkit_free
            and _arguments_arrive_valid()
            and _battle_outlives_the_launcher_valid()
            and settled_first
            and before == after
            and unknown.get('ok') is False
            and described
            and all(replies[name].get('ok') for name in reads)
        ),
    }
