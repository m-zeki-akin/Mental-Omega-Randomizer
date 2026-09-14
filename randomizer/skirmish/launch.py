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
7. the player's copies, then the ally's, then each armed enemy's, every
   one reading what the ones before it left;
8. the AI file, if any house has anything to build.

The two callables are the parts that belong to the launcher rather than to
a battle -- clearing a generated ruleset the client would otherwise load,
and writing the difficulty into the game's own options file. They are
passed in so that this module needs nothing from a window.
"""

from dataclasses import replace
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
from .colors import UNCHOSEN, color_ids, house_colors, is_a_color
from .flag import stage_seat_flags
from .factions import country_by_index, skirmish_countries
from .options import merge_game_options
from .powers import apply_power_clones, superweapon_ids
from .seats import apply_seat
from .spawn import (
    match_settings,
    skirmish_spawn_ini_text,
    spread_starts,
    write_skirmish_spawn_ini,
)
from .speed import apply_locked_speed


SPAWN_MAP_INI = GAME_ROOT / 'spawnmap.ini'
# What a player's private copy of a unit is called, and what a computer
# player's is. Distinct so two houses' copies of the same unit never answer
# to one ID.
PLAYER_CLONE_PREFIX = 'MOP'
ALLY_CLONE_PREFIX = 'MOL'
ENEMY_CLONE_PREFIX = 'MOE'
# A unit handed over rather than improved: the player's prototype, and
# what an enemy that has infiltrated somebody fields.
GRANT_CLONE_PREFIX = 'MOG'
# And what a computer player's own copy of a power is called, so it can
# never answer to the same id as the player's.
ENEMY_POWER_PREFIX = 'MOX'


# What the player wears when they have not said, and what everyone wears
# when the installation's colour table cannot be read at all: the first
# colour for the player and one of the others for each computer player.
DEFAULT_PLAYER_COLOR = 0
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
        # A challenge is the map's fight: its armies, its colours and its
        # starting points, all kept. What the run adds is the ally, in the
        # co-op partner's seat and wearing a colour none of them wear.
        scripted = tuple(
            SkirmishHouse(
                country=house.country,
                color=house.color,
                friendly=False,
                handicap=offer.handicap,
            )
            for house in described.houses
        )
        if not offer.ally:
            return scripted
        return (SkirmishHouse(
            country=run.ally_country,
            color=challenge_ally_color(run, described, scripted),
            friendly=True,
            # The dial is what the run is fought against, not who it is
            # fought beside -- the same reason an ordinary battle's ally
            # ignores the tier.
            handicap=ALLY_DIFFICULTY,
        ),) + scripted
    houses = []
    if offer.ally:
        houses.append(SkirmishHouse(
            country=run.ally_country,
            color=0,
            friendly=True,
            # Not the tier's difficulty. An ally on Easy builds a base and
            # stands in it; what a run is fought against is the dial, not
            # who it is fought beside.
            handicap=ALLY_DIFFICULTY,
        ))
    for country, handicap in zip(offer.enemy_countries, offer.enemy_handicaps()):
        houses.append(SkirmishHouse(
            country=country,
            color=0,
            friendly=False,
            handicap=handicap,
        ))
    # The colours are handed out once the line-up is known, so that none of
    # them is the player's and no two are each other's.
    wearing = house_colors(
        player=player_color(run, described),
        taken=described.disallowed_colors if described is not None else (),
        # Allies first, then enemies -- the order the line-up was built in
        # above, so the colours land on the houses they were chosen for.
        friends=sum(1 for house in houses if house.friendly),
        foes=sum(1 for house in houses if not house.friendly),
    )
    return tuple(
        replace(house, color=color) for house, color in zip(houses, wearing)
    )


def challenge_ally_color(run, described, scripted):
    """The colour the ally wears beside a challenge's own armies.

    Nearest the player's, the way an ally is told apart everywhere else,
    but never one the map forbids and never one its scripted armies already
    wear -- the client dresses all three of them in the same colour, and an
    ally in it would read as a fourth.
    """
    return house_colors(
        player=player_color(run, described),
        taken=tuple(described.disallowed_colors)
        + tuple(house.color for house in scripted),
        friends=1,
    )[0]


def challenge_starts(described, spawn_count, with_ally):
    """Return ``{seat: start}`` for a challenge: player, ally, then armies.

    The scripted armies keep the starting points the fight was designed
    around, and the player keeps the first. The ally takes the seat the map
    holds for a second human -- on the stock challenges the second start,
    asked for rather than assumed, so a submod that placed its armies
    differently still seats everybody somewhere of their own.
    """
    starts = {1: 0}
    seat = 2
    if with_ally:
        standing = {0} | {house.start for house in described.houses}
        starts[seat] = next(
            (
                one for one in range(max(int(spawn_count), 2))
                if one not in standing
            ),
            1,
        )
        seat += 1
    for house in described.houses:
        starts[seat] = house.start
        seat += 1
    return starts


def player_color(run, described=None):
    """Return the colour the player's army wears in this battle.

    Their own choice, unless the map has spoken: a challenge names the
    colours its armies wear, and the client keeps the player out of those.
    """
    disallowed = set(
        described.disallowed_colors if described is not None else ()
    )
    chosen = int(getattr(run, 'player_color', UNCHOSEN))
    if is_a_color(chosen) and chosen not in disallowed:
        return chosen
    return next(
        (number for number in color_ids() if number not in disallowed),
        DEFAULT_PLAYER_COLOR,
    )


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
        'player_color': player_color(run, described),
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
        starts = challenge_starts(described, len(entry.spawns), offer.ally)
    else:
        # An ordinary map places its own line-up, keeping the enemies off
        # the player's doorstep. A challenge is placed by its script above.
        starts = spread_starts(entry.spawns, battle['houses'])

    merge_game_options(SPAWN_MAP_INI, match_settings(options))
    apply_locked_speed(SPAWN_MAP_INI, battle['game_speed'])
    if described is not None:
        code = map_code_path(game_mode)
        if code is not None:
            merge_map_code(SPAWN_MAP_INI, code)

    apply_seat(SPAWN_MAP_INI, battle['player'].country_id, battle['seat'])
    # The map now names the chosen country's flag on the seat, but the
    # engine loaded the seat's picture at startup by the name the rules
    # gave it. The picture behind that name is swapped instead.
    stage_seat_flags(battle['player'].country_id, battle['seat'])
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

    # A superweapon is not a TechnoType and the unit machinery would make
    # nonsense of one, so the two kinds of purchase are separated before
    # either is written.
    powers = superweapon_ids()
    bought_units = tuple(
        one for one in battle['purchases'] if one.unit not in powers
    )
    bought_powers = tuple(
        one for one in battle['purchases'] if one.unit in powers
    )
    built = apply_house_clones(
        SPAWN_MAP_INI,
        bought_units,
        battle['seat'],
        prefix=PLAYER_CLONE_PREFIX,
        roster=battle['player'].country_id,
    )
    # The player's own copies of the powers they bought upgrades for,
    # granted by the same building and taken away from nobody else.
    powered = apply_power_clones(
        SPAWN_MAP_INI, bought_powers, battle['seat'],
    )
    # The prototype, if this battle hands one over. Its own call because
    # it is the one copy written without the gate it is named for: the
    # upgrades above keep theirs, so a run that has bought stolen-tech
    # upgrades still has to infiltrate for those.
    granted = {}
    if offer.player_stolen:
        granted = apply_house_clones(
            SPAWN_MAP_INI,
            (),
            battle['seat'],
            prefix=GRANT_CLONE_PREFIX,
            roster=battle['player'].country_id,
            forbid_source=False,
            gated=False,
            grant=(offer.player_stolen,),
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
        player_powers=len(powered),
        player_granted=len(granted),
        ally_clones=len(ai_units),
    )
    return {
        'game_mode': game_mode,
        'player_clones': built,
        'player_granted': granted,
        'ally_clones': ai_units,
    }


def enemy_purchases(offer):
    """Return what each enemy country was handed, by that country.

    The offer stores one set per enemy, but a copy is gated to a country
    rather than to a house, so two enemies playing the same country are
    one army as far as the rules are concerned. Their sets are put
    together rather than written twice.
    """
    from .model import UpgradePurchase
    from .progression import faction_units

    by_country = {}
    for index, bought in zip(offer.enemy_countries, offer.enemy_bought()):
        country = country_by_index(index)
        if country is None or not bought:
            continue
        for key in bought:
            unit, _, buff_type = str(key).partition(':')
            if not unit or not buff_type:
                continue
            by_country.setdefault(country.country_id, {})[key] = (
                UpgradePurchase(unit.upper(), buff_type, 1)
            )
    # And the army-wide ones, which name a stat and no unit: every unit
    # the country's shelf sells that stat for is bought up in it. Two
    # enemies playing one country share the copies either way, so the
    # stats are merged before they are spread across the units.
    for index, stats in zip(
        offer.enemy_countries, offer.enemy_faction_bought()
    ):
        country = country_by_index(index)
        if country is None or not stats:
            continue
        for buff_type in stats:
            for unit in faction_units(country.country_id, buff_type):
                by_country.setdefault(country.country_id, {})[
                    f'{unit}:{buff_type}'
                ] = UpgradePurchase(unit.upper(), buff_type, 1)
    return {
        country: tuple(bought.values())
        for country, bought in by_country.items()
    }


def ai_houses(battle, ally_clones, enemy_clones):
    """Return every computer player with the copies it is to build.

    The ally builds what it bought; an enemy builds what the offer handed
    the country it is playing. A house the installed rules no longer have
    is left out rather than named to the AI file as a country that is not
    there.

    Which side a house is on is the house's own answer, not its country's.
    An ordinary battle never seats the ally's country as an enemy, but a
    challenge's armies are the map's and the ally is the player's, so the
    two can meet -- and a copy the ally paid for is not something to hand
    the army it is fighting.
    """
    houses = []
    for house in battle['houses']:
        country = country_by_index(house.country)
        if country is None:
            continue
        houses.append((
            country.country_id,
            side_number(country.side_id),
            dict(ally_clones) if house.friendly
            else dict(enemy_clones.get(country.country_id) or {}),
        ))
    return houses


def prepare_ai(battle):
    """Give the computer players their copies, and the wish to build them.

    A human builds what the sidebar offers, so a copy gated to their seat
    is the whole of it. A computer player builds what its task forces name,
    so the copies are useless until those name them.

    The ally's copies are what it bought with its own earnings. An enemy's
    are what the offer handed it, which is how an opposition gets better
    over a run without having a purse to keep it in.
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
    # What an enemy that has infiltrated fields. Not drawn: it is every
    # stolen-tech unit its own country may own, which is what having
    # infiltrated means. The AI needs no new script for them -- all
    # fifteen are already named by Mental Omega's own task forces, and
    # ai_house_code copies those the way it copies any other.
    from .ownership import stolen_tech_units

    infiltrated = set()
    if 'stolen' in set(battle['offer'].modifiers):
        for index in battle['offer'].enemy_countries:
            country = country_by_index(index)
            if country is None or (
                ally is not None and country.country_id == ally.country_id
            ):
                continue
            infiltrated.add(country.country_id)

    by_country = {}
    for country_id in sorted(infiltrated):
        made = apply_house_clones(
            SPAWN_MAP_INI,
            (),
            country_id,
            prefix=GRANT_CLONE_PREFIX,
            forbid_source=False,
            gated=False,
            grant=stolen_tech_units(country_id),
        )
        if made:
            by_country.setdefault(country_id, {}).update(made)
    for country_id, bought in enemy_purchases(battle['offer']).items():
        if ally is not None and country_id == ally.country_id:
            # The ally is playing what an enemy is playing. A copy is the
            # country's, so arming the enemy here would arm the ally too;
            # the enemy fights this one with what the rules gave it.
            continue
        # A superweapon is not a TechnoType, so what the enemy spent its
        # Ore on is split the way the player's purchases are: the units
        # become its own copies, the powers become copies of the power
        # granted to the country it is playing.
        armed = superweapon_ids()
        made = apply_house_clones(
            SPAWN_MAP_INI,
            tuple(one for one in bought if one.unit not in armed),
            country_id,
            prefix=ENEMY_CLONE_PREFIX,
            forbid_source=False,
        )
        apply_power_clones(
            SPAWN_MAP_INI,
            tuple(one for one in bought if one.unit in armed),
            country_id,
            prefix=ENEMY_POWER_PREFIX,
        )
        if made:
            by_country.setdefault(country_id, {}).update(made)
    houses = ai_houses(battle, clones, by_country)
    if houses and (clones or by_country):
        stage_ai_file(ai_house_code(houses))
    log_event(
        'skirmish_ai_prepared',
        ally_clones=len(clones),
        armed_enemies=len(by_country),
        infiltrated_enemies=len(infiltrated),
        enemy_clones=sum(len(made) for made in by_country.values()),
    )
    return clones
