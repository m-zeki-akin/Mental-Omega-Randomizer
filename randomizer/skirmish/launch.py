"""Putting one battle where the game will find it.

Everything a launch writes, in the order it has to be written, with no
window anywhere in it. The order is not arrangement -- each step reads what
the one before it left:

1. the map is copied into place, because everything after edits it;
2. the game options are merged, and a challenge's forced options are read
   first so the flag and the file it stands for can never disagree;
3. the speed table, so the slider in the in-game menu means nothing;
4. a challenge's own map code, last of the three, so it outranks them;
5. the seat, which reads the map's ownership as it now stands -- a
   ``ForbiddenHouses`` written by a house's copies would otherwise be read
   as the unit's own and extended to the seat;
6. the spawn file, naming the seat rather than the country it stands for;
7. the player's copies, then the ally's, each reading what the other left;
8. the AI file, if any house has anything to build.

The two callables are the parts that belong to the launcher rather than to
a battle -- clearing a generated ruleset the client would otherwise load,
and writing the difficulty into the game's own options file. They are
passed in so that this module needs nothing from a window.
"""

import shutil

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import GAME_ROOT, SPAWN_INI

from .ai import ai_house_code, remove_staged_ai_file, side_number, stage_ai_file
from .challenges import (
    challenge_mode_for_level,
    forced_options,
    map_code_path,
    merge_map_code,
)
from .clones import apply_house_clones
from .factions import country_by_index, skirmish_countries
from .options import merge_game_options
from .seats import apply_seat
from .spawn import match_settings, skirmish_spawn_ini_text, write_skirmish_spawn_ini
from .speed import apply_locked_speed


SPAWN_MAP_INI = GAME_ROOT / 'spawnmap.ini'
# What a player's private copy of a unit is called, and what a computer
# player's is. Distinct so two houses' copies of the same unit never answer
# to one ID.
PLAYER_CLONE_PREFIX = 'MOP'
ALLY_CLONE_PREFIX = 'MOL'


# The player's house takes the first colour and every other house the
# next, so no two share one.
HOUSE_COLORS = (0, 2, 4, 6, 8, 10, 12, 14)
# The player's house is named in the spawn file and named again in the
# score block the game writes at the end, which is how the launcher finds
# its own result among the houses.
PLAYER_NAME = 'Commander'


def houses_for(run, offer):
    """Return the computer players, ally first, in seating order."""
    from .challenges import challenge_for
    from .progression import ALLY_DIFFICULTY
    from .spawn import SkirmishHouse

    described = challenge_for(offer.map_path) if offer.challenge else None
    if described is not None and described.houses:
        # A challenge is the map's fight: its armies, its colours, its
        # starting points, and nobody standing beside the player.
        return tuple(
            SkirmishHouse(
                country=house.country,
                color=house.color,
                friendly=False,
                handicap=offer.handicap,
            )
            for house in described.houses
        )
    houses = []
    if offer.ally:
        houses.append(SkirmishHouse(
            country=run.ally_country,
            color=HOUSE_COLORS[1],
            friendly=True,
            # Not the tier's difficulty. An ally on Easy builds a base and
            # stands in it; what a run is fought against is the dial, not
            # who it is fought beside.
            handicap=ALLY_DIFFICULTY,
        ))
    for country, handicap in zip(offer.enemy_countries, offer.enemy_handicaps()):
        houses.append(SkirmishHouse(
            country=country,
            color=HOUSE_COLORS[len(houses) + 1],
            friendly=False,
            handicap=handicap,
        ))
    return tuple(houses)


def build_battle(run, offer, entry, *, difficulty, game_speed):
    """Return everything one battle needs, ready to be written.

    A reading, not a change: nothing here touches a file. What it decides
    is the line-up, the colours, and the seat -- a country nobody else in
    this battle plays, wearing the country the player chose.
    """
    from .challenges import challenge_for
    from .seats import pick_seat

    player = country_by_index(run.player_country)
    if player is None:
        raise LookupError(
            'This run plays a country the installed rules no longer have'
        )
    described = challenge_for(offer.map_path) if offer.challenge else None
    houses = houses_for(run, offer)
    countries = skirmish_countries()
    in_play = [
        country.country_id for country in (
            country_by_index(house.country) for house in houses
        ) if country is not None
    ]
    return {
        'run_id': run.run_id,
        'battle': run.battle,
        'offer': offer,
        'challenge': described,
        'map': entry,
        'player': player,
        # A challenge names a colour its own armies wear, and the client
        # keeps the player out of it.
        'player_color': next(
            color for color in HOUSE_COLORS
            if described is None or color not in described.disallowed_colors
        ),
        'houses': houses,
        'seat': pick_seat(
            player.country_id,
            in_play,
            [country.country_id for country in countries],
            sides={
                country.country_id: country.side for country in countries
            },
            salt=f'{run.seed}:{run.battle}:seat',
        ),
        'seed': offer.seed,
        'player_name': PLAYER_NAME,
        'purchases': run.purchases,
        'ally_purchases': run.ally_purchases,
        'ally': next(
            (
                country_by_index(house.country) for house in houses
                if house.friendly
            ),
            None,
        ),
        'difficulty': difficulty,
        'game_speed': game_speed,
    }


