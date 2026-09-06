"""The Skirmish Shop mode, as plain data.

Every screen this mode has ever needed is here as one reading: a run, what
it is offered, what is on its shelf, and the board of runs that have
ended. Nothing in it knows what will draw it.
"""

from pathlib import Path

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import GAME_EXE, GAME_LAUNCHER_EXE
from randomizer.launch.game import (
    clear_generated_root_maps,
    clear_generated_rules,
    write_game_options,
)
from randomizer.skirmish.factions import country_by_index, skirmish_countries
from randomizer.skirmish.leaderboard import board_row, load_board, reached_text
from randomizer.skirmish.maps import map_by_relative_path
from randomizer.skirmish.progression import SKILL_NAMES, describe_offer
from randomizer.skirmish.shop import owned_stacks, shelf_for
from randomizer.skirmish.table import deal
from randomizer.skirmish.stats import stats_lines
from randomizer.skirmish.transitions import run_progress_text

from randomizer.ui.config import LOCKED_GAME_SPEED_VALUE

from . import session
from .contract import COMMAND, ApiError, action


# What a preview is allowed to weigh before it is not worth sending. The
# stock previews run to 300 KB and the median is 122 KB; three of those on
# every redraw is a quarter of a megabyte across the bridge for pictures
# that have not changed.
MAX_PREVIEW_BYTES = 512 * 1024


def _data_uri(path):
    """Return a picture the page can draw, as data rather than as a path.

    A page loaded from a file cannot open another file: the engine refuses
    it, and a refused picture looks exactly like a map that has none. So
    the bytes go across and the page caches them by map.
    """
    import base64

    if not path:
        return ''
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size > MAX_PREVIEW_BYTES:
            return ''
        raw = path.read_bytes()
    except OSError:
        return ''
    encoded = base64.b64encode(raw).decode('ascii')
    return f'data:image/png;base64,{encoded}'


# What a run is played at. The launcher locks both: a run whose pacing or
# difficulty can be changed between battles is not the run its rewards
# were tuned against.
LOCKED_DIFFICULTY = 1


def _country(index):
    country = country_by_index(index)
    return {
        'index': index,
        'id': country.country_id if country else '',
        'side': country.side if country else '',
        'label': country.label if country else str(index),
        'display': country.display if country else str(index),
    }


@action('skirmish.countries', 'Every country a run may be played as')
def countries():
    return [
        {
            'index': country.index,
            'id': country.country_id,
            'side': country.side,
            'label': country.label,
            'display': country.display,
        }
        for country in skirmish_countries()
    ]


def offer_view(offer, index):
    """One battle card, as a screen needs it."""
    entry = map_by_relative_path(offer.map_path)
    return {
        'index': index,
        'map_name': offer.map_name or offer.map_path,
        'map_path': offer.map_path,
        'installed': entry is not None,
        # Whether there is one to ask for. The picture itself is asked
        # for by map, once, rather than sent with every redraw.
        'has_preview': bool(entry is not None and entry.preview),
        'summary': describe_offer(offer),
        # Each enemy with how well it plays: a tier mixes them, so the
        # card has to be able to say two trained and one hardened.
        'enemies': [
            dict(_country(index), skill=SKILL_NAMES.get(handicap, ''))
            for index, handicap in zip(
                offer.enemy_countries, offer.enemy_handicaps()
            )
        ],
        'challenge': offer.challenge,
        'ally': offer.ally,
        'mental_ai': offer.mental_ai,
        'bonus_percent': offer.bonus_percent,
        'seats': offer.seats,
    }


def upgrade_view(upgrade, purchases):
    """One shelf card, with what the run has already done about it."""
    return {
        'unit': upgrade.unit,
        'buff_type': upgrade.buff_type,
        'key': f'{upgrade.unit}:{upgrade.buff_type}',
        'name': upgrade.name,
        'effect': upgrade.effect,
        'description': upgrade.description,
        'price': upgrade.price,
        'owned': bool(
            owned_stacks(purchases, upgrade.unit, upgrade.buff_type)
        ),
    }


