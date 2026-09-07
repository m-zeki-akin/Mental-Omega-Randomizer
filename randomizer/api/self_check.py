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
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from .contract import ApiError, actions, call, describe_actions


TOOLKIT_NAMES = ('tkinter', 'import tk', 'ttk.', 'webview')
# A reading that is about one named thing and cannot be asked in general,
# so the sweep asks it without one to prove it refuses cleanly rather than
# to read it. No screen calls it yet -- it and `skirmish.tiers` are there
# for the shelf and tier tables that are not drawn.
ARGUMENT_REQUIRED = frozenset({'campaign.catalogue', 'skirmish.upgrades'})


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


def _a_setting_kept_is_a_setting_read_back_valid():
    """What a setting screen writes is what the next reading answers.

    Both setup screens are the same shape -- a row says what kind of thing
    a setting is, a control changes it, and the launcher keeps it -- so
    what is checked is that shape rather than any one row: a switch comes
    back switched, a number out of range comes back at the edge of it, and
    a choice that is not a choice is refused rather than written.

    Against settings this check owns, because writing the player's while
    asking whether writing works is how a check becomes the thing it was
    meant to catch.
    """
    from randomizer.ui.campaign_settings import NUMBER, SECTIONS, SWITCH

    switch = next(
        (row for _name, rows in SECTIONS for row in rows
         if row['kind'] == SWITCH), None
    )
    number = next(
        (row for _name, rows in SECTIONS for row in rows
         if row['kind'] == NUMBER), None
    )
    if switch is None or number is None:
        return False

    def held(reply, key):
        for part in reply.get('result', {}).get('sections', ()):
            for setting in part['settings']:
                if setting['key'] == key:
                    return setting['value']
        return None

    with _store_of_its_own():
        before = call('campaign.settings')
        flipped = call(
            'campaign.use_setting',
            name=switch['key'],
            value=not held(before, switch['key']),
        )
        over = call(
            'campaign.use_setting',
            name=number['key'],
            value=number['maximum'] + 50,
        )
        under = call(
            'campaign.use_setting', name=number['key'], value=-50,
        )
        refused = call(
            'campaign.use_setting', name=switch['key'], value=None,
        )
        unknown = call('campaign.use_setting', name='no.such.setting', value=1)
        after = call('campaign.settings')
    return bool(
        before.get('ok')
        and held(flipped, switch['key']) is not held(before, switch['key'])
        and held(over, number['key']) == number['maximum']
        and held(under, number['key']) == number['minimum']
        and refused.get('kind') == 'ApiError'
        and unknown.get('kind') == 'ApiError'
        # And the sweep's own settings are thrown away with it: what the
        # player has is what they had.
        and after.get('ok')
    )


def _held(reply, key):
    """Return one setting out of a settings reply, whatever kind it is."""
    for part in reply.get('result', {}).get('sections', ()):
        for setting in part['settings']:
            if setting['key'] == key:
                return setting
    return None


def _a_named_list_keeps_what_it_was_given_valid():
    """A setting that names things keeps the names it was handed.

    Three settings name units, powers and rewards out of the installed
    rules rather than holding a value, and what they may name is a few
    hundred entries long -- so the screen is a search, and the reply
    carries only what has been picked. What is checked is that picking
    survives the round trip, and that a name the rules no longer know is
    kept rather than quietly dropped: a submod renaming a unit must not
    empty a list somebody built.
    """
    from randomizer.ui.campaign_catalogues import catalogue
    from randomizer.ui.campaign_settings import SEARCH, SECTIONS

    named = None
    for row in (row for _name, rows in SECTIONS for row in rows
                if row['kind'] == SEARCH):
        # A catalogue whose entries are called what they are called,
        # rather than one whose names are their own labels: resolving
        # a name is the thing being checked.
        entry = next(
            (entry for entry in catalogue(row['catalogue_name'])
             if entry['label'] != entry['id']), None
        )
        if entry is not None:
            named = (row, entry)
            break
    if named is None:
        return False
    row, entry = named
    key = f"{row['where']}.{row['key']}" if row['where'] else row['key']

    with _store_of_its_own():
        listed = call('campaign.catalogue', name=row['catalogue_name'])
        entries = (listed.get('result') or {}).get('entries') or []
        if not entries:
            return False
        first = entry['id']
        kept = call(
            'campaign.use_setting', name=key, value=[first, 'NO-SUCH-THING'],
        )
        emptied = call('campaign.use_setting', name=key, value=[])
        refused = call('campaign.use_setting', name=key, value=first)
        unnamed = call('campaign.catalogue', name='no-such-catalogue')
    chosen = (_held(kept, key) or {}).get('chosen') or []
    return bool(
        [entry['id'] for entry in chosen] == [first, 'NO-SUCH-THING']
        # The one the rules know is named; the one they do not is shown
        # as itself, which is what makes it possible to take out.
        and chosen[0]['label'] == entry['label']
        and chosen[1]['label'] == 'NO-SUCH-THING'
        and (_held(emptied, key) or {}).get('value') == []
        and refused.get('kind') == 'ApiError'
        and unnamed.get('kind') == 'ApiError'
    )