def _seat_index(seat, fallback):
    for country in skirmish_countries():
        if country.country_id == seat:
            return country.index
    return fallback


def prepare_battle(battle, *, before=None, after=None):
    """Write everything one battle needs, and say what was written.

    ``before`` is run first and ``after`` last: the launcher's own two
    steps, which have nothing to do with which battle this is.
    """
    if before is not None:
        before()

    entry = battle['map']
    offer = battle['offer']
    described = battle['challenge']
    shutil.copy2(entry.path, SPAWN_MAP_INI)

    options = {'GameSpeed': str(battle['game_speed'])}
    game_mode = 'Standard'
    starts = None
    if offer.mental_ai:
        # The late tiers are fought against the boosted AI, and so are the
        # battles that offer it as the price of a bonus.
        options['MentalAI'] = 'True'
    if described is not None:
        game_mode = challenge_mode_for_level(offer.handicap)
        options.update(forced_options(
            f'{game_mode}ForcedOptions', described.forced_options
        ))
        starts = {1: 0}
        for index, house in enumerate(described.houses):
            starts[index + 2] = house.start

    merge_game_options(SPAWN_MAP_INI, match_settings(options))
    apply_locked_speed(SPAWN_MAP_INI, battle['game_speed'])
    if described is not None:
        code = map_code_path(game_mode)
        if code is not None:
            merge_map_code(SPAWN_MAP_INI, code)

    apply_seat(SPAWN_MAP_INI, battle['player'].country_id, battle['seat'])
    write_skirmish_spawn_ini(
        SPAWN_INI,
        skirmish_spawn_ini_text(
            map_name=entry.name,
            player_name=battle['player_name'],
            player_country=_seat_index(battle['seat'], battle['player'].index),
            player_color=battle['player_color'],
            houses=battle['houses'],
            seed=battle['seed'],
            game_mode=game_mode,
            starts=starts,
            options=options,
        ),
    )

    built = apply_house_clones(
        SPAWN_MAP_INI,
        battle['purchases'],
        battle['seat'],
        prefix=PLAYER_CLONE_PREFIX,
        roster=battle['player'].country_id,
    )
    ai_units = prepare_ai(battle)

    if after is not None:
        after()
    log_event(
        'skirmish_battle_prepared',
        map=entry.path.name,
        game_mode=game_mode,
        seat=battle['seat'],
        player_clones=len(built),
        ally_clones=len(ai_units),
    )
    return {
        'game_mode': game_mode,
        'player_clones': built,
        'ally_clones': ai_units,
    }


def prepare_ai(battle):
    """Give the computer players their copies, and the wish to build them.

    A human builds what the sidebar offers, so a copy gated to their seat
    is the whole of it. A computer player builds what its task forces name,
    so the copies are useless until those name them.
    """
    remove_staged_ai_file()
    ally = battle.get('ally')
    purchases = battle.get('ally_purchases') or ()
    clones = {}
    if ally is not None and purchases:
        clones = apply_house_clones(
            SPAWN_MAP_INI,
            purchases,
            ally.country_id,
            prefix=ALLY_CLONE_PREFIX,
            # The original stays available: shutting it out left the AI
            # unable to fill any autocreate team that named it, and a team
            # carries no owner, so there is no standing one down for a
            # single house.
            forbid_source=False,
        )
    houses = []
    for house in battle['houses']:
        country = country_by_index(house.country)
        if country is None:
            continue
        houses.append((
            country.country_id,
            side_number(country.side_id),
            clones if ally is not None and country.index == ally.index else {},
        ))
    if houses and clones:
        stage_ai_file(ai_house_code(houses))
    return clones