def run_view(run, *, shelf=()):
    """A whole run, as one reading."""
    if run is None:
        return None
    return {
        'run_id': run.run_id,
        'seed': run.seed,
        'created': run.created,
        'status': run.status.value,
        'active': run.status.name == 'ACTIVE',
        'battle': run.battle,
        'tier': run.tier,
        'nightmare': run.nightmare,
        'warmup': run.warmup,
        'challenge_battle': run.challenge_battle,
        'progress': run_progress_text(run),
        'lives': run.lives,
        'lives_left': run.lives_left,
        'coins': run.coins,
        'ally_coins': run.ally_coins,
        'won_battles': run.won_battles,
        'player': _country(run.player_country),
        'ally': _country(run.ally_country),
        'purchases': [
            {'unit': item.unit, 'buff_type': item.buff_type,
             'stacks': item.stacks}
            for item in run.purchases
        ],
        'ally_purchases': [
            {'unit': item.unit, 'buff_type': item.buff_type,
             'stacks': item.stacks}
            for item in run.ally_purchases
        ],
        'offers': [
            offer_view(offer, index) for index, offer in enumerate(run.offers)
        ],
        'committed_offer': run.committed_offer,
        'shelf': [upgrade_view(item, run.purchases) for item in shelf],
        'stats': run.stats.to_dict(),
        'stat_lines': list(stats_lines(run.stats)),
    }


@action('skirmish.run', 'The run being played, or nothing')
def run(repository=None):
    from randomizer.skirmish.persistence import SkirmishRepository

    repository = repository or SkirmishRepository()
    current = repository.load_run()
    if current is None:
        return None
    country = country_by_index(current.player_country)
    shelf = (
        shelf_for(current, country.country_id)
        if country and not current.warmup else ()
    )
    return run_view(current, shelf=shelf)


@action('skirmish.runs', 'Every saved run, and which one is being played')
def runs(repository=None):
    from randomizer.skirmish.persistence import SkirmishRepository

    repository = repository or SkirmishRepository()
    stored, active = repository.list_runs()
    return {
        'active': active,
        'runs': [run_view(item) for item in stored],
    }


@action('skirmish.board', 'Runs that have ended, furthest first')
def board():
    return [
        {
            'run_id': entry.run_id,
            'seed': entry.seed,
            'reached': reached_text(entry),
            'outcome': entry.outcome,
            'army': entry.army,
            'ally': entry.ally,
            'ended': entry.ended,
            'row': list(board_row(entry)),
            'stats': entry.stats.to_dict(),
            'stat_lines': list(stats_lines(entry.stats)),
        }
        for entry in load_board()
    ]


@action('skirmish.preview', "One map's picture, as data a page can draw")
def preview(map_path=''):
    entry = map_by_relative_path(str(map_path))
    if entry is None:
        return {'map_path': map_path, 'uri': ''}
    return {'map_path': map_path, 'uri': _data_uri(entry.preview)}


@action('skirmish.tiers', 'What each tier of a run is made of')
def tiers():
    from randomizer.skirmish.progression import (
        BONUSES,
        SKILL_NAMES,
        TIERS,
        WARMUP,
        offer_bonuses,
    )

    def described(tier, number):
        return {
            'tier': number,
            'enemies': [SKILL_NAMES.get(item, '') for item in tier.enemies],
            'challenge': SKILL_NAMES.get(tier.challenge, ''),
            'mental_ai': tier.mental,
            'challenge_mental_ai': tier.challenge_mental,
        }

    return {
        'warmup': described(WARMUP, 0),
        'tiers': [
            described(tier, number)
            for number, tier in enumerate(TIERS, 1)
        ],
        'bonuses': [
            {
                'label': bonus.label,
                'percent': bonus.percent,
                'extra_enemies': bonus.extra_enemies,
                'alone': bonus.alone,
                'mental_ai': bonus.mental,
            }
            for bonus in offer_bonuses(1)
        ],
        'plain_bonus_count': len(BONUSES),
    }


@action('skirmish.start', 'Begin a new run as one army, allied with another',
        kind=COMMAND)
