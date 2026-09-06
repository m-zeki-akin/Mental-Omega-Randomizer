"""The spawn file that starts a skirmish.

Modelled on a spawn.ini the Mental Omega client actually wrote for an
eight-player skirmish, rather than on inference, and then proven by launching
it. Four things in that file settled questions guessing had got wrong:

The human player is ``Multi1`` and appears **only** in ``[Settings]`` -- its
country and colour are the ``Side`` and ``Color`` there. ``HouseCountries``,
``HouseColors`` and ``HouseHandicaps`` start at ``Multi2`` and describe the
computer players alone.

An ally is written as the ally's house index minus one, so ``Multi1`` naming
``HouseAllyOne=1`` means "allied with Multi2". A house with no ally simply
has no section, which is how that file expressed one free-for-all opponent
beside two teams.

``SpawnLocations`` is a 0-based waypoint index, and is optional per house.

And no campaign key belongs here. ``IsSinglePlayer=Yes``, copied across from
the launcher's campaign spawn file, is read by the spawner as ``IsCampaign``
and ends the launch with a fatal error while the engine is processing sides.

An open question this does not answer: how a finished skirmish reports what
happened. Campaign victory is detected from markers in the game's hook log,
keyed on mission TeamType names that a skirmish has none of.
"""

from dataclasses import dataclass


# The AI's difficulty counts the other way from everything else: 0 is the
# hardest. Read off a spawn.ini the client wrote beside the settings it was
# written from -- a lobby of Hard, Medium, Easy, Easy became HouseHandicaps
# of 0, 1, 2, 2 -- and it is the same scale the challenge modes count with.
AI_DIFFICULTY_HARD = 0
AI_DIFFICULTY_MEDIUM = 1
AI_DIFFICULTY_EASY = 2

ALLY_ORDINALS = (
    'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight',
)

# Named by the client in every skirmish it writes; the file lives inside a
# MIX rather than on disk. This is the one from a working sample -- a load
# screen chosen per side is still to come.
DEFAULT_LOAD_SCREEN = 'Resources/l600s21.pcx'

# The match rules a battle is played under. Kept together so a run can change
# one of them without the caller restating the rest.
# The spawner's own [Settings] keys, read out of cncnet5.dll: UnitCount,
# Scenario, GameSpeed, Seed, TechLevel, AIPlayers, AIDifficulty,
# BuildOffAlly, Superweapons, HarvesterTruce, GameMode, BridgeDestroy,
# FogOfWar, Crates, ShortGame, Bases, MCVRedeploy, Credits, Name, Side,
# Color, MultiEngineer, Firestorm, AlliesAllowed, IsSpectator, MultiN.
# A key that is not written is not defaulted to the sensible thing -- it is
# read as off. That is how a whole run was played with no superweapons in
# it: nobody had written Superweapons at all.
DEFAULT_MATCH_OPTIONS = {
    'Superweapons': 'True',
    # Whether a house may build a base rather than fight with what it
    # starts with. Off would be a different game entirely.
    'Bases': 'True',
    # The multiple-factory build bonus, and the two rules a skirmish is
    # normally played with. All three are the client's own defaults.
    'MultipleFactory': 'True',
    'HarvesterTruce': 'False',
    'BridgeDestroy': 'True',
    'ShortGame': 'True',
    'NoGarrisons': 'False',
    'MCVRedeploy': 'True',
    'BuildOffAlly': 'True',
    'Crates': 'False',
    'NavalCombat': 'False',
    'AlliesAllowed': 'True',
    'StolenTech': 'True',
    # Mental Omega's own AI boost, off by default and turned on by the
    # battles that want it. It is not a free improvement: its numbers are
    # per difficulty, and on Easy it raises the team delay from 90 to 1000,
    # so an easy AI given the boost attacks even less than one without it.
    # The late tiers ask for it, and it is what a bonus battle can offer.
    'MentalAI': 'False',
    'LimitedMCV': 'False',
    'ImmuneDerricks': 'False',
    'FreeRadar': 'False',
    'NoSpawnPreviews': 'False',
    'ConYardStart': 'False',
    'NerfEights': 'False',
    'UnitCount': '0',
    'GameSpeed': '1',
    # Everybody's starting credits, the player and every computer player
    # alike. High, on purpose: the AI's own income cheat is small and a
    # battle that opens with both sides broke is a battle nobody fights.
    'Credits': '25000',
    'TechLevel': '10',
    'FogOfWar': 'No',
    'MultiEngineer': 'Yes',
}


