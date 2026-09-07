"""What a campaign run is set up with, before a seed is generated.

The three campaign modes share almost every setting -- they are the same
campaign in a different order -- so one screen answers for all three, and
the table says which of the rows belong to Grid alone.

A run that has been generated keeps the settings it was generated with;
these describe the next one, which is why they are settings rather than
run state. The run itself is a separate thing to ask about, and there are
three questions: how far the one standing got, generating another, and
playing a mission of it.

How a table becomes a reply is not here either: that is the same question
for every setup screen, and it is answered once in ``settings``.
"""

from randomizer.campaign import progress, store
from randomizer.campaign.store import CHECK_SCHEMA_VERSION
from randomizer.ui import campaign_catalogues
from randomizer.ui.campaign_catalogues import CATALOGUE_NAMES
from randomizer.ui.campaign_settings import (
    ENEMY_CAPACITY,
    ENEMY_SCALING,
    SECTIONS,
)

from randomizer.core.diagnostics import event as log_event

from .contract import COMMAND, ApiError, action
from .pictures import data_uri
from .settings import Settings


# What the stored run calls the mode it was generated for, and the one
# mode whose openings are a board rather than a count.
MODE_KEY = 'progression_mode'
GRID_MODE = 'Grid Mode'


# What one icon is allowed to weigh, and how many may be asked for at
# once. A cameo is a sixty-by-forty-eight picture and runs to about four
# kilobytes; the ceiling is generous enough that a submod with a larger
# one still draws, and mean enough that nothing else gets through. The
# batch is what a page can show at a time -- roughly two screenfuls of
# rows -- because asking for three hundred is a megabyte and a half sent
# across for the sake of the twenty somebody is looking at.
MAX_CAMEO_BYTES = 64 * 1024
MAX_CAMEO_BATCH = 60


def _power_icons():
    """Return, for each power, whatever the rewards say its icon is.

    Two kinds, and the rules name neither. Four of the powers a run can
    hand out are the randomizer's own -- reinforcements, an engineering
    team -- and the game has no sidebar art for them because it never
    offers them from a sidebar; the reward that invents the power names
    an installed icon instead. And a power the Arsenal has rewritten may
    carry a picture of its own that is not in the game at all.
    """
    from randomizer.rewards.catalogue import REWARD_POOL

    named, drawn = {}, {}
    for reward in REWARD_POOL:
        power = str(reward.get('superweapon') or '').upper()
        if not power:
            continue
        image = reward.get('superweapon_sidebar_image')
        if image and power not in drawn:
            drawn[power] = str(image)
        icon = (reward.get('superweapon_rules') or {}).get('SidebarPCX')
        if icon and power not in named:
            named[power] = str(icon)
    return named, drawn


def _enemy_capacity(config, row):
    """Return what the bonuses actually allowed could add up to.

    The enemy's total is capped by them: turning most of them off lowers
    what a run could ever hand out, and the generator has always clamped
    the number there. A screen going on offering the full range would be
    offering a number that is quietly cut on the way to the seed.

    With nothing allowed the number means nothing at all, and the help
    beside it says so. The row's own range is what is offered then: a
    stepper pinned dead at nought reads as a broken control, and the
    number it holds is not asked of anything until a bonus is allowed
    again.
    """
    from randomizer.rewards.enemy_scaling import enemy_buff_capacity

    held = config
    for step in ENEMY_SCALING.split('.'):
        inside = held.get(step)
        held = inside if isinstance(inside, dict) else {}
    capacity = enemy_buff_capacity(held)
    return min(row['maximum'], capacity) if capacity else row['maximum']


CAMPAIGN = Settings(
    SECTIONS,
    catalogues=campaign_catalogues,
    ceilings={ENEMY_CAPACITY: _enemy_capacity},
)
BY_KEY = CAMPAIGN.by_key


def _settings():
    from randomizer.config.player import load_config

    return load_config()


def _keep(config):
    from randomizer.config.player import save_config

    save_config(config)


def _standing():
    """Return the seed the classic window has generated, if one stands."""
    from .launcher import _campaign_seed

    return str((_campaign_seed() or {}).get('seed') or '')