def start(player=0, ally=3):
    """Start a run and deal its warmup, and make it the run being played.

    The run that was being played is not thrown away -- it stays in the
    list, and can be resumed. What changes is which one the screens are
    looking at.
    """
    from datetime import date
    from uuid import uuid4

    from randomizer.skirmish.transitions import (
        SkirmishTransitionError,
        start_run,
    )

    if session.running():
        raise ApiError('Wait for the running game to close')
    chosen = country_by_index(int(player))
    beside = country_by_index(int(ally))
    if chosen is None or beside is None:
        raise ApiError('Choose an army and an ally')
    try:
        run = deal(start_run(
            run_id=uuid4().hex,
            seed=uuid4().hex[:12].upper(),
            player_country=chosen.index,
            ally_country=beside.index,
            created=date.today().isoformat(),
            # So the ally is not empty-handed in the opening battle: it
            # shops out of what a victory pays, and at the start nothing
            # has been won.
            ally_roster=beside.country_id,
        ))
    except SkirmishTransitionError as exc:
        raise ApiError(str(exc)) from exc
    saved = _repository().save_run(run)
    log_event(
        'skirmish_run_started',
        run_id=saved.run_id,
        seed=saved.seed,
        player_country=chosen.country_id,
        ally_country=beside.country_id,
    )
    return {
        'run_id': saved.run_id,
        'seed': saved.seed,
        'army': chosen.display,
        'ally': beside.display,
    }


@action('skirmish.resume', 'Play a stored run instead of the current one',
        kind=COMMAND)
def resume(run_id=''):
    from randomizer.skirmish.persistence import SkirmishPersistenceError

    if session.running():
        raise ApiError('Wait for the running game to close')
    try:
        run = _repository().select_run(str(run_id))
    except SkirmishPersistenceError as exc:
        raise ApiError(str(exc)) from exc
    return {'run_id': run.run_id, 'seed': run.seed, 'battle': run.battle}


@action('skirmish.delete', 'Forget a stored run', kind=COMMAND)
def delete(run_id=''):
    """Delete one run. What it did is on the board if it ended there.

    Deleting the run being played leaves none being played, which the
    screens say rather than hide.
    """
    from randomizer.skirmish.persistence import SkirmishPersistenceError

    if session.running():
        raise ApiError('Wait for the running game to close')
    repository = _repository()
    stored, _active = repository.list_runs()
    gone = next(
        (item for item in stored if item.run_id == str(run_id)), None
    )
    if gone is None:
        raise ApiError('No such run')
    try:
        repository.delete_run(gone.run_id)
    except SkirmishPersistenceError as exc:
        raise ApiError(str(exc)) from exc
    return {'run_id': gone.run_id, 'seed': gone.seed}


def _repository():
    from randomizer.skirmish.persistence import SkirmishRepository

    return SkirmishRepository()


def _playing(repository):
    """Return the run being played, or say there is not one."""
    current = repository.load_run()
    if current is None:
        raise ApiError('There is no run to play')
    return current


@action(
    'skirmish.buy',
    "Spend Ore on one upgrade from this battle's shelf",
    kind=COMMAND,
)
def buy(key=''):
    from randomizer.skirmish.transitions import (
        SkirmishTransitionError,
        buy_upgrade,
    )

    repository = _repository()
    current = _playing(repository)
    country = country_by_index(current.player_country)
    if country is None:
        raise ApiError('This run plays a country the rules no longer have')
    wanted = str(key)
    upgrade = next(
        (
            item for item in shelf_for(current, country.country_id)
            if f'{item.unit}:{item.buff_type}' == wanted
        ),
        None,
    )
    if upgrade is None:
        raise ApiError('That upgrade is not on this battle\'s shelf')
    try:
        saved = repository.save_run(buy_upgrade(current, upgrade))
    except SkirmishTransitionError as exc:
        raise ApiError(str(exc)) from exc
    return {'bought': upgrade.name, 'coins': saved.coins}


@action('skirmish.skip_warmup', 'Step past the warmup without fighting it', kind=COMMAND)
def skip_the_warmup():
    from randomizer.skirmish.transitions import (
        SkirmishTransitionError,
        skip_warmup,
    )

    repository = _repository()
    current = _playing(repository)
    try:
        # Stepping past the warmup clears its table, so the battle behind
        # it is dealt in the same breath.
        saved = repository.save_run(deal(skip_warmup(current)))
    except SkirmishTransitionError as exc:
        raise ApiError(str(exc)) from exc
    return {'battle': saved.battle, 'offers': len(saved.offers)}


@action('skirmish.give_up', 'End the run being played', kind=COMMAND)
def give_up_run():
    from randomizer.skirmish.leaderboard import record_finished_run
    from randomizer.skirmish.transitions import give_up

    repository = _repository()
    current = _playing(repository)
    if session.running():
        raise ApiError('Wait for the running game to close')
    saved = repository.save_run(give_up(current))
    # A run that ends goes on the board, whatever ended it.
    recorded = True
    try:
        record_finished_run(saved, 'Gave up')
    except OSError:
        recorded = False
    return {'status': saved.status.value, 'recorded': recorded}


