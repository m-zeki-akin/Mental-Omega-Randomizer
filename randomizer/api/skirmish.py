"""The Skirmish Shop mode, as plain data.

Every screen this mode has ever needed is here as one reading: a run, what
it is offered, what is on its shelf, and the board of runs that have
ended. Nothing in it knows what will draw it.
"""

from randomizer.skirmish.factions import country_by_index, skirmish_countries
from randomizer.skirmish.leaderboard import board_row, load_board, reached_text
from randomizer.skirmish.maps import map_by_relative_path
from randomizer.skirmish.progression import describe_offer
from randomizer.skirmish.shop import owned_stacks, shelf_for
from randomizer.skirmish.stats import stats_lines
from randomizer.skirmish.transitions import run_progress_text

from .contract import ApiError, action


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
        'preview': str(entry.preview) if entry and entry.preview else '',
        'summary': describe_offer(offer),
        'enemies': [_country(index) for index in offer.enemy_countries],
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


@action('skirmish.upgrades', "Everything one country's shelf can ever hold")
def upgrades(country=''):
    from randomizer.skirmish.shop import country_upgrades

    if not country:
        raise ApiError('Which country the shelf is for was not said')
    return [upgrade_view(item, ()) for item in country_upgrades(country)]