def _mode(config):
    """Return the campaign mode being set up, if one is standing.

    Which is asked of the screen table rather than of the mode: the modes
    this screen answers for are exactly the modes it is a screen of, and
    that is one list, not two. Asked from a roguelike workspace it says
    nothing is standing, and what comes back is the settings the three
    campaign modes share, without any one mode's own.
    """
    from randomizer.shell import screens as screen_table

    current = screen_table.known(config.get('progression_mode'))
    drawn = [name for name, _label in screen_table.screens(current)]
    return current if 'campaign' in drawn else ''


def _answer(config):
    mode = _mode(config)
    # A seed already generated is a run in progress, and a run in progress
    # is why the seed box is empty in the classic window. Both windows say
    # the same thing about it, and this is what it is.
    standing = _standing()
    return {
        'mode': mode,
        'generated_seed': standing,
        'sections': CAMPAIGN.answer(config, mode=mode, blank=bool(standing)),
    }


def _missions_by_code():
    """Return every installed mission by its code, or nothing at all.

    Nothing at all is a real answer: a launcher opened away from the game
    still has a run written down, and a run whose missions are named by
    their codes is worth more than a screen that refuses to draw.
    """
    from randomizer.core.paths import BATTLE_CLIENT_INI
    from randomizer.missions.catalogue import (
        FALLBACK_OBJECTIVE_COUNT,
        parse_missions,
    )

    try:
        listed = parse_missions(BATTLE_CLIENT_INI, FALLBACK_OBJECTIVE_COUNT)
    except (OSError, ValueError):
        return {}
    return {str(entry['code']): entry for entry in listed}


def _mission_view(state, code, installed, tiles):
    """Return one mission of a run, as much as a screen needs of it."""
    entry = installed.get(code) or {}
    done, total = progress.check_counts(state, code)
    complete = progress.is_complete(state, code)
    if tiles:
        # Grid says so itself. A mission it has not opened is locked
        # however many have been won, which is the whole point of a board.
        open_now = tiles.get(code) in {'unlocked', 'completed'}
    else:
        open_now = code in _open_codes(state)
    return {
        'code': code,
        'name': str(entry.get('title') or code),
        'side': str(entry.get('side') or ''),
        'installed': bool(entry),
        'unlocked': bool(open_now),
        'started': progress.is_started(state, code),
        'complete': complete,
        'done': done,
        'total': total,
    }


def _open_codes(state):
    """Return the open missions once, rather than once per mission."""
    global _OPEN_FOR
    held = _OPEN_FOR
    if held is not None and held[0] is state:
        return held[1]
    codes = frozenset(progress.unlocked_codes(state))
    _OPEN_FOR = (state, codes)
    return codes


_OPEN_FOR = None


@action('campaign.run', 'The campaign run standing, or nothing')
def run():
    """Return how far the run written down has got.

    What this answers is the question a player opens the launcher to ask
    -- which mission is next, and how much of the run is behind them. It
    reads and does not touch; playing one of those missions is its own
    action, and finishing one happens where the game is watched.
    """
    state = store.standing()
    if not state.get('seed'):
        return {'run': None}
    version = state.get('check_schema_version')
    if version is not None and int(version or 0) > CHECK_SCHEMA_VERSION:
        # A run written by a newer launcher. Drawing it from an older
        # reading of what a check is would show the wrong count against
        # every mission, and quietly.
        return {
            'run': None,
            'refused': 'This run was made by a newer launcher.',
        }
    installed = _missions_by_code()
    tiles = (
        progress.grid_states(state)
        if str(state.get(MODE_KEY) or '') == GRID_MODE else {}
    )
    listed = [
        _mission_view(state, code, installed, tiles)
        for code in progress.order(state)
    ]
    won = [mission for mission in listed if mission['complete']]
    goal = int(state.get('mission_goal') or len(listed) or 0)
    return {
        'run': {
            'seed': str(state.get('seed') or ''),
            'mode': str(state.get(MODE_KEY) or ''),
            # What the launcher is set to now, which is not always what
            # this run was made as: a mode can be changed after a run
            # exists, and the run keeps the order it was dealt.
            'standing_mode': str(_settings().get(MODE_KEY) or ''),
            'campaign': str(state.get('campaign_filter') or ''),
            'goal': goal,
            'won': len(won),
            'rewards': len(state.get('earned_rewards') or ()),
            'finished': bool(listed) and len(won) >= goal,
            'next': progress.next_code(state),
            'missions': listed,
        },
    }