@action(
    'skirmish.deal',
    "Draw this battle's offers, if none stand",
    kind=COMMAND,
)
def deal_table():
    """Set the table a screen is about to read.

    Reading is not allowed to write, so a screen that finds no offers asks
    for them. Asking twice into one battle changes nothing: a table that
    already stands is left alone.
    """
    from randomizer.skirmish.transitions import SkirmishTransitionError

    repository = _repository()
    current = _playing(repository)
    if current.offers:
        return {'battle': current.battle, 'offers': len(current.offers),
                'dealt': False}
    try:
        saved = repository.save_run(deal(current))
    except SkirmishTransitionError as exc:
        raise ApiError(str(exc)) from exc
    return {'battle': saved.battle, 'offers': len(saved.offers), 'dealt': True}


@action(
    'skirmish.launch',
    'Start the battle behind one of the offers',
    kind=COMMAND,
)
def launch(index=0):
    """Commit to one offer, write the files, and start the game.

    Committing is what a launch does and it is final: a battle scouted and
    put back is a battle chosen twice.
    """
    from randomizer.skirmish.launch import build_battle, prepare_battle
    from randomizer.skirmish.transitions import (
        SkirmishTransitionError,
        commit_offer,
    )

    repository = _repository()
    # A battle that finished while nobody was watching -- the launcher
    # closed, or closed and opened again -- is settled before another one
    # starts. Nothing is being played by then, so nothing above would have
    # refused, and starting would write the new battle over the old one's
    # ticket: a battle fought and never charged for.
    settled = session.poll(repository)
    if (settled.get('finished') or {}).get('recorded'):
        raise ApiError(
            'The battle before this one had just finished. It is recorded '
            'now, and the table has changed.'
        )
    current = _playing(repository)
    if session.running():
        raise ApiError('A battle is already being played')
    try:
        current = commit_offer(current, int(index))
    except (SkirmishTransitionError, TypeError, ValueError) as exc:
        raise ApiError(str(exc)) from exc
    offer = current.committed()
    entry = map_by_relative_path(offer.map_path)
    if entry is None:
        raise ApiError(f'{offer.map_name} is not installed any more')
    for path in (GAME_LAUNCHER_EXE, GAME_EXE):
        if not path.exists():
            raise ApiError(f'The game is missing {path.name}')

    saved = repository.save_run(current)
    try:
        battle = build_battle(
            saved, offer, entry,
            difficulty=LOCKED_DIFFICULTY,
            game_speed=LOCKED_GAME_SPEED_VALUE,
        )
    except LookupError as exc:
        raise ApiError(str(exc)) from exc
    prepare_battle(
        battle,
        # The launcher's own two steps around a battle: a ruleset it
        # generated for a campaign mission would otherwise still be sitting
        # in the game folder for the client to load, and the game's own
        # option file has to be told the pace this run is played at.
        before=lambda: (clear_generated_rules(), clear_generated_root_maps()),
        after=lambda: write_game_options(
            battle['difficulty'], battle['game_speed']
        ),
    )
    session.start(battle)
    return {
        'map_name': entry.name,
        'battle': saved.battle,
        'houses': len(battle['houses']),
    }


@action('skirmish.session', 'Whether a battle is being played, and how it ended')
def battle_session():
    """Read the game the launcher started, and record it once it has ended.

    A screen asks this on a timer. While the game is up it says so; the
    first read after it closes is the one that reads the score block and
    writes the outcome into the run.

    So this is the one reading that writes, and it is deliberate: a screen
    polls it, and a poll that had to be a command would mean every screen
    asking permission to notice the game had closed. It writes nothing
    unless the launcher itself started a game, which is why the self-check
    -- where nothing has -- can call it as safely as any other reading.
    """
    return session.poll(_repository())


@action('skirmish.upgrades', "Everything one country's shelf can ever hold")
def upgrades(country=''):
    from randomizer.skirmish.shop import country_upgrades

    if not country:
        raise ApiError('Which country the shelf is for was not said')
    return [upgrade_view(item, ()) for item in country_upgrades(country)]
