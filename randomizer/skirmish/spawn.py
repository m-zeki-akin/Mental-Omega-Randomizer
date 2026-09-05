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


# The client's own SkirmishSettings.ini uses 2 for Hard.
AI_HANDICAP_EASY = 0
AI_HANDICAP_NORMAL = 1
AI_HANDICAP_HARD = 2

ALLY_ORDINALS = (
    'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight',
)

# Named by the client in every skirmish it writes; the file lives inside a
# MIX rather than on disk. This is the one from a working sample -- a load
# screen chosen per side is still to come.
DEFAULT_LOAD_SCREEN = 'Resources/l600s21.pcx'

# The match rules a battle is played under. Kept together so a run can change
# one of them without the caller restating the rest.
DEFAULT_MATCH_OPTIONS = {
    'ShortGame': 'True',
    'NoGarrisons': 'False',
    'MCVRedeploy': 'True',
    'BuildOffAlly': 'True',
    'Crates': 'False',
    'NavalCombat': 'False',
    'AlliesAllowed': 'True',
    'StolenTech': 'True',
    'MentalAI': 'False',
    'LimitedMCV': 'False',
    'ImmuneDerricks': 'False',
    'FreeRadar': 'False',
    'NoSpawnPreviews': 'False',
    'ConYardStart': 'False',
    'NerfEights': 'True',
    'UnitCount': '0',
    'GameSpeed': '1',
    'Credits': '10000',
    'TechLevel': '10',
    'FogOfWar': 'No',
    'MultiEngineer': 'Yes',
}


@dataclass(frozen=True)
class SkirmishHouse:
    """One computer player in the line-up."""

    country: int
    color: int
    friendly: bool
    handicap: int = AI_HANDICAP_HARD


def skirmish_spawn_ini_text(
    *,
    map_name,
    player_country,
    player_color,
    houses,
    seed,
    player_name='Commander',
    spawn_locations=True,
    load_screen=DEFAULT_LOAD_SCREEN,
    options=None,
):
    """Return a complete skirmish spawn.ini.

    ``houses`` are the computer players in seating order, becoming ``Multi2``
    onwards. The human is always ``Multi1``.
    """
    houses = tuple(houses)
    numbered = tuple(
        (index + 2, house) for index, house in enumerate(houses)
    )
    friendly = [1] + [multi for multi, house in numbered if house.friendly]
    hostile = [multi for multi, house in numbered if not house.friendly]

    settings = dict(DEFAULT_MATCH_OPTIONS)
    settings.update(options or {})
    lines = [
        '[Settings]',
        f'Name={player_name}',
        # The map itself is copied to spawnmap.ini beside the game; the
        # spawner reads the scenario under that name and nothing else.
        'Scenario=spawnmap.ini',
        'UIGameMode=Standard',
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
        for position, multi in enumerate(
            [1] + [multi for multi, _house in numbered]
        ):
            lines.append(f'Multi{multi}={position}')
    return '\r\n'.join(lines) + '\r\n'
