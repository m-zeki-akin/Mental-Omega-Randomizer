"""Assert the skirmish contract the launcher had to be taught.

Every check here stands for a launch that failed on this machine, or for a
line in a spawn file the client writes that guessing had got wrong. The map
reader is checked against maps written for the purpose rather than against
the installation, so the reader is what is being tested and the report says
the same thing on a developer's checkout as on a player's game folder.
"""

from configparser import ConfigParser
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from randomizer.core.integrity import sign
from randomizer.core.storage import atomic_write_json
from randomizer.shop.model import RunStatus

from .factions import (
    SKIRMISH_SIDES,
    country_by_index,
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
from .transitions import SkirmishTransitionError
from .spawn import (
    AI_DIFFICULTY_HARD,
    SkirmishHouse,
    skirmish_spawn_ini_text,
)


# Keys the campaign spawn file carries. One of them, IsSinglePlayer, is read
# by the spawner as IsCampaign and ends a skirmish launch with a fatal error
# while the engine is processing sides.
CAMPAIGN_ONLY_KEYS = (
    'issingleplayer', 'campdifficulty', 'difficultymodehuman',
    'difficultymodecomputer', 'firestorm', 'sidebarhack',
)

MAP_FIXTURE = """; a map, as FinalAlert writes one

[DUMMYDUMMY]
Name=
UIName=Name:DUMMYDUMMY

[LIONH]
Name=Lionheart Bomber

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
    ally = SkirmishHouse(
        country=3, color=2, friendly=True, handicap=AI_DIFFICULTY_HARD
    )
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

    # Every key the spawner reads that this mode has an answer for. A key
    # left out is not defaulted to the sensible thing: it is read as off,
    # which is how a whole run was played with no superweapons in it.
    spawner_keys_valid = bool(
        settings['Credits'] == '25000'
        and settings['Superweapons'] == 'True'
        and settings['Bases'] == 'True'
        and settings['MultipleFactory'] == 'True'
        and settings['BridgeDestroy'] == 'True'
        and settings['HarvesterTruce'] == 'False'
        # The match-wide AI difficulty, on the same scale as the per-house
        # handicaps: 0 is Hard.
        and settings['AIDifficulty'] == '0'
    )

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
        # Hard is 0: the AI's difficulty counts the other way from
        # everything else, and a lobby of Hard/Medium/Easy/Easy became
        # handicaps of 0/1/2/2 in the file the client wrote.
        and spawn['HouseHandicaps']['Multi2'] == '0'
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
        'skirmish_spawn_spawner_keys_valid': spawner_keys_valid,
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
            # Read from [Basic], not from the first Name= in the file: a
            # challenge map carries unit overrides with Name= keys of their
            # own, thousands of lines above the section describing the map.
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


@dataclass(frozen=True)
class SimpleCountry:
    """Stands in for an installed country when there are no rules to read."""

    index: int


def _fixture_pool(directory, count, *, prefix='map', seats=6):
    """Return maps that exist, so a draw can be checked without a game."""
    from .maps import read_map_pool

    for index in range(count):
        (directory / f'{prefix}{index:02d}.map').write_text(
            MAP_FIXTURE
            .replace('MaxPlayer=4', f'MaxPlayer={seats}')
            .replace('NumberStartingPoints=3', f'NumberStartingPoints={seats}')
            .replace('(3) Self Check Valley', f'({seats}) Fixture {index:02d}'),
            encoding='utf-8',
        )
    return read_map_pool(directory, cache=False)


def _run_checks():
    from .model import DEFAULT_LIVES
    from .persistence import (
        SkirmishPersistenceError,
        SkirmishPersistencePaths,
        SkirmishRepository,
    )
    from .progression import is_challenge_battle, offers_for, tier_for
    from .transitions import (
        commit_offer,
        offer_battles,
        record_defeat,
        record_victory,
        start_run,
    )

    countries = skirmish_countries() or tuple(
        SimpleCountry(index) for index in range(12)
    )
    with TemporaryDirectory(prefix='mo-skirmish-run-check-') as temporary:
        root = Path(temporary)
        maps_dir = root / 'MapsMO'
        standard = maps_dir / 'Standard'
        challenge = maps_dir / 'Challenge'
        standard.mkdir(parents=True)
        challenge.mkdir(parents=True)
        standard_pool = _fixture_pool(standard, 12, prefix='std')
        challenge_pool = _fixture_pool(challenge, 4, prefix='chl', seats=5)

        # Past the warmup: what is checked here is how a tier counts, and
        # the warmup is outside the count.
        run = replace(
            start_run(
                run_id='check-run',
                seed='SKIRMISH-CHECK',
                player_country=0,
                ally_country=3,
                created='2026-09-06',
            ),
            battle=1,
        )
        # A tier is five battles and the fifth is the challenge.
        cadence_valid = bool(
            [tier_for(battle) for battle in (1, 5, 6, 10, 11)]
            == [1, 1, 2, 2, 3]
            and not is_challenge_battle(4)
            and is_challenge_battle(5)
            and not is_challenge_battle(6)
            and is_challenge_battle(10)
        )

        first = offers_for(
            run, standard_pool, challenge_pool, maps_dir, countries
        )
        again = offers_for(
            run, standard_pool, challenge_pool, maps_dir, countries
        )
        offers_valid = bool(
            len(first) == 3
            and first == again
            and not any(offer.challenge for offer in first)
            # Stored as a path relative to MapsMO, so a moved installation
            # still finds the map and the pool it came from is readable.
            and all(
                offer.map_path.startswith('Standard/') for offer in first
            )
            and all(offer.enemy_countries for offer in first)
            and len({offer.map_path for offer in first}) == 3
        )

        # Taking one and winning it moves the run on.
        run = commit_offer(offer_battles(run, first), 1)
        won = record_victory(run)
        victory_valid = bool(
            won.battle == 2
            and won.won_battles == 1
            and not won.offers
            and won.committed_offer is None
        )

        # A defeat costs a life and leaves the battle where it was.
        lost = record_defeat(run)
        defeat_valid = bool(
            lost.battle == run.battle
            and lost.revivals_used == 1
            and lost.lives_left == DEFAULT_LIVES - 1
            and lost.status is RunStatus.ACTIVE
            and record_defeat(
                commit_offer(record_defeat(commit_offer(lost, 1)), 1)
            ).status is RunStatus.FAILED
        )

        # The challenge battle offers one map and no choice, and the pool
        # comes back whole once it has been through.
        closing = replace(won, battle=5)
        seen = []
        for _round in range(len(challenge_pool)):
            offers = offers_for(
                closing, standard_pool, challenge_pool, maps_dir, countries
            )
            closing = record_victory(
                commit_offer(offer_battles(closing, offers), 0)
            )
            seen.append(offers[0].map_path)
            closing = replace(closing, battle=closing.battle + 4)
        after = offers_for(
            closing, standard_pool, challenge_pool, maps_dir, countries
        )
        challenge_valid = bool(
            len(seen) == len(challenge_pool)
            and len(set(seen)) == len(challenge_pool)
            and all(path.startswith('Challenge/') for path in seen)
            and len(closing.used_challenge_maps) == len(challenge_pool)
            # Exhausted, so the next challenge draws from the whole pool
            # again rather than offering nothing.
            and len(after) == 1
            and after[0].challenge
        )

        paths = SkirmishPersistencePaths(
            runs=root / 'skirmish_runs.dat',
            backup_dir=root / 'backups',
        )
        repository = SkirmishRepository(paths)
        stored = repository.save_run(commit_offer(offer_battles(run, first), 0))
        reopened = SkirmishRepository(paths).load_run()
        second = repository.save_run(
            start_run(
                run_id='check-run-2',
                seed='SKIRMISH-CHECK-2',
                player_country=6,
                ally_country=9,
            )
        )
        runs, active = SkirmishRepository(paths).list_runs()
        storage_valid = bool(
            reopened == stored
            and reopened.committed() == first[0]
            and len(runs) == 2
            and active == second.run_id
            and runs[0].run_id == 'check-run'
        )
        repository.select_run('check-run')
        repository.delete_run('check-run-2')
        runs, active = SkirmishRepository(paths).list_runs()
        selection_valid = bool(
            len(runs) == 1
            and active == 'check-run'
            and SkirmishRepository(paths).load_run().run_id == 'check-run'
        )

        # A run whose map the installation no longer has still loads: the
        # offer is unplayable, the run is not lost.
        missing = replace(
            stored,
            offers=(replace(first[0], map_path='Standard/gone.map'),),
            committed_offer=0,
        )
        repository.save_run(missing)
        survives_missing_map = bool(
            SkirmishRepository(paths).load_run().committed().map_path
            == 'Standard/gone.map'
        )

        atomic_write_json(paths.runs, sign({
            'schema_version': 1,
            'active_run_id': 'twin',
            'runs': [
                replace(stored, run_id='twin').to_dict(),
                replace(stored, run_id='twin', battle=3).to_dict(),
            ],
        }), indent=None)
        try:
            SkirmishRepository(paths).load_run()
            duplicate_rejected = False
        except SkirmishPersistenceError:
            duplicate_rejected = True

    return {
        'skirmish_tier_cadence_valid': cadence_valid,
        'skirmish_offers_deterministic_valid': offers_valid,
        'skirmish_victory_valid': victory_valid,
        'skirmish_defeat_costs_a_life_valid': defeat_valid,
        'skirmish_challenge_pool_valid': challenge_valid,
        'skirmish_run_storage_valid': storage_valid and selection_valid,
        'skirmish_run_survives_missing_map_valid': survives_missing_map,
        'skirmish_run_duplicate_rejected_valid': duplicate_rejected,
    }


# A challenge map as the client's own map list describes it, verbatim from
# the installation, beside the game mode that forces its options.
CHALLENGE_INI = """[Challenge Hard]
CustomIniPath=INI\\Map Code\\Challenge Hard.ini
ForcedOptions=Challenge HardForcedOptions
CoopDifficultyLevel=0

[Challenge HardForcedOptions]
chkShortGame=true
chkIngameAllying=false
chkNoSpawnPreviews=true
cmbUnitCount=6
cmbTechLevel=0

[noconyardstartForcedOptions]
chkConYardStart=false

[MapsMO\\Challenge\\c_aberration]
Description=Challenge XIII: Aberration
GameModes=Challenge Easy,Challenge Medium,Challenge Hard
MinPlayers=1
MaxPlayers=2
Waypoint0=142134
Waypoint1=142154
IsCoopMission=yes
DisallowedPlayerColors=6
EnemyHouse0=0,6,2 ; United States, Blue
EnemyHouse1=1,6,3 ; Euro Alliance, Blue
EnemyHouse2=2,6,4 ; Pacific Front, Blue
ForcedOptions=noconyardstartForcedOptions
"""

MAP_CODE = """; Mental Omega Mode Client INI

[General]
TeamRetaliate=no
TeamDelays=500,1500,2500

[Actions]
MODEINT1=1,11,4,MISSION:AIDHARD,0,0,0,0,A
"""


def _table_checks():
    """A battle that has ended clears the table, and the next one deals it.

    The window used to deal, so nothing else could: a screen that read a
    won run found no offers and had no way to fight again. What is checked
    is that dealing is now the mode's own, that it leaves a standing table
    alone, and that it never seats the ally's country as the enemy.
    """
    from .maps import STANDARD_POOL_DIR
    from .table import deal, enemy_pool
    from .transitions import commit_offer, record_victory, start_run

    countries = skirmish_countries()
    if len(countries) < 2:
        return {'skirmish_deals_next_table': False}
    run = start_run(
        run_id='table-check', seed='TABLE', created='2026-01-01',
        player_country=countries[0].index,
        ally_country=countries[1].index,
    )
    pool = enemy_pool(run)
    # Every installed country but the ally's own, and never nothing.
    pool_valid = bool(
        pool
        and all(country.index != run.ally_country for country in pool)
        and len(pool) == len(countries) - 1
    )
    if not STANDARD_POOL_DIR.is_dir():
        # No maps to deal from. What can be read without them still is.
        return {'skirmish_deals_next_table': pool_valid}

    dealt = deal(run)
    standing = deal(dealt)
    won = record_victory(commit_offer(dealt, 0))
    again = deal(won)
    return {
        'skirmish_deals_next_table': bool(
            pool_valid
            and dealt.offers
            and dealt.shelf
            # Dealing twice into one battle leaves what the player is
            # looking at exactly where it was.
            and standing.offers == dealt.offers
            and standing.shelf == dealt.shelf
            # A victory clears the table and the next deal sets it again.
            and not won.offers
            and again.offers
            and again.battle == dealt.battle + 1
            and all(
                run.ally_country not in offer.enemy_countries
                for offer in again.offers
            )
        ),
    }


def _challenge_checks():
    from .challenges import (
        _sections,
        merge_map_code,
        parse_challenges,
        parse_forced_options,
    )
    from .progression import challenge_level, challenge_offer
    from .spawn import (
        AI_DIFFICULTY_EASY,
        AI_DIFFICULTY_HARD,
        AI_DIFFICULTY_MEDIUM,
    )
    from .transitions import start_run

    sections = _sections(CHALLENGE_INI)
    described = parse_challenges(sections).get('Challenge/c_aberration.map')
    forced = parse_forced_options(
        sections, 'Challenge HardForcedOptions', described.forced_options
    )
    read_valid = bool(
        described is not None
        and [house.country for house in described.houses] == [0, 1, 2]
        and [house.start for house in described.houses] == [2, 3, 4]
        and described.disallowed_colors == (6,)
        # Only the options that are spawn settings; cmbUnitCount and its
        # like are applied as map code, not written here.
        and forced == {
            'ShortGame': 'True',
            'AlliesAllowed': 'False',
            'NoSpawnPreviews': 'True',
            'ConYardStart': 'False',
        }
    )

    # The three challenge modes count the other way: Hard is 0. A run meets
    # them in the order its own tier table names, and the last tier stands
    # for every battle after it.
    from .progression import TIERS

    level_valid = bool(
        challenge_level(5) == AI_DIFFICULTY_EASY
        and challenge_level(10) == AI_DIFFICULTY_EASY
        and challenge_level(15) == AI_DIFFICULTY_MEDIUM
        and challenge_level(25) == AI_DIFFICULTY_HARD
        and challenge_level(45) == AI_DIFFICULTY_HARD
        and challenge_level(400) == TIERS[-1].challenge
        # Nothing is fought on Easy but the first two challenges: an easy
        # AI does not make an easy battle, it makes a quiet one.
        and not any(
            AI_DIFFICULTY_EASY in tier.enemies for tier in TIERS
        )
        # The tiers name more enemies and better ones as they rise.
        and [len(tier.enemies) for tier in TIERS] == [1, 2, 2, 3, 3, 3, 3, 4, 5]
        and [tier.mental for tier in TIERS].count(True) == 3
    )

    with TemporaryDirectory(prefix='mo-skirmish-challenge-') as temporary:
        root = Path(temporary)
        maps_dir = root / 'MapsMO'
        pool_dir = maps_dir / 'Challenge'
        pool_dir.mkdir(parents=True)
        pool = _fixture_pool(pool_dir, 2, prefix='chl', seats=5)

        # The offer is drawn from the pool; whichever it lands on, a
        # challenge is fought alone, since the second start on those maps is
        # a co-op partner's and the fight was balanced for who stands in it.
        run = start_run(
            run_id='challenge-check',
            seed='CHALLENGE-CHECK',
            player_country=0,
            ally_country=3,
        )
        offer = challenge_offer(
            replace(run, battle=5), pool, maps_dir,
            skirmish_countries() or (SimpleCountry(0),),
        )
        offer_valid = bool(
            offer is not None
            and offer.challenge
            and not offer.ally
            and offer.handicap == AI_DIFFICULTY_EASY
        )

        # The mode's INI is merged into the map rather than appended: the
        # reader keeps the first value it sees, so a second [Actions] under
        # the map's own would change nothing.
        map_file = root / 'spawnmap.ini'
        map_file.write_bytes(
            (
                '[Header]\nWidth=100\n\n[Actions]\nOWN1=1,2,3\n\n'
                '[Basic]\nName=Fixture\n'
            ).encode('utf-8')
        )
        code_file = root / 'code.ini'
        code_file.write_text(MAP_CODE, encoding='utf-8')
        applied = merge_map_code(map_file, code_file)
        merged = map_file.read_bytes().decode('utf-8')
        merge_valid = bool(
            applied == 3
            and merged.count('[Actions]') == 1
            and 'MISSION:AIDHARD' in merged
            and 'OWN1=1,2,3' in merged
            and '[General]' in merged
            and 'TeamRetaliate=no' in merged
            # The map is written with bare line feeds and stays that way.
            and b'\r\n' not in map_file.read_bytes()
        )

    return {
        'skirmish_challenge_read_valid': read_valid,
        'skirmish_challenge_level_valid': level_valid,
        'skirmish_challenge_offer_valid': offer_valid,
        'skirmish_challenge_map_code_valid': merge_valid,
    }

def _option_checks():
    """A game option answers in two places, and both have to agree.

    The client writes a flag into spawn.ini and merges an INI into the map.
    The launcher wrote the flags and merged nothing, so a match declaring
    stolen tech had no Construction Yard a spy could enter. What is checked
    here is that every option this mode turns on still resolves to the file
    the installed client says it resolves to.
    """
    from .options import (
        GAME_OPTIONS_PATH,
        option_map_code_paths,
        parse_game_options,
        read_ini_sections,
    )
    from .spawn import DEFAULT_MATCH_OPTIONS, match_settings

    sections = read_ini_sections(GAME_OPTIONS_PATH)
    checkboxes, dropdowns = parse_game_options(sections)
    known_valid = bool(
        checkboxes
        and dropdowns
        # Every option named in the client is one this mode has an answer
        # for; an option it has never heard of would go out unset.
        and all(option in DEFAULT_MATCH_OPTIONS for option in checkboxes)
    )

    paths = option_map_code_paths(match_settings({}))
    names = {path.name.lower() for path in paths}
    spyable = {}
    for path in paths:
        for section, values in read_ini_sections(path).items():
            if any(key.lower() == 'spyable' for key in values):
                spyable[section] = values
    merged_valid = bool(
        paths
        # Stolen tech is on by default, so the file that makes a Construction
        # Yard enterable has to be among what the map gets.
        and 'stolen tech.ini' in names
        and 'GACNST' in spyable
        and 'GATECH' in spyable
        # And an option this mode leaves off brings nothing with it. The
        # AI boost is off by default and asked for by the tiers that want
        # it, so it is not in what a plain battle merges.
        and 'mental ai.ini' not in names
        # But it is there for a battle that asks.
        and any(
            path.name.lower() == 'mental ai.ini'
            for path in option_map_code_paths(
                match_settings({'MentalAI': 'True'})
            )
        )
    )
    # The in-game speed slider cannot be taken away, so every one of its
    # positions is given the same delay as the speed the run is locked to.
    from .speed import GLOBAL_CONTROLS, SPEED_STEPS, locked_speed_code

    controls = locked_speed_code(1).get(GLOBAL_CONTROLS) or {}
    speed_valid = bool(
        controls.get('CustomGS') == 'yes'
        and len(controls) == SPEED_STEPS + 1
        and {
            value for key, value in controls.items() if key != 'CustomGS'
        } == {'1'}
        and locked_speed_code(4)[GLOBAL_CONTROLS]['CustomGS0.DefaultDelay']
        == '4'
        and not locked_speed_code(None)
    )
    return {
        'skirmish_game_options_known': known_valid,
        'skirmish_game_options_merged': merged_valid,
        'skirmish_speed_slider_inert': speed_valid,
    }


def _clone_checks():
    """A run's upgrades must reach the run and nobody else.

    Writing a buff onto the unit changes it for every house fielding that
    unit. So what a purchase produces is a copy of the type, gated to a
    country only the buyer plays, with the weapons it fires copied too --
    damage, range and reload are the weapon's, and weapons are shared.
    """
    from randomizer.rewards.catalogue import BUFF_TARGETS
    from randomizer.rewards.roster import _installed_sections
    from .clones import house_clone_code
    from .model import UpgradePurchase
    from .seats import pick_seat, seat_map_code

    installed = _installed_sections()
    purchases = (
        UpgradePurchase('GGI', 'speed', 5),
        UpgradePurchase('GGI', 'damage', 4),
    )
    sections, built = house_clone_code(purchases, 'Guild3', prefix='MOP')
    clone = sections.get(built.get('GGI'), {})
    stock = installed.get('GGI') or {}

    def value(body, key):
        return next(
            (body[name] for name in body if name.lower() == key.lower()), ''
        )

    # The installed sections are keyed in upper case; a rules file's own
    # spelling is not.
    weapon = str(value(clone, 'Primary')).upper()
    stock_weapon = str(value(stock, 'Primary')).upper()
    clone_valid = bool(
        built.get('GGI')
        # The copy is faster than the unit it was copied from, and the unit
        # itself is untouched but for the gate that shuts the buyer out.
        and int(value(clone, 'Speed')) > int(value(stock, 'Speed'))
        and value(clone, 'RequiredHouses') == 'Guild3'
        and 'Guild3' in str(value(clone, 'Owner'))
        and set(sections.get('GGI', {})) == {'ForbiddenHouses'}
        # Art comes from the source, so no art file is needed.
        and value(clone, 'Image')
        # The weapon is the copy's own, and it hits harder than the shared
        # one every other house still fires.
        and weapon and weapon != stock_weapon
        and weapon in sections
        and float(value(sections[weapon], 'Damage'))
        > float(value(installed.get(stock_weapon, {}), 'Damage'))
        # Registered at the end of its list: a script argument can be an
        # index into one, so nothing may be renumbered.
        and int(next(iter(sections.get('InfantryTypes', {'0': ''})))) >= 20000
    )

    # Two houses buy in the same battle and both write into the same map.
    # The second has to read what the first left, or it takes the type-list
    # slot and the ForbiddenHouses with it -- and the player's copy quietly
    # stops being the only one they can build.
    first_code, player_built = house_clone_code(
        (UpgradePurchase('GGI', 'speed', 5),), 'Pacific', prefix='MOP',
    )
    shared_code = dict(first_code)
    second_code, ally_built = house_clone_code(
        (UpgradePurchase('GGI', 'damage', 4),), 'UnitedStates', prefix='MOL',
        forbid_source=True, existing=shared_code,
    )
    for name, body in second_code.items():
        shared_code.setdefault(name, {}).update(body)
    listed = shared_code.get('InfantryTypes') or {}
    shared_valid = bool(
        player_built.get('GGI')
        and ally_built.get('GGI')
        and player_built['GGI'] != ally_built['GGI']
        and len(listed) == 2
        and set(listed.values()) == {player_built['GGI'], ally_built['GGI']}
        and set(_csv(shared_code.get('GGI', {}).get('ForbiddenHouses', '')))
        == {'Pacific', 'UnitedStates'}
    )

    countries = [
        'UnitedStates', 'Europeans', 'Pacific', 'USSR', 'Latin', 'Chinese',
        'PsiCorps', 'ScorpionCell', 'Headquaters', 'Guild1', 'Guild2',
        'Guild3',
    ]
    country_sides = {
        name: str(_installed_country_side(name)) for name in countries
    }
    taken = ['UnitedStates', 'Guild1']
    seat = pick_seat(
        'UnitedStates', taken, countries, sides=country_sides, salt='x'
    )
    code, counts = seat_map_code('UnitedStates', seat)
    sides = code.get('Sides') or {}
    crossed = seat_map_code('UnitedStates', 'Guild3')[0].get('Sides') or {}
    seat_valid = bool(
        seat not in {'UnitedStates', 'Guild1'}
        and seat == pick_seat(
            'UnitedStates', taken, countries, sides=country_sides, salt='x'
        )
        # A sister country, so the side lists are left alone entirely and
        # the ownership pass stays small.
        and country_sides[seat] == country_sides['UnitedStates']
        and not sides
        # The seat wears the chosen country and keeps its own place in the
        # country list, which is what the spawner counts with.
        and value(code.get(seat, {}), 'Side')
        == value(installed.get('UNITEDSTATES', {}), 'Side')
        and value(code.get(seat, {}), 'ListIndex')
        == value(installed.get(seat.upper(), {}), 'ListIndex')
        and counts['added'] > 0
        # And when a seat does have to cross sides, every side is written:
        # a map naming two sides leaves the game with two sides.
        and len(crossed) == len(_installed_sides())
        and 'Guild3' in str(crossed.get('GDI', ''))
    )
    return {
        'skirmish_unit_clone_valid': clone_valid,
        'skirmish_two_houses_share_the_map': shared_valid,
        'skirmish_private_seat_valid': seat_valid,
    }


def _csv(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def _installed_country_side(name):
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, sections = installed_rules_registry(synchronous=True)
    values = (sections or {}).get(name) or {}
    return next(
        (values[key] for key in values if str(key).lower() == 'side'), ''
    )


def _installed_sides():
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, sections = installed_rules_registry(synchronous=True)
    return dict((sections or {}).get('Sides') or {})


def _ai_checks():
    """A computer player has to be asked for its copies, not just given them.

    Its production comes from task forces naming units by ID. So a bought
    unit means a copy of every task force that names it, a team pointing at
    the copy, and -- where a trigger is what reaches that team -- a copy of
    the trigger owned by that house, with the original stood down. Standing
    one down that nothing replaced would take behaviour away for nothing,
    so only the replaced ones are touched.
    """
    import tempfile

    from .ai import (
        RANDOMIZER_RULES_MARKER,
        TRIGGER_DIFFICULTIES,
        TRIGGER_OWNER,
        TRIGGER_TYPES,
        ai_house_code,
        installed_ai_sections,
        remove_staged_ai_file,
        side_number,
        stage_ai_file,
        taskforce_units,
    )
    from .options import read_ini_sections

    sections = installed_ai_sections()
    read_valid = bool(
        sections
        and len(sections.get(TRIGGER_TYPES) or {}) > 100
        and len(sections.get('TaskForces') or {}) > 100
        and side_number('GDI') == 1
        and side_number('FourthSide') == 4
    )

    clones = {'GGI': 'MOLGGI'}
    code = ai_house_code(
        [('Europeans', 1, clones), ('Guild1', 4, {})], sections=sections
    )
    rows = code.get(TRIGGER_TYPES) or {}
    stood_down = {
        key for key in rows if key in (sections.get(TRIGGER_TYPES) or {})
    }
    copies = {key: rows[key] for key in rows if key not in stood_down}
    forces = [
        values for name, values in code.items()
        if name not in {TRIGGER_TYPES, 'TaskForces', 'TeamTypes'}
        and any(str(key).isdigit() for key in values)
    ]
    code_valid = bool(
        forces
        # Every copied task force asks for the copy rather than the unit.
        and any(
            unit == 'MOLGGI'
            for values in forces
            for _count, unit in taskforce_units(values).values()
        )
        and not any(
            unit == 'GGI'
            for values in forces
            for _count, unit in taskforce_units(values).values()
        )
        # A copy belongs to one house, and it is live.
        and copies
        and all(
            row.split(',')[TRIGGER_OWNER] in {'Europeans', 'Guild1'}
            for row in copies.values()
        )
        # Live on at least one difficulty: a trigger the file had already
        # switched off is not copied at all.
        and all(
            any(
                row.split(',')[slot] != '0' for slot in TRIGGER_DIFFICULTIES
            )
            for row in copies.values()
        )
        # Nothing the file already had is touched. Standing a trigger down
        # only removed an attack the house was still making: a team carries
        # no owner, so its original cannot be stood down for one house, and
        # a match played that way produced an ally that built defences and
        # attacked almost never.
        and not stood_down
        # A house that bought nothing takes nothing away.
        and not ai_house_code([('Guild1', 4, {})], sections=sections)
    )

    with tempfile.TemporaryDirectory(prefix='mo-ai-') as directory:
        target = Path(directory) / 'aimo.ini'
        staged = stage_ai_file(code, path=target)
        written = read_ini_sections(target) if staged else {}
        first = (
            target.read_text(encoding='utf-8', errors='ignore').splitlines()[:1]
        )
        stage_valid = bool(
            staged
            # A complete file, because the game folder outranks the archives.
            and len(written) >= len(sections)
            and first and first[0].startswith(RANDOMIZER_RULES_MARKER)
            # Every trigger the file had, still exactly as it had it.
            and all(
                written[TRIGGER_TYPES][key] == row
                for key, row in (sections.get(TRIGGER_TYPES) or {}).items()
            )
            # And it is ours to remove, which is why it carries the marker.
            and remove_staged_ai_file(target)
            and not target.exists()
        )
        # A file somebody else wrote is neither ours to overwrite nor ours
        # to delete: the AI a submod ships is its own.
        stray = Path(directory) / 'someone else.ini'
        stray.write_text('[General]\n', encoding='utf-8')
        stage_valid = bool(
            stage_valid
            and not remove_staged_ai_file(stray)
            and stage_ai_file(code, path=stray) is None
            and stray.read_text(encoding='utf-8') == '[General]\n'
        )

    return {
        'skirmish_ai_file_read': read_valid,
        'skirmish_ai_code_valid': code_valid,
        'skirmish_ai_staging_valid': stage_valid,
    }


def _offer():
    from .model import BattleOffer

    return BattleOffer(
        map_path='self-check.map',
        map_name='Self Check',
        enemy_countries=(6,),
        handicap=1,
        seed='SELF-CHECK',
        ally=True,
        challenge=False,
    )


def _shop_checks():
    from .model import UpgradePurchase
    from .rules import unit_rules
    from .shop import (
        BATTLE_REWARD,
        REWARD_PER_TIER,
        STARTING_ORE,
        Upgrade,
        ally_shopping,
        battle_reward,
        country_upgrades,
        owned_stacks,
        purchase_labels,
        purchase_stacks,
        shelf_for,
    )
    from .transitions import (
        buy_upgrade,
        record_defeat,
        run_progress_text,
        start_run,
    )

    # Fixed by the tier the battle was fought in, and doubled for a
    # challenge. Never by score: a score can be farmed by dragging a won
    # battle out, and the difficulty is not something to grind around.
    # The warmup is fought with what you have: no shop, no life at stake,
    # and it can be stepped past. And the ally is equipped before the first
    # shot rather than after the first victory.
    from .model import WARMUP_BATTLE
    from .progression import is_warmup
    from .transitions import skip_warmup

    opening = start_run(
        run_id='warmup-check', seed='WARMUP', player_country=0,
        ally_country=3, ally_roster='USSR',
    )
    fought = replace(
        opening, offers=(_offer(),), committed_offer=0,
    )
    try:
        buy_upgrade(opening, Upgrade(
            unit='GGI', buff_type='speed', name='x', description='',
            price=1, limit=1,
        ))
        warmup_shops = True
    except SkirmishTransitionError:
        warmup_shops = False
    warmup_valid = bool(
        opening.battle == WARMUP_BATTLE
        and opening.warmup
        and is_warmup(opening.battle)
        and not opening.challenge_battle
        # The ally has already spent its opening Ore.
        and opening.ally_purchases
        and opening.ally_coins < STARTING_ORE
        # Nothing is bought during it and nothing is lost by losing it.
        and not warmup_shops
        and record_defeat(fought).lives_left == fought.lives_left
        # And it can be stepped past, which starts the run at battle one.
        and skip_warmup(opening).battle == WARMUP_BATTLE + 1
        and not skip_warmup(opening).warmup
    )

    # Three battles that differ only in which map they are on is a
    # shuffle, not a choice. Two of the three ask for something and pay
    # for the asking.
    from .progression import BONUSES, offer_bonuses

    early = offer_bonuses(1)
    late = offer_bonuses(16)
    bonus_valid = bool(
        # The first offer is the plain one, and it is the only plain one.
        early[0].percent == 0
        and all(bonus.percent > 0 for bonus in early[1:])
        # What they ask for is a harder battle, not a different map.
        and any(bonus.extra_enemies for bonus in early)
        and any(bonus.alone for bonus in early)
        # From the tier that fields three, the dearest asks for a better
        # opponent rather than another one.
        and late[-1].mental and not early[-1].mental
        and late[-1].percent > early[-1].percent
        # The warmup asks for nothing.
        and all(bonus.percent == 0 for bonus in offer_bonuses(0))
        # And the Ore follows the asking.
        and battle_reward(1, bonus_percent=0) == BATTLE_REWARD
        and battle_reward(1, bonus_percent=40)
        > battle_reward(1, bonus_percent=0)
        and battle_reward(5, challenge=True, bonus_percent=0)
        == BATTLE_REWARD * 2
    )

    # The ninth tier does not end the run: it starts it again, harder.
    from .model import BATTLES_PER_TIER as _per_tier, TIER_COUNT
    from .transitions import enter_nightmare

    last = replace(
        start_run(
            run_id='nightmare-check', seed='NIGHTMARE', player_country=0,
            ally_country=3,
        ),
        battle=TIER_COUNT * _per_tier,
        coins=900,
        purchases=(UpgradePurchase('GGI', 'speed', 1),),
        used_challenge_maps=('a.map', 'b.map'),
        won_battles=40,
    )
    again = enter_nightmare(last, ally_country='USSR')
    nightmare_valid = bool(
        again.nightmare == 1
        and again.battle == 1
        # Both your armies start again with nothing bought and the opening
        # Ore, and the ally is equipped before the first shot.
        and again.coins == STARTING_ORE
        and not again.purchases
        and again.ally_purchases
        and again.ally_coins < STARTING_ORE
        # What the run has been through is not forgotten.
        and again.won_battles == last.won_battles
        and again.used_challenge_maps == last.used_challenge_maps
        and again.lives_left == last.lives_left
        # And it says which time round it is.
        and 'Nightmare 1' in run_progress_text(again)
        and enter_nightmare(again).nightmare == 2
    )

    # A run that ends still exists on the board, with what it did.
    from tempfile import TemporaryDirectory as _TempDir

    from .leaderboard import (
        BoardEntry,
        board_row,
        load_board,
        record_finished_run,
        record_run,
    )
    from .results import HouseResult
    from .stats import RunStats, record_battle, stats_lines

    fresh = record_battle(
        RunStats(),
        won=True,
        result=HouseResult(
            name='Commander', won=True, scheme=1, lost=15, kills=120,
            built=104, score=106946,
        ),
        offer=_offer(),
        reward=175,
        tier=3,
        nightmare=1,
    )
    quit_early = record_battle(fresh, won=False, tier=2, nightmare=1)
    with _TempDir(prefix='mo-board-') as _board_dir:
        board_file = Path(_board_dir) / 'board.dat'
        entry = BoardEntry(
            run_id='r', seed='SEED', army='Allies', ally='Soviets',
            started='2026-09-06', ended='2026-09-06', outcome='Out of lives',
            battle=13, tier=3, nightmare=1, stats=quit_early,
        )
        record_run(entry, board_file)
        further = record_run(
            replace(entry, run_id='r2', tier=5, nightmare=2), board_file
        )
        # The two run-end paths -- giving up and running out of lives --
        # both describe the run through one reading now, which is what
        # keeps a run ended from a screen and a run ended from a window
        # on the board as the same row.
        described = record_finished_run(
            replace(
                start_run(
                    run_id='ended-check', seed='ENDED', player_country=0,
                    ally_country=3, created='2026-09-06',
                ),
                battle=7, stats=quit_early,
            ),
            'Gave up',
            ended='2026-09-06',
            path=board_file,
        )
        ended = next(item for item in described if item.run_id == 'ended-check')
        player = country_by_index(0)
        board_valid = bool(
            # One battle in, and the totals are the game's own numbers.
            fresh.battles == 1 and fresh.won == 1
            and fresh.kills == 120 and fresh.score == 106946
            and fresh.best_score == 106946 and fresh.ore_earned == 175
            and fresh.bonus_battles == 0
            # A battle closed before it ended still counts as a battle and
            # as a defeat, and adds kills nobody made.
            and quit_early.battles == 2 and quit_early.lost == 1
            and quit_early.kills == fresh.kills
            # How far it got is where it reached, not where it fell back to.
            and quit_early.best_tier == 3 and quit_early.best_nightmare == 1
            # The board keeps them furthest first, and reads back.
            and len(further) == 2
            and further[0].run_id == 'r2'
            and load_board(board_file)[0].stats.kills == 120
            and len(board_row(entry)) == 8
            and len(stats_lines(quit_early)) == 8
            # A run ended anywhere lands on the board wearing the country
            # it fought as, not the number it was stored under.
            and ended.outcome == 'Gave up'
            and ended.battle == 7
            and ended.army == (player.display if player else '0')
            and ended.stats.battles == quit_early.battles
        )

    reward_valid = bool(
        battle_reward(1) == BATTLE_REWARD
        and battle_reward(4) == BATTLE_REWARD
        and battle_reward(6) == BATTLE_REWARD + REWARD_PER_TIER
        and battle_reward(11) == BATTLE_REWARD + 2 * REWARD_PER_TIER
        and battle_reward(5, challenge=True) == BATTLE_REWARD * 2
    )

    # Past the warmup: nothing is bought during it, so a shop check has
    # to stand where a shop stands.
    run = replace(
        start_run(
            run_id='shop-check',
            seed='SHOP-CHECK',
            player_country=0,
            ally_country=3,
        ),
        battle=1,
    )
    cheap = Upgrade(
        unit='GGI', buff_type='speed', name='Cheap', description='',
        price=50, limit=2,
    )
    dear = Upgrade(
        unit='GGI', buff_type='health', name='Dear', description='',
        price=STARTING_ORE + 1, limit=5,
    )
    bought = buy_upgrade(buy_upgrade(run, cheap), cheap)
    try:
        buy_upgrade(bought, cheap)
        limit_refused = False
    except SkirmishTransitionError:
        limit_refused = True
    try:
        buy_upgrade(run, dear)
        price_refused = False
    except SkirmishTransitionError:
        price_refused = True
    purchase_valid = bool(
        bought.coins == STARTING_ORE - 2 * cheap.price
        and owned_stacks(bought.purchases, 'GGI', 'speed') == 2
        and limit_refused
        and price_refused
        # A second buff on the same unit is its own purchase.
        and len(purchase_stacks(bought.purchases, dear)) == 2
    )

    # An ally spends what it has, on its own faction's list, and stops when
    # nothing left is affordable.
    ally_purchases, ally_left = ally_shopping(run, 'USSR', 400)
    soviet = {upgrade.key for upgrade in country_upgrades('USSR')}
    allied = {upgrade.key for upgrade in country_upgrades('UnitedStates')}
    ally_valid = bool(
        ally_purchases
        and all(purchase.key in soviet for purchase in ally_purchases)
        and not any(
            purchase.key in allied - soviet for purchase in ally_purchases
        )
        and 0 <= ally_left < 400
    )

    # The shelf is the run's own: same seed and battle, same shelf, and
    # nothing on it belongs to another faction. And it holds still when it
    # is bought from -- a shelf that only held what you had not bought
    # would deal six new offers the moment you took one.
    from .shop import draw_shelf
    from .transitions import offer_battles

    offered = offer_battles(
        run, run.offers or (_offer(),),
        shelf=draw_shelf(run, 'UnitedStates'),
    )
    shelf = shelf_for(offered, 'UnitedStates')
    taken = buy_upgrade(offered, shelf[0])
    shelf_valid = bool(
        shelf
        and shelf == shelf_for(offered, 'UnitedStates')
        and all(upgrade.key in allied for upgrade in shelf)
        and shelf != shelf_for(
            replace(offered, battle=2, shelf=()), 'UnitedStates'
        )
        # Bought, and still exactly where it was.
        and shelf_for(taken, 'UnitedStates') == shelf
        and owned_stacks(taken.purchases, shelf[0].unit, shelf[0].buff_type)
        # Won, and the six are drawn again.
        and not replace(taken, shelf=()).shelf
    )

    # A side is not an army. The three Allied countries field different
    # rosters, and an upgrade for a unit the player's own country cannot
    # build is Ore spent on nothing.
    from .ownership import buildable_units, country_builds

    def sold_units(country):
        # A shelf row can stand for several units; what is compared here is
        # the units, so a group is opened first.
        from .ownership import expand_group

        return {
            unit
            for upgrade in country_upgrades(country)
            for unit in expand_group(upgrade.unit, country)
        }

    united = sold_units('UnitedStates')
    pacific = sold_units('Pacific')
    soviet_units = sold_units('USSR')
    country_valid = bool(
        united and pacific
        # Ownership: the Stormchild is the United States', the tier two
        # buildings are one per country.
        and country_builds('STORM', 'UnitedStates')
        and not country_builds('STORM', 'Pacific')
        and country_builds('GASCPF', 'Pacific')
        and not country_builds('GASCPF', 'UnitedStates')
        # The prerequisite chain: a unit gated by another country's tier two
        # building is not this country's, however the Owner list reads.
        and country_builds('HOWI', 'Pacific')
        and not country_builds('HOWI', 'UnitedStates')
        and 'HOWI' in pacific and 'HOWI' not in united
        # A campaign unit is not a skirmish unit. The Future Tank X-0 and
        # Sammy Stallion sit above the match's tech level, with no owner
        # and no prerequisite, because a mission hands them over.
        and not country_builds('AHVYBOT', 'UnitedStates')
        and not country_builds('STLN', 'UnitedStates')
        and 'AHVYBOT' not in united and 'STLN' not in united
        # But the Construction Yard, TechLevel=-1 because an MCV deploys
        # into one, must not take the whole tech tree down with it.
        and country_builds('GGI', 'UnitedStates')
        and country_builds('TANY', 'UnitedStates')
        # And the sides do not bleed into one another.
        # No unit is on two sides' shelves. The one that was -- the
        # stolen-tech Cyborg Commando, which everybody can steal -- is
        # excluded outright now.
        and not (united & soviet_units)
        and 'GGI' in united and 'GGI' in pacific
    )

    # A hero is priced off its own cost here. The campaign shop sells the
    # only Tanya a run will ever own, flat and with a premium on top; a
    # skirmish builds one in a barracks, so what improving one costs is
    # what improving anything of that cost costs.
    from randomizer.shop.economy import run_buff_price
    from randomizer.shop.unit_pricing import unit_pricing_traits
    from .shop import upgrade_price

    hero_valid = bool(
        unit_pricing_traits('TANY').get('unique')
        and upgrade_price('TANY') < run_buff_price('TANY')
        # And within a few Ore of a unit that costs about the same and is
        # nobody's hero.
        and abs(upgrade_price('TANY') - upgrade_price('CARRIER')) <= 10
        # Everything that was never special is untouched.
        and upgrade_price('GGI') == run_buff_price('GGI')
        and upgrade_price('FORTRESS') == run_buff_price('FORTRESS')
    )

    # What an infiltration might bring is bought as one row, not as one row
    # per unit: a run cannot decide to build these and cannot choose which
    # of them it gets, so five separate price tags would be five lottery
    # tickets. One purchase becomes one copy per member.
    from .clones import house_clone_code
    from .model import UpgradePurchase
    from .ownership import (
        STOLEN_TECH_GROUP,
        excluded_units,
        expand_group,
        stolen_tech_units,
    )

    members = stolen_tech_units('UnitedStates')
    bundles = [
        upgrade for upgrade in country_upgrades('UnitedStates')
        if upgrade.unit == STOLEN_TECH_GROUP
    ]
    stolen_valid = bool(
        # Read from the game option file, because that is where these units
        # are described at all -- the rules do not carry them.
        len(members) >= 2
        # And what the mode has excluded is excluded here too.
        and not (set(members) & excluded_units())
        and bundles
        # None of them is on the shelf in its own right.
        and not any(
            upgrade.unit in members
            for upgrade in country_upgrades('UnitedStates')
        )
        # A bundle costs more than any one member's own upgrade would.
        and all(
            upgrade.price
            > max(
                (
                    item.price for item in country_upgrades('UnitedStates')
                    if item.unit != STOLEN_TECH_GROUP
                    and item.buff_type == upgrade.buff_type
                ),
                default=0,
            ) / 2
            for upgrade in bundles
        )
        # And one purchase reaches every member.
        and set(expand_group(STOLEN_TECH_GROUP, 'UnitedStates')) == set(members)
        # Every member, and the other forms of the ones that deploy: a
        # copy that packs up has to become another copy.
        and set(members) <= set(
            house_clone_code(
                (UpgradePurchase(STOLEN_TECH_GROUP, 'range', 2),),
                'UnitedStates', prefix='MOP',
            )[1]
        )
        # A country's stolen tech is its own side's.
        and not (set(members) & set(stolen_tech_units('USSR')))
    )

    # A unit that deploys is two sections naming each other, and a copy
    # has to name copies or deploying would hand back the original the
    # buyer is shut out of.
    from randomizer.rewards.catalogue import BUFF_TARGETS as _targets_now
    from randomizer.rewards.roster import (
        _installed_sections as _sections_now,
    )
    from .clones import clonable as _clonable, form_closure

    installed_now = _sections_now()
    pair = form_closure('AHVYBOT2', installed_now)
    _pair_sections, pair_built = house_clone_code(
        (UpgradePurchase('AHVYBOT2', 'speed', 3),), 'Pacific', prefix='MOP',
    )
    forms_valid = bool(
        len(pair) == 2
        and _clonable('AHVYBOT2', installed_now, _targets_now)
        and set(pair) == set(pair_built)
        # The copy deploys into the other copy, and both originals are shut
        # out of the house that bought them.
        and _pair_sections[pair_built['AHVYBOT2']]['Convert.Deploy']
        == pair_built['AHVYBOT2B']
        and all(
            _pair_sections[form]['ForbiddenHouses'] == 'Pacific'
            for form in pair
        )
    )

    # A price tag is no use without what it buys, so every upgrade says
    # what one stack does in the campaign shop's own words rather than in
    # the internal name of the buff.
    effect_valid = bool(
        shelf
        and all(
            upgrade.effect
            and upgrade.effect != upgrade.buff_type.replace('_', ' ')
            for upgrade in country_upgrades('UnitedStates')
        )
        # And what an army owns can be named, for the ally that shops unseen.
        and purchase_labels(bought.purchases, 'UnitedStates')
        == ('Guardian GI Mobility I x2',)
    )

    # Nothing on any faction's list takes Ore without changing a unit. The
    # campaign grants veterancy on the house and raises a build limit by
    # building a clone; neither reaches a skirmish, so neither is sold.
    from randomizer.rewards.catalogue import BUFF_TARGETS
    from randomizer.rewards.roster import _installed_sections

    sections = _installed_sections()
    from .ownership import expand_group as _expand

    # A row that stands for several units keeps its promise when any of
    # them takes the stat: one of the stolen-tech units carries nobody, and
    # a passenger upgrade that reaches the other four is still an upgrade.
    sold = [
        (_expand(upgrade.unit, country), upgrade.buff_type)
        for country in ('UnitedStates', 'USSR', 'PsiCorps', 'Guild1')
        for upgrade in country_upgrades(country)
    ]
    delivers_valid = bool(
        sold
        and not any(
            buff_type in {'veteran', 'build_limit', 'building_limit'}
            for _units, buff_type in sold
        )
        and all(
            any(
                unit_rules(unit, buff_type, 1, sections, BUFF_TARGETS)
                for unit in units
            )
            for units, buff_type in sold
        )
    )

    # A purchase becomes an edit on the unit's own section, read off the
    # unit as this installation has it.
    installed = {
        'FIXTUNIT': {'Speed': '6', 'Strength': '200', 'Primary': 'FIXTGUN'},
        'FIXTGUN': {'Damage': '50', 'ROF': '40', 'Range': '5'},
    }
    targets = {
        'FIXTUNIT': {
            'speed': 6, 'strength': 200, 'category': 'units',
            'weapons': {'FIXTGUN': {'damage': 50, 'rof': 40, 'range': 5}},
        },
    }
    speed_rules = unit_rules('FIXTUNIT', 'speed', 3, installed, targets)
    damage_rules = unit_rules('FIXTUNIT', 'damage', 3, installed, targets)
    rules_valid = bool(
        set(speed_rules) == {'FIXTUNIT'}
        and int(speed_rules['FIXTUNIT']['Speed']) > 6
        and set(damage_rules) == {'FIXTGUN'}
        and int(damage_rules['FIXTGUN']['Damage']) > 50
        # A unit the catalogue does not describe is not written about.
        and unit_rules('NOSUCH', 'speed', 1, installed, targets) == {}
    )

    return {
        'skirmish_warmup_valid': warmup_valid,
        'skirmish_offer_bonuses_valid': bonus_valid,
        'skirmish_nightmare_valid': nightmare_valid,
        'skirmish_run_board_valid': board_valid,
        'skirmish_battle_reward_valid': reward_valid,
        'skirmish_purchase_valid': purchase_valid,
        'skirmish_ally_shops_alone_valid': ally_valid,
        'skirmish_shelf_valid': shelf_valid,
        'skirmish_shelf_is_one_country': country_valid,
        'skirmish_stolen_tech_is_one_row': stolen_valid,
        'skirmish_hero_priced_by_cost': hero_valid,
        'skirmish_linked_forms_copied': forms_valid,
        'skirmish_upgrade_effect_valid': effect_valid,
        'skirmish_upgrade_delivers_valid': delivers_valid,
        'skirmish_upgrade_rules_valid': rules_valid,
    }

def validate_skirmish_contract():
    """Return the skirmish self-check rows, plus what the pools hold."""
    report = {}
    report.update(_spawn_checks())
    report.update(_result_checks())
    report.update(_map_reader_checks())
    report.update(_country_checks())
    report.update(_run_checks())
    report.update(_table_checks())
    report.update(_challenge_checks())
    report.update(_option_checks())
    report.update(_clone_checks())
    report.update(_ai_checks())
    report.update(_shop_checks())
    report['skirmish_map_pools'] = (
        summarize_map_pools()
        if STANDARD_POOL_DIR.is_dir() or CHALLENGE_POOL_DIR.is_dir()
        else {}
    )
    return report
