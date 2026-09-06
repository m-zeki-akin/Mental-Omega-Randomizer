"""Setting a battle's table: what it is offered, and who it is fought against.

A battle's offers are drawn once and kept. Everything that ends a battle
clears them -- a victory, a skipped warmup, the walk into Nightmare -- and
whatever comes next has to deal a new table before there is anything to
choose from. That was a window's job for as long as there was only one, and
a screen that could not deal had no way past its first battle.

So it lives here, beside the rule that decides who may be fought, because
the two are one decision: a table dealt without that rule is a table that
can seat the ally's own country as the enemy.
"""

from .factions import country_by_index, skirmish_countries
from .maps import MAPS_DIR, challenge_map_pool, skirmish_map_pool
from .progression import offers_for
from .shop import draw_shelf
from .transitions import SkirmishTransitionError, offer_battles


def enemy_pool(run):
    """Return the countries a battle may be fought against.

    Every installed country but the ally's own. What keeps a run's
    upgrades out of enemy hands is not which side they fight for: the
    player is seated on a country nobody else plays, and both armies'
    upgraded units are copies gated to a country. So Allies against
    Allies is a battle this mode can offer again -- but not against the
    very country standing beside the player, whose copies an enemy of
    that country would be handed.
    """
    ally = country_by_index(run.ally_country)
    countries = skirmish_countries()
    if ally is None:
        return countries
    eligible = tuple(
        country for country in countries if country.index != ally.index
    )
    return eligible or countries


def deal(run):
    """Put this battle's offers on the table, drawing them if needed.

    Returns the run unchanged when a table already stands. Dealing twice
    into the same battle would redraw what the player is looking at.
    """
    if run is None or run.offers:
        return run
    offers = offers_for(
        run,
        skirmish_map_pool(),
        challenge_map_pool(),
        MAPS_DIR,
        enemy_pool(run),
    )
    if not offers:
        raise SkirmishTransitionError(
            'No installed map can seat this battle. Check that '
            'MapsMO/Standard and MapsMO/Challenge are present.'
        )
    country = country_by_index(run.player_country)
    # The shop's six are this battle's offers too, drawn once here so
    # that buying one does not redraw the other five.
    return offer_battles(
        run,
        offers,
        shelf=draw_shelf(run, country.country_id) if country else (),
    )