def match_settings(options=None):
    """Return the settings this match plays under.

    A setting is answered in two places -- the flag the spawner reads and
    the INI the client merges into the map -- so both have to be decided
    from the same dictionary or a match ends up saying one thing and
    playing another.
    """
    settings = dict(DEFAULT_MATCH_OPTIONS)
    settings.update(options or {})
    return settings


@dataclass(frozen=True)
class SkirmishHouse:
    """One computer player in the line-up."""

    country: int
    color: int
    friendly: bool
    handicap: int = AI_DIFFICULTY_MEDIUM


def skirmish_spawn_ini_text(
    *,
    map_name,
    player_country,
    player_color,
    houses,
    seed,
    difficulty=None,
    player_name='Commander',
    game_mode='Standard',
    spawn_locations=True,
    starts=None,
    load_screen=DEFAULT_LOAD_SCREEN,
    options=None,
):
    """Return a complete skirmish spawn.ini.

    ``houses`` are the computer players in seating order, becoming ``Multi2``
    onwards. The human is always ``Multi1``.

    ``starts`` names each house's starting point when the map decides them,
    as a challenge map does: ``{1: 0, 2: 2, 3: 3, 4: 4}``. Without it the
    houses take the first starts in order.
    """
    houses = tuple(houses)
    numbered = tuple(
        (index + 2, house) for index, house in enumerate(houses)
    )
    friendly = [1] + [multi for multi, house in numbered if house.friendly]
    hostile = [multi for multi, house in numbered if not house.friendly]

    settings = match_settings(options)
    # The spawner keeps a match-wide AI difficulty beside the per-house
    # handicaps, on the same scale: 0 is Hard. Left unwritten it is read as
    # 0 like everything else, which is not the same as being told.
    if difficulty is None and houses:
        difficulty = min(house.handicap for house in houses)
    if difficulty is not None:
        settings.setdefault('AIDifficulty', str(int(difficulty)))
    lines = [
        '[Settings]',
        f'Name={player_name}',
        # The map itself is copied to spawnmap.ini beside the game; the
        # spawner reads the scenario under that name and nothing else.
        'Scenario=spawnmap.ini',
        f'UIGameMode={game_mode}',
        f'UIMapName={map_name}',
        'PlayerCount=1',
        f'Side={int(player_country)}',
        'IsSpectator=False',
        f'Color={int(player_color)}',
        f'CustomLoadScreen={load_screen}',
        f'AIPlayers={len(houses)}',
        f'Seed={int(seed)}',
    ]
    lines.extend(
        f'{key}={value}' for key, value in sorted(settings.items())
    )

    def table(section, value_for):
        lines.append('')
        lines.append(f'[{section}]')
        for multi, house in numbered:
            lines.append(f'Multi{multi}={value_for(house)}')

    table('HouseHandicaps', lambda house: int(house.handicap))
    table('HouseCountries', lambda house: int(house.country))
    table('HouseColors', lambda house: int(house.color))

    for team in (friendly, hostile):
        for multi in team:
            allies = [other for other in team if other != multi]
            if not allies:
                continue
            lines.append('')
            lines.append(f'[Multi{multi}_Alliances]')
            for index, ally in enumerate(allies):
                lines.append(f'HouseAlly{ALLY_ORDINALS[index]}={ally - 1}')

    if spawn_locations:
        lines.append('')
        lines.append('[SpawnLocations]')
        ordered = [1] + [multi for multi, _house in numbered]
        for position, multi in enumerate(ordered):
            lines.append(
                f'Multi{multi}={(starts or {}).get(multi, position)}'
            )
    return '\r\n'.join(lines) + '\r\n'


def write_skirmish_spawn_ini(path, text):
    """Write the spawn file with the line endings it was built with.

    The lines are joined with CRLF, which is what the client writes. Writing
    that through the default text mode translates every newline again and
    puts CR CR LF on disk; the engine tolerates it, but there is no reason
    to hand it something no other tool produces.
    """
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)