def _all_of_them_is_kept_as_all_of_them_valid():
    """Everything allowed stays written as everything, not as a list.

    The enemy's bonuses are stored as a wildcard when they are all
    allowed, which is what makes a settings file still mean all of them
    after a submod adds one. Turning one off has to write the list out,
    and turning it back on has to collapse it again -- otherwise a player
    who looked at the setting once would be pinned to the bonuses that
    existed the day they looked.
    """
    from randomizer.ui.campaign_settings import BY_KEY, ENEMY_SCALING

    allowed = f'{ENEMY_SCALING}.allowed_buff_ids'
    total = f'{ENEMY_SCALING}.maximum_total_buffs'
    # Every bonus there is, rather than the ones this player has left
    # on: what is being checked is what happens when they are all on,
    # and a player who has turned four of them off would otherwise be
    # checking something else.
    names = [entry['id'] for entry in BY_KEY[allowed]['catalogue']]

    def stored():
        # Asked for by name each time: the settings this reads are the
        # sweep's own, and they are put in place around the calls
        # below rather than around this function.
        from randomizer.config.player import load_config

        block = load_config()
        for step in ENEMY_SCALING.split('.'):
            block = block.get(step) or {}
        return block.get('allowed_buff_ids')

    with _store_of_its_own():
        # The list is only worth showing while the enemy collects
        # anything at all, so this is what makes it visible.
        call('campaign.use_setting', name=total, value=5)
        every = call('campaign.use_setting', name=allowed, value=None)
        if every.get('ok'):
            return False
        opened = call('campaign.settings')
        # And the screen can see every one of them: the list itself is
        # written for the player by the limits beside it, where nought
        # means the enemy is never handed that bonus at all.
        drawn = _held(opened, f'{ENEMY_SCALING}.caps') or {}
        if len(drawn.get('entries') or ()) != len(names) or len(names) < 2:
            return False
        def limits(reply):
            drawn = _held(reply, f'{ENEMY_SCALING}.caps') or {}
            return {
                entry['key'].rsplit('.', 1)[-1]: entry['value']
                for entry in drawn.get('entries') or ()
            }

        call('campaign.use_setting', name=allowed, value=names)
        as_wildcard = stored()
        every = limits(call('campaign.settings'))
        fewer = call('campaign.use_setting', name=allowed, value=names[1:])
        as_list = stored()
        without = limits(fewer)
        call('campaign.use_setting', name=allowed, value=names)
        collapsed = stored()
        # And the other way about: the screen moves the limit, and the
        # list follows it. This is the write the player actually makes.
        one = f'{ENEMY_SCALING}.caps.{names[0]}'
        call('campaign.use_setting', name=one, value=0)
        after_nought = stored()
        call('campaign.use_setting', name=one, value=2)
        after_two = stored()
    return bool(
        as_wildcard == ['*']
        and as_list == names[1:]
        and collapsed == ['*']
        # And what the screen draws says the same thing: a bonus the
        # enemy may not be given is a limit of nought, whatever the
        # settings hold for it.
        and every.get(names[0])
        and without.get(names[0]) == 0
        and without.get(names[1])
        # Written out in full, without the one turned off. The wildcard
        # would answer "not in" for every name there is, so what is
        # checked is that it is no longer the wildcard.
        and after_nought != ['*']
        and names[0] not in (after_nought or ())
        and after_two == ['*']
    )


