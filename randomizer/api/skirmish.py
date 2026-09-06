"""The Skirmish Shop mode, as plain data.

Every screen this mode has ever needed is here as one reading: a run, what
it is offered, what is on its shelf, and the board of runs that have
ended. Nothing in it knows what will draw it.
"""

from pathlib import Path

from randomizer.skirmish.factions import country_by_index, skirmish_countries
from randomizer.skirmish.leaderboard import board_row, load_board, reached_text
from randomizer.skirmish.maps import map_by_relative_path
from randomizer.skirmish.progression import SKILL_NAMES, describe_offer
from randomizer.skirmish.shop import owned_stacks, shelf_for
from randomizer.skirmish.stats import stats_lines
from randomizer.skirmish.transitions import run_progress_text

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
        saved = repository.save_run(skip_warmup(current))
    except SkirmishTransitionError as exc:
        raise ApiError(str(exc)) from exc
    return {'battle': saved.battle}


@action('skirmish.give_up', 'End the run being played', kind=COMMAND)
def give_up_run():
    from randomizer.skirmish.transitions import give_up

    repository = _repository()
    current = _playing(repository)
    saved = repository.save_run(give_up(current))
    return {'status': saved.status.value}


@action('skirmish.launch', 'Start the battle behind one of the offers', kind=COMMAND)
def launch(index=0):
    # Copying the map, writing the spawn file and starting the process
    # still live in the window's own controller. Until that moves across,
    # saying so is better than a button that does nothing.
    raise ApiError(
        'Launching a battle is still wired to the old window. '
        f'Offer {index} was not started.'
    )


@action('skirmish.upgrades', "Everything one country's shelf can ever hold")
def upgrades(country=''):
    from randomizer.skirmish.shop import country_upgrades

    if not country:
        raise ApiError('Which country the shelf is for was not said')
    return [upgrade_view(item, ()) for item in country_upgrades(country)]
