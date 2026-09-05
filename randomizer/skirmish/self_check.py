"""Assert the skirmish contract the launcher had to be taught.

Every check here stands for a launch that failed on this machine, or for a
line in a spawn file the client writes that guessing had got wrong. The map
reader is checked against maps written for the purpose rather than against
the installation, so the reader is what is being tested and the report says
the same thing on a developer's checkout as on a player's game folder.
"""

from configparser import ConfigParser
from pathlib import Path
from tempfile import TemporaryDirectory

from .factions import (
    SKIRMISH_SIDES,
    skirmish_countries,
    validate_installed_countries,
)
from .maps import (
    CHALLENGE_POOL_DIR,
    STANDARD_POOL_DIR,
    maps_for_players,
    read_map_pool,
    summarize_map_pools,
)
from .results import last_game_result, result_blocks
from .spawn import SkirmishHouse, skirmish_spawn_ini_text


# Keys the campaign spawn file carries. One of them, IsSinglePlayer, is read
# by the spawner as IsCampaign and ends a skirmish launch with a fatal error
# while the engine is processing sides.
CAMPAIGN_ONLY_KEYS = (
    'issingleplayer', 'campdifficulty', 'difficultymodehuman',
    'difficultymodecomputer', 'firestorm', 'sidebarhack',
)

MAP_FIXTURE = """; a map, as FinalAlert writes one

[Header]
Width=100
Height=100
Waypoint1=10,10
Waypoint2=90,90
Waypoint3=10,90
Waypoint4=0,0
Waypoint8=50,50
NumberStartingPoints=3

[Terrain]
1234=TREE01

[Basic]
Name=(3) Self Check Valley
GameMode=Standard,No Bases
MaxPlayer=4
MinPlayer=2
Official=yes
"""


# The two outcomes as the game actually wrote them, from a battle won and a
# battle lost on this machine. Trimmed at both ends, otherwise verbatim.
DEFEAT_LOG = """LOADED NTRLMD.MIXLOADED NEUTRAL.MIX
Release_Mouse()
Commander: Loser
 Scheme: 1
 Lost = 0
 Kills = 0
 Built = 0
 Score = 0
Computer: Winner
 Scheme: 7
 Lost = 0
 Kills = 0
 Built = 3
 Score = 0
Default
Sound frame size = 21504 bytes
Sound buffer size = 86016 bytes
Default
Default
Tooltips are on.
     Releasing NEUTRAL.MIX
     Releasing NTRLMD.MIX
LOADED NTRLMD.MIXLOADED NEUTRAL.MIX
Game loop finished. Average FPS = 12
     Releasing NEUTRAL.MIX
     Releasing NTRLMD.MIX
Closing log file on request 111
"""

VICTORY_LOG = """MPlayer_Defeated: frame 45074, house id 1, MapIsClear set to true
MPlayer_Defeated() - Opponent Computer has been defeated
MPlayer_Defeated() - Alive = 1, Humans = 1
Saw game completion due to player defeat
MPlayer_Defeated() - All remaining players are allied
MPlayer_Defeated() - Flag_To_Win
Frame 45074, BorrowedTime == 90
Tooltips are off.
Sending game results.  SawCompletion=1
LOADED NTRLMD.MIXLOADED NEUTRAL.MIX
Release_Mouse()
Commander: Winner
 Scheme: 1
 Lost = 101
 Kills = 518
 Built = 195
 Score = 478701
Computer: Loser
 Scheme: 7
 Lost = 513
 Kills = 88
 Built = 369
 Score = 33890
Default
Sound frame size = 21504 bytes
Sound buffer size = 86016 bytes
Default
Default
Tooltips are on.
     Releasing NEUTRAL.MIX
     Releasing NTRLMD.MIX
LOADED NTRLMD.MIXLOADED NEUTRAL.MIX
Game loop finished. Average FPS = 59
     Releasing NEUTRAL.MIX
     Releasing NTRLMD.MIX
Closing log file on request 111
"""


def _result_checks():
    defeat = last_game_result(DEFEAT_LOG)
    victory = last_game_result(VICTORY_LOG)
    both = result_blocks(DEFEAT_LOG + VICTORY_LOG)
    return {
        'skirmish_result_defeat_valid': bool(
            defeat is not None
            and not defeat.won
            and defeat.name == 'Commander'
        ),
        'skirmish_result_victory_valid': bool(
            victory is not None
            and victory.won
            and victory.kills == 518
            and victory.lost == 101
            and victory.built == 195
            and victory.score == 478701
        ),
        # Two games in one log are two blocks, and the battle just played is
        # the last of them.
        'skirmish_result_last_game_valid': bool(
            len(both) == 2
            and len(both[0]) == 2
            and last_game_result(DEFEAT_LOG + VICTORY_LOG).won
            and both[1][1].name == 'Computer'
            and both[1][1].kills == 88
        ),
        # MPlayer_Defeated is written about whichever house was defeated and
        # appears in a won game. Reading it as the player's defeat would call
        # every victory a loss.
        'skirmish_result_ignores_defeat_marker_valid': bool(
            'MPlayer_Defeated' in VICTORY_LOG and victory.won
        ),
        # A game closed before it ended is neither outcome.
        'skirmish_result_unfinished_valid': bool(
            last_game_result('Tooltips are on.\nClosing log file 111\n')
            is None
            and last_game_result(VICTORY_LOG, player_name='Someone Else')
            is None
        ),
    }

def _parsed(text):
    parser = ConfigParser(strict=False)
    parser.optionxform = str
    parser.read_string(text)
    return parser