# The three modes this generates for. Shop Mode deals a run through its
# own shelf and its own controller; refusing here is better than dealing
# it a campaign run that its screens would then have to explain.
CAMPAIGN_MODES = ('Classic', 'Mission List', 'Grid Mode')


def _refuse_if_archipelago(state, doing):
    """Refuse to touch a run an Archipelago server is playing along with.

    The classic window locks its own controls while a session is up. The
    mark is on the run rather than on that window, which is what makes it
    askable from here -- and the answer sends the player back there,
    because that is where a session is ended.
    """
    playing = (state or {}).get('archipelago')
    if isinstance(playing, dict) and str(
        playing.get('activation') or ''
    ).strip().lower() == 'active':
        raise ApiError(
            'This run is being played with Archipelago. Finish or '
            f'disconnect it in the classic window before {doing}.'
        )


@action('campaign.generate', 'Generate the run these settings describe',
        kind=COMMAND)
def generate():
    """Make a run from the settings as they stand, and keep it.

    This replaces whatever run was there. That is what generating has
    always meant -- there is one campaign run and a new one is a new one
    -- and it is why the screen asks before pressing rather than after.
    """
    from randomizer.campaign import generation, generator

    config = _settings()
    mode = str(config.get(MODE_KEY) or '')
    if mode not in CAMPAIGN_MODES:
        raise ApiError(f'{mode or "This mode"} does not generate a campaign run')
    _refuse_if_archipelago(store.standing(), 'generating another')
    missions = generator.installed_missions()
    if not missions:
        raise ApiError('No missions are installed to generate a run from')
    maker = generator.build(config, missions)
    try:
        options = generation.options_from(
            maker,
            generation.controls_from_config(config),
            missions=missions,
            reward_settings=maker.config_reward_settings(),
        )
        result = maker.build_seed_generation(options)
    except generation.GenerationRefused as refusal:
        raise ApiError(str(refusal)) from refusal
    generation.settle(result['state'], config)
    # A seed typed in is kept so the run can be played again; one made up
    # is not, or the next run would quietly be the same one.
    if not options['seed_was_explicit']:
        config['seed'] = ''
    _keep(config)
    return run()


@action('campaign.settings', 'How the next campaign run will be generated')
def settings():
    return _answer(_settings())


@action('campaign.catalogue', 'What one campaign setting may name')
def catalogue(name=''):
    """Return one named list, whole.

    Whole rather than searched, because a screen filters it as somebody
    types and the launcher is not the place to be asked once a letter.
    Which is why it is a reading of its own: the settings are read again
    after every change, and a few hundred entries have no business
    coming back with them.
    """
    wanted = str(name or '')
    if wanted not in CATALOGUE_NAMES:
        raise ApiError(f'There is no {wanted or "unnamed"} catalogue')
    return {
        'name': wanted,
        'entries': [
            dict(entry) for entry in campaign_catalogues.catalogue(wanted)
        ],
    }


@action('campaign.cameos', 'The pictures for some of what a list names')
def cameos(units=(), powers=()):
    """Return an icon for each thing asked about, as data a page can draw.

    Asked for in batches rather than with the list itself. The list is
    three hundred rows and the icons for all of them are a megabyte and a
    half; what a player is looking at is twenty of them. So the names
    come over once and the pictures follow the eye.

    A thing with no icon is simply absent from the answer. That is not an
    error and the screen already draws it: a row with a blank where the
    picture goes still says what it is.
    """
    wanted_units = _named(units)
    wanted_powers = _named(powers)
    if len(wanted_units) + len(wanted_powers) > MAX_CAMEO_BATCH:
        raise ApiError(
            f'Ask for at most {MAX_CAMEO_BATCH} pictures at a time'
        )
    from randomizer.ui.cameos import (
        ensure_superweapon_cameos,
        ensure_unit_cameos,
    )

    def drawn(found):
        pictures = {}
        for asset_id, path in (found or {}).items():
            uri = data_uri(path, ceiling=MAX_CAMEO_BYTES)
            if uri:
                pictures[str(asset_id)] = uri
        return pictures

    named, own_picture = _power_icons()
    # A power with a picture of its own is not looked for in the game's
    # art at all: it is not there, and asking would answer nothing.
    from randomizer.maps.assets import custom_sidebar_preview

    powers = {}
    for power in wanted_powers:
        image = own_picture.get(power)
        if not image:
            continue
        try:
            powers[power] = custom_sidebar_preview(image)
        except Exception:
            log_event('campaign_power_picture_unreadable', power=power)
    if wanted_powers:
        powers.update(ensure_superweapon_cameos(
            [power for power in wanted_powers if power not in powers],
            named,
            synchronous=True,
        ))
    return {
        'units': drawn(
            ensure_unit_cameos(wanted_units, synchronous=True)
            if wanted_units else {}
        ),
        'powers': drawn(powers),
    }


