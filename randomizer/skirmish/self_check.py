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

        run = start_run(
            run_id='check-run',
            seed='SKIRMISH-CHECK',
            player_country=0,
            ally_country=3,
            created='2026-09-06',
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
    # them in order as its tiers rise.
    level_valid = bool(
        challenge_level(5) == AI_DIFFICULTY_EASY
        and challenge_level(10) == AI_DIFFICULTY_MEDIUM
        and challenge_level(15) == AI_DIFFICULTY_HARD
        and challenge_level(40) == AI_DIFFICULTY_HARD
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
        faction_upgrades,
        owned_stacks,
        purchase_labels,
        purchase_stacks,
        shelf_for,
    )
    from .transitions import buy_upgrade, start_run

    # Fixed by the tier the battle was fought in, and doubled for a
    # challenge. Never by score: a score can be farmed by dragging a won
    # battle out, and the difficulty is not something to grind around.
    reward_valid = bool(
        battle_reward(1) == BATTLE_REWARD
        and battle_reward(4) == BATTLE_REWARD
        and battle_reward(6) == BATTLE_REWARD + REWARD_PER_TIER
        and battle_reward(11) == BATTLE_REWARD + 2 * REWARD_PER_TIER
        and battle_reward(5, challenge=True) == BATTLE_REWARD * 2
    )

    run = start_run(
        run_id='shop-check',
        seed='SHOP-CHECK',
        player_country=0,
        ally_country=3,
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
    ally_purchases, ally_left = ally_shopping(run, 'Soviets', 400)
    soviet = {upgrade.key for upgrade in faction_upgrades('Soviets')}
    allied = {upgrade.key for upgrade in faction_upgrades('Allies')}
    ally_valid = bool(
        ally_purchases
        and all(purchase.key in soviet for purchase in ally_purchases)
        and not any(
            purchase.key in allied - soviet for purchase in ally_purchases
        )
        and 0 <= ally_left < 400
    )

    # The shelf is the run's own: same seed and battle, same shelf, and
    # nothing on it belongs to another faction.
    shelf = shelf_for(run, 'Allies')
    shelf_valid = bool(
        shelf
        and shelf == shelf_for(run, 'Allies')
        and all(upgrade.key in allied for upgrade in shelf)
        and shelf != shelf_for(replace(run, battle=2), 'Allies')
    )

    # A price tag is no use without what it buys, so every upgrade says
    # what one stack does in the campaign shop's own words rather than in
    # the internal name of the buff.
    effect_valid = bool(
        shelf
        and all(
            upgrade.effect
            and upgrade.effect != upgrade.buff_type.replace('_', ' ')
            for upgrade in faction_upgrades('Allies')
        )
        # And what an army owns can be named, for the ally that shops unseen.
        and purchase_labels(bought.purchases, 'Allies')
        == ('Guardian GI Mobility I x2',)
    )

    # Nothing on any faction's list takes Ore without changing a unit. The
    # campaign grants veterancy on the house and raises a build limit by
    # building a clone; neither reaches a skirmish, so neither is sold.
    from randomizer.rewards.catalogue import BUFF_TARGETS
    from randomizer.rewards.roster import _installed_sections

    sections = _installed_sections()
    sold = [
        upgrade for side in ('Allies', 'Soviets', 'Epsilon', 'Foehn')
        for upgrade in faction_upgrades(side)
    ]
    delivers_valid = bool(
        sold
        and not any(
            upgrade.buff_type in {'veteran', 'build_limit', 'building_limit'}
            for upgrade in sold
        )
        and all(
            unit_rules(
                upgrade.unit, upgrade.buff_type, 1, sections, BUFF_TARGETS
            )
            for upgrade in sold
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
        'skirmish_battle_reward_valid': reward_valid,
        'skirmish_purchase_valid': purchase_valid,
        'skirmish_ally_shops_alone_valid': ally_valid,
        'skirmish_shelf_valid': shelf_valid,
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
    report.update(_challenge_checks())
    report.update(_shop_checks())
    report['skirmish_map_pools'] = (
        summarize_map_pools()
        if STANDARD_POOL_DIR.is_dir() or CHALLENGE_POOL_DIR.is_dir()
        else {}
    )
    return report