def _spawn_checks():
    ally = SkirmishHouse(country=3, color=2, friendly=True)
    enemies = (
        SkirmishHouse(country=6, color=4, friendly=False),
        SkirmishHouse(country=9, color=6, friendly=False),
    )
    text = skirmish_spawn_ini_text(
        map_name='Self Check Valley',
        player_country=0,
        player_color=0,
        houses=(ally, *enemies),
        seed=12345,
    )
    spawn = _parsed(text)
    settings = spawn['Settings']

    # The launch that failed: the campaign writer's keys have no place here.
    no_campaign_keys = not any(
        key.lower() in CAMPAIGN_ONLY_KEYS
        for section in spawn.sections()
        for key in spawn[section]
    )
    # The human is Multi1 and is described by Settings alone.
    tables = ('HouseCountries', 'HouseColors', 'HouseHandicaps')
    human_in_settings_only = bool(
        settings['Side'] == '0'
        and settings['Color'] == '0'
        and settings['Scenario'] == 'spawnmap.ini'
        and settings['AIPlayers'] == '3'
        and all('Multi1' not in spawn[table] for table in tables)
        and all(
            sorted(spawn[table]) == ['Multi2', 'Multi3', 'Multi4']
            for table in tables
        )
    )
    ai_tables_valid = bool(
        spawn['HouseCountries']['Multi2'] == '3'
        and spawn['HouseCountries']['Multi3'] == '6'
        and spawn['HouseCountries']['Multi4'] == '9'
        and spawn['HouseColors']['Multi2'] == '2'
        and spawn['HouseHandicaps']['Multi2'] == '2'
    )
    # An ally is the ally's house index minus one, and a house with nobody to
    # ally with has no section at all.
    alliances_valid = bool(
        spawn['Multi1_Alliances']['HouseAllyOne'] == '1'
        and spawn['Multi2_Alliances']['HouseAllyOne'] == '0'
        and spawn['Multi3_Alliances']['HouseAllyOne'] == '3'
        and spawn['Multi4_Alliances']['HouseAllyOne'] == '2'
    )
    spawn_locations_valid = bool(
        spawn['SpawnLocations']['Multi1'] == '0'
        and spawn['SpawnLocations']['Multi2'] == '1'
        and spawn['SpawnLocations']['Multi4'] == '3'
    )
    # A free-for-all opponent is expressed by having no alliance section.
    free_for_all = skirmish_spawn_ini_text(
        map_name='Self Check Valley',
        player_country=0,
        player_color=0,
        houses=(SkirmishHouse(country=6, color=4, friendly=False),),
        seed=1,
    )
    solitary_houses_valid = not any(
        section.endswith('_Alliances') for section in _parsed(
            free_for_all
        ).sections()
    )
    return {
        'skirmish_spawn_no_campaign_keys_valid': no_campaign_keys,
        'skirmish_spawn_human_is_settings_only_valid': human_in_settings_only,
        'skirmish_spawn_ai_tables_valid': ai_tables_valid,
        'skirmish_spawn_alliances_valid': alliances_valid,
        'skirmish_spawn_locations_valid': spawn_locations_valid,
        'skirmish_spawn_free_for_all_valid': solitary_houses_valid,
    }


def _map_reader_checks():
    with TemporaryDirectory(prefix='mo-skirmish-maps-') as temporary:
        root = Path(temporary)
        (root / 'valley.map').write_text(MAP_FIXTURE, encoding='utf-8')
        (root / 'valley.png').write_bytes(b'not really a png')
        (root / 'nopreview.map').write_text(
            MAP_FIXTURE.replace('MaxPlayer=4', 'MaxPlayer=8'),
            encoding='utf-8',
        )
        pool = read_map_pool(root, cache=False)
        valley = next(entry for entry in pool if entry.path.stem == 'valley')
        other = next(
            entry for entry in pool if entry.path.stem == 'nopreview'
        )
        read_valid = bool(
            len(pool) == 2
            and valley.name == '(3) Self Check Valley'
            and valley.players == 4
            and valley.minimum_players == 2
            # Three starts, as the header states, whatever MaxPlayer says.
            and valley.starts == 3
            and valley.game_modes == ('Standard', 'No Bases')
            and valley.preview is not None
            and other.preview is None
        )
        # What a map claims and what it can place are different numbers, and
        # a house with no start is dropped on top of somebody.
        seats_valid = bool(
            valley.seats == 3
            and other.seats == 3
            and len(maps_for_players(pool, 3)) == 2
            and not maps_for_players(pool, 4)
        )
        return {
            'skirmish_map_reader_valid': read_valid,
            'skirmish_map_seats_valid': seats_valid,
        }


def _country_checks():
    countries = skirmish_countries()
    if not countries:
        # No installed rules to read: nothing is claimed rather than failed,
        # the way every other game-file check behaves off a game folder.
        return {'skirmish_countries_valid': True, 'skirmish_countries': {}}
    report = validate_installed_countries()
    return {
        'skirmish_countries_valid': bool(
            # Twelve playable countries across the mod's four sides, each
            # keeping the position the spawn file indexes it by.
            report['playable_countries'] >= 12
            and set(report['sides']) >= set(SKIRMISH_SIDES.values())
            and report['stock_order_matches'] >= 12
        ),
        'skirmish_countries': report,
    }


def validate_skirmish_contract():
    """Return the skirmish self-check rows, plus what the pools hold."""
    report = {}
    report.update(_spawn_checks())
    report.update(_result_checks())
    report.update(_map_reader_checks())
    report.update(_country_checks())
    report['skirmish_map_pools'] = (
        summarize_map_pools()
        if STANDARD_POOL_DIR.is_dir() or CHALLENGE_POOL_DIR.is_dir()
        else {}
    )
    return report