def _named(asked):
    """Return the ids asked about, once each and in the order given."""
    listed = []
    seen = set()
    for value in asked or ():
        name = str(value or '').strip().upper()
        if name and name not in seen:
            seen.add(name)
            listed.append(name)
    return listed


@action('campaign.use_setting', 'Change one campaign setting', kind=COMMAND)
def use_setting(name='', value=None):
    """Keep one campaign setting and answer with all of them."""
    config = _settings()
    CAMPAIGN.write(config, name, value)
    _keep(config)
    return _answer(config)



def _open_now(state, code):
    """Whether this run will let that mission be played right now.

    A board says so itself -- a tile it has not opened is locked however
    many missions have been won, which is the whole point of one -- and
    an ordered run says so by counting. A mission already finished is
    open either way: replaying one is allowed, and always has been.
    """
    if code in (state.get('completed_missions') or ()):
        return True
    if str(state.get(MODE_KEY) or '') == GRID_MODE:
        return progress.grid_states(state).get(code) in {
            'unlocked', 'completed',
        }
    return code in progress.unlocked_codes(state)


def _hook_for(mission, prepared):
    """Return what the watcher will read this mission by.

    Usually the map it just wrote, which has the objective markers in it.
    Sometimes that fails and the window launches anyway without automatic
    objective detection -- and the mission still has to be watched, or a
    game closed after an hour would leave a ticket nobody ever settles.
    So the mission is described either way, with no markers on it when
    there are none.
    """
    from randomizer.core.paths import DEBUG_LOG

    if isinstance(prepared, dict) and prepared.get('mission_code'):
        return prepared
    try:
        offset = DEBUG_LOG.stat().st_size if DEBUG_LOG.exists() else 0
    except OSError:
        offset = 0
    return {
        'mission_code': str(mission.get('code') or ''),
        'scenario': str(mission.get('scenario') or ''),
        'markers': {},
        'seen': set(),
        'completed_objective_checks': 0,
        'objective_events_seen': 0,
        'offset': offset,
    }


@action('campaign.launch', 'Play one mission of the run standing', kind=COMMAND)
def launch(code=''):
    """Write out one mission, open the game on it, and start watching.

    Everything that decides anything is the classic window's own code,
    run on a launcher with nothing drawn: which rules the mission gets,
    which rewards are already in hand, what the map is hooked with. What
    is different is only what happens after the game opens -- a window
    watches on a timer, and this leaves a ticket for whoever asks next.
    """
    from randomizer.campaign import generator
    from randomizer.core.paths import GAME_EXE, GAME_LAUNCHER_EXE

    from . import mission_session, session

    wanted = str(code or '').strip().upper()
    state = store.standing()
    if not state.get('seed'):
        raise ApiError('There is no run to play a mission of')
    if mission_session.running():
        raise ApiError('A mission is already being played')
    if session.running():
        raise ApiError('A skirmish battle is being played')
    _refuse_if_archipelago(state, 'playing a mission from here')
    if wanted not in progress.order(state):
        raise ApiError(f'{wanted or "That mission"} is not part of this run')
    if not _open_now(state, wanted):
        raise ApiError(
            f'{wanted} is locked. Finish more open missions to reach it.'
        )
    mission = _missions_by_code().get(wanted)
    if not mission or not mission.get('scenario'):
        raise ApiError(f'{wanted} is not installed here')
    missing = [
        path for path in (GAME_LAUNCHER_EXE, GAME_EXE) if not path.exists()
    ]
    if missing:
        raise ApiError(
            'The game is not where the launcher expects it: '
            + ', '.join(path.name for path in missing)
        )

    maker = generator.build(_settings(), generator.installed_missions(), state)
    prepared = maker.prepare_mission_launch_files(
        mission,
        None,
        maker.get_selected_difficulty_value(),
        maker.get_selected_game_speed_value(),
    )
    hook = _hook_for(mission, prepared)
    try:
        process, _command = maker.spawn_game_process()
    except OSError as exc:
        # Nothing is running, so nothing should be left behind written
        # out for it -- the same tidying the window does on this failure.
        maker.cleanup_generated_root_maps()
        maker.disable_generated_rules_for_client()
        raise ApiError(f'The game would not start: {exc}') from exc
    # In this order, and before the ticket: an attempt begins when the
    # game does, and a launcher that fell over between the two should
    # have written down the attempt rather than only the ticket.
    maker.remember_mission_started(mission)
    mission_session.start(hook, state.get('seed'), process)
    return {
        'code': wanted,
        'name': str(mission.get('title') or wanted),
        'markers': len(hook.get('markers') or {}),
        'watched': bool(hook.get('markers')),
    }