def _the_registry_is_never_half_ready_valid():
    """A call arriving while the actions are still being imported waits.

    The window hands a page's calls to whatever thread it has, and a page
    opening asks for several things in the same breath. The registry used
    to mark itself loaded before it did the loading, so the second of
    those calls read a registry that was still being filled and was told
    the launcher had no action by that name -- a screen that failed for a
    moment at startup and worked ever after, which is the hardest kind of
    fault to be shown.

    Checked against a stand-in for the importing, because the real one
    has already happened by the time anything can ask.
    """
    from randomizer.api import contract

    finished = []
    returned = []
    lock = threading.Lock()

    def slow_import():
        time.sleep(0.05)
        with lock:
            finished.append(time.monotonic())

    held_import = contract._import_action_modules
    held_flag = contract._LOADED
    contract._import_action_modules = slow_import
    contract._LOADED = False
    try:
        def ask():
            contract._load_actions()
            with lock:
                returned.append(time.monotonic())

        threads = [threading.Thread(target=ask) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        contract._import_action_modules = held_import
        contract._LOADED = held_flag
    return bool(
        # Imported once, however many asked.
        len(finished) == 1
        and len(returned) == 4
        # And nobody was told it was ready before it was.
        and all(moment >= finished[0] for moment in returned)
    )


def _two_presses_at_once_keep_both_valid():
    """Two controls moved at once are two settings kept, not one.

    Nearly every command reads the settings, changes one and writes them
    back. Two of those on two threads -- which is what two presses a
    moment apart are, because the window answers on whatever thread it
    has -- would interleave, and the second would write over the first
    with the copy it had read before the first had saved. The player sees
    a control spring back on its own, and nothing anywhere says why.

    Written against two weights because they are the two controls most
    likely to be pressed in a row.
    """
    from randomizer.config import player as settings_file
    from randomizer.ui.campaign_settings import REWARD_WEIGHTS

    first = f'{REWARD_WEIGHTS}.main.unit_unlocks'
    second = f'{REWARD_WEIGHTS}.main.power_unlocks'

    def held(key):
        block = settings_file.load_config()
        for step in key.split('.')[:-1]:
            block = block.get(step) or {}
        return block.get(key.split('.')[-1])

    with _store_of_its_own():
        # Keeping settings is a file write in the launcher and a dict
        # update here, so the window a lost write slips through is much
        # narrower than the real one. This is what widens it back.
        keeping = settings_file.save_config

        def slowly(config):
            time.sleep(0.03)
            keeping(config)

        settings_file.save_config = slowly
        threads = [
            threading.Thread(
                target=call, args=('campaign.use_setting',),
                kwargs={'name': key, 'value': value},
            )
            for key, value in ((first, 5), (second, 10))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        kept = (held(first), held(second))
    return kept == (5, 10)


def _a_ceiling_answers_the_other_settings_valid():
    """What a number is offered is what it could actually reach.

    The enemy's total is capped by the bonuses that are allowed: turning
    most of them off lowers what the run could ever hand out, and the
    generator has always clamped the number there. A screen that went on
    offering the full range would be offering a number that is quietly
    cut on the way to the seed.
    """
    from randomizer.ui.campaign_settings import BY_KEY, ENEMY_SCALING

    total = f'{ENEMY_SCALING}.maximum_total_buffs'
    allowed = f'{ENEMY_SCALING}.allowed_buff_ids'
    names = [entry['id'] for entry in BY_KEY[allowed]['catalogue']]
    with _store_of_its_own():
        call('campaign.use_setting', name=allowed, value=names)
        whole = _held(call('campaign.settings'), total) or {}
        call('campaign.use_setting', name=allowed, value=names[:4])
        narrowed = _held(call('campaign.settings'), total) or {}
        call('campaign.use_setting', name=allowed, value=[])
        # Nothing allowed is the one case the row's own maximum stands
        # in for, so that the list a player emptied stays reachable.
        emptied = _held(call('campaign.settings'), total) or {}
    return bool(
        whole.get('maximum') == BY_KEY[total]['maximum']
        and 0 < narrowed.get('maximum', 0) < whole['maximum']
        # And the number itself is offered no higher than the ceiling.
        and narrowed['value'] <= narrowed['maximum']
        and emptied.get('maximum') == whole['maximum']
    )


def _a_battle_that_cannot_be_fought_is_not_committed_to_valid():
    """A launch that fails leaves the table as it found it.

    Committing to an offer is final -- a battle scouted and put back is a
    battle chosen twice -- and the run used to be saved as committed
    before the battle it named had been built. Anything that went wrong
    after that point left the run pinned to an offer it could not fight
    and could not trade for another, with giving up the only way out. A
    submod that takes a country away is enough to cause it.

    So the run is written down between the files being written and the
    game being started, and this is what says so: a battle that cannot be
    built is refused, and the offer is still there to choose.
    """
    from randomizer.skirmish import launch as battles
    from randomizer.skirmish.factions import skirmish_countries
    from randomizer.skirmish.table import deal
    from randomizer.skirmish.transitions import skip_warmup, start_run

    from . import skirmish as actions_module

    countries = skirmish_countries()
    if len(countries) < 2:
        return False

    def cannot_build(*_args, **_kwargs):
        raise LookupError('This run plays a country the rules no longer have')

    with _store_of_its_own():
        store = actions_module._repository()
        store.save_run(deal(skip_warmup(start_run(
            run_id='a-run-that-cannot-be-fought',
            seed='SELFCHECK',
            player_country=countries[0].index,
            ally_country=countries[1].index,
            created='2026-01-01',
        ))))
        building = battles.build_battle
        battles.build_battle = cannot_build
        try:
            refused = call('skirmish.launch', index=0)
        finally:
            battles.build_battle = building
        after = store.load_run()
    return bool(
        refused.get('kind') == 'ApiError'
        and after is not None
        # Free to choose, which is the whole of it.
        and after.committed_offer is None
    )


def _a_setting_about_one_thing_keeps_both_halves_valid():
    """What is turned off for one thing is kept for that thing only.

    A unit barred from one kind of upgrade is a sentence with two
    subjects, and the setting holds both: which units, and what each of
    them is never offered. What is checked is that both halves survive
    the round trip -- and that a unit with nothing turned off is not
    kept at all, because "here with nothing barred" and "not here" would
    otherwise be two ways of saying one thing.
    """
    from randomizer.ui.campaign_settings import MAP, SECTIONS

    row = next(
        (row for _name, rows in SECTIONS for row in rows
         if row['kind'] == MAP), None
    )
    if row is None or not row['catalogue']:
        return False
    key = f"{row['where']}.{row['key']}" if row['where'] else row['key']
    kind = row['catalogue'][0]['id']

    with _store_of_its_own():
        listed = call('campaign.catalogue', name=row['catalogue_name'])
        entries = (listed.get('result') or {}).get('entries') or []
        if not entries:
            return False
        first = entries[0]['id']
        kept = call('campaign.use_setting', name=key, value={
            first: [kind, 'no-such-upgrade'],
            'nothing-barred': [],
        })
        refused = call('campaign.use_setting', name=key, value=[first])
        emptied = call('campaign.use_setting', name=key, value={})
    chosen = (_held(kept, key) or {}).get('chosen') or []
    return bool(
        len(chosen) == 1
        and chosen[0]['id'] == first
        # Named out of the installed rules, like any other search.
        and chosen[0]['label'] == entries[0]['label']
        # The upgrade it is barred from, and not the one that does not
        # exist.
        and chosen[0]['types'] == [kind]
        and refused.get('kind') == 'ApiError'
        and ((_held(emptied, key) or {}).get('chosen') or []) == []
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
    # And the player's own settings. A command that takes no arguments --
    # putting a mode's setup back to its defaults, say -- cannot be made
    # to refuse the way one that needs a name does, so the sweep is given
    # settings of its own to write over. The two functions are patched
    # rather than the path they use: loading also migrates a settings file
    # from where an older launcher kept it, and a path that does not exist
    # yet is exactly what makes it move one.
    from randomizer.config import player as settings_file

    reading, writing = settings_file.load_config, settings_file.save_config
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
        held = reading()
        settings_file.load_config = lambda: deepcopy(held)

        def keep_settings(config):
            held.clear()
            held.update(deepcopy(config))

        settings_file.save_config = keep_settings
        try:
            yield
        finally:
            actions_module._repository = original
            leaderboard.LEADERBOARD_PATH = board
            session.SKIRMISH_LAUNCH_PATH = ticket_path
            session.start = starter
            launch.prepare_battle = preparer
            ai.remove_staged_ai_file = staged
            settings_file.load_config = reading
            settings_file.save_config = writing


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
    settings_kept = _a_setting_kept_is_a_setting_read_back_valid()
    one_at_a_time = _two_presses_at_once_keep_both_valid()
    ready_or_waiting = _the_registry_is_never_half_ready_valid()
    ceilings_answer = _a_ceiling_answers_the_other_settings_valid()
    nothing_committed = (
        _a_battle_that_cannot_be_fought_is_not_committed_to_valid()
    )
    named_lists_kept = _a_named_list_keeps_what_it_was_given_valid()
    both_halves_kept = (
        _a_setting_about_one_thing_keeps_both_halves_valid()
    )
    all_of_them_kept = _all_of_them_is_kept_as_all_of_them_valid()
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
        'api_settings_kept_are_read_back_valid': settings_kept,
        'api_two_presses_at_once_keep_both_valid': one_at_a_time,
        'api_registry_is_never_half_ready_valid': ready_or_waiting,
        'api_ceilings_answer_the_settings_valid': ceilings_answer,
        'api_failed_launch_commits_to_nothing_valid': nothing_committed,
        'api_named_lists_keep_their_names_valid': named_lists_kept,
        'api_settings_about_one_thing_keep_both_valid': both_halves_kept,
        'api_all_of_them_stays_all_of_them_valid': all_of_them_kept,
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
            and settings_kept
            and one_at_a_time
            and ready_or_waiting
            and ceilings_answer
            and nothing_committed
            and named_lists_kept
            and both_halves_kept
            and all_of_them_kept
            and before == after
            and unknown.get('ok') is False
            and described
            and all(replies[name].get('ok') for name in reads)
        ),
    }