@action('campaign.session', 'What the mission being played is doing')
def playing():
    """Read what the game has said since the last ask.

    A read that writes, which is unusual here and deliberate: the game
    says an objective is done exactly once, in a line of its own log, and
    a reading that did not record it would be a reward lost. What it
    records is what the game already did.
    """
    from randomizer.campaign import generator

    from . import mission_session

    state = store.standing()
    if not state.get('seed'):
        return {'playing': False, 'finished': None}
    maker = generator.build(_settings(), generator.installed_missions(), state)
    return mission_session.poll(maker)


# What a dashboard entry can be, in the order a player reads them: what
# is in hand, what the next reward could be, what the run has locked
# behind something, and what this run was never going to offer.
UNLOCK_STANDINGS = ('unlocked', 'available', 'locked', 'unavailable')


def _unlock_picture(entry):
    """Return which picture stands for one thing on the dashboard."""
    reward = entry.get('reward') or {}
    if entry.get('kind') == 'unit':
        return {'unit': str(entry.get('id') or '').upper()}
    if entry.get('kind') == 'power':
        return {'power': str(
            reward.get('cameo_superweapon') or entry.get('id') or ''
        ).upper()}
    # A buff or a global is not a thing with art of its own: it is a
    # change to something else, and the something else is not one thing.
    return {}


@action('campaign.unlocks', 'Everything this run could hand over, and what it has')
def unlocks():
    """Return the run as a catalogue of what is in hand and what is not.

    The counts on the Run screen say how far a run has got; this says
    what it got. Both come off the same stored run, and the deciding is
    the classic window's own -- which reward a mission could pay, what a
    reward would unlock, whether the run can still reach it -- run on a
    launcher with nothing drawn.

    Everything is listed, including what this run will never offer.
    That is not noise: a seed that has left every Soviet aircraft out is
    a fact about the run, and a list showing only what is reachable
    cannot say it.
    """
    from randomizer.campaign import generator

    state = store.standing()
    if not state.get('seed'):
        return {'run': None, 'entries': [], 'factions': []}
    reading = generator.build(
        _settings(), generator.installed_missions(), state,
    )
    try:
        listed = reading.unlock_dashboard_entries()
    except Exception as exc:
        raise ApiError(f'This run cannot be read: {exc}') from exc
    entries = [
        {
            'key': str(entry.get('key') or ''),
            'id': str(entry.get('id') or ''),
            'label': str(entry.get('label') or entry.get('id') or ''),
            'kind': str(entry.get('kind') or ''),
            'faction': str(entry.get('faction') or 'Other'),
            'group': str(entry.get('category') or ''),
            'standing': str(entry.get('status') or ''),
            # Why it is where it is: which mission would pay for it, or
            # what the run would have to do first.
            'note': str(entry.get('condition') or ''),
            'cameo': _unlock_picture(entry),
        }
        for entry in listed
    ]
    factions = []
    for entry in entries:
        if entry['faction'] not in factions:
            factions.append(entry['faction'])
    return {
        'run': {
            'seed': str(state.get('seed') or ''),
            'mode': str(state.get(MODE_KEY) or ''),
            'earned': len(state.get('earned_rewards') or ()),
        },
        'factions': factions,
        'counts': {
            standing: sum(
                1 for entry in entries if entry['standing'] == standing
            )
            for standing in UNLOCK_STANDINGS
        },
        'entries': entries,
    }
