"""Shop Mode balance harness.

Answers the questions that were previously settled by argument: how fast the
economy grows, whether Ore keeps pace with what the shop charges, how deep a
run gets, and how many runs a permanent upgrade actually costs.

Two kinds of output, and the difference matters:

* The **economy report** is fact. It reads the same functions the game uses,
  so every figure is exactly what a player would be paid or charged.
* The **run report** depends on a win-probability model, because nothing in
  the repository knows how likely a player is to win a mission. The model is
  a declared assumption (see WinModel), not a prediction. Use it to compare
  settings against each other, not to forecast a real player.

    python tools/shop_balance_simulator.py
    python tools/shop_balance_simulator.py --runs 2000 --set shop_stage_length=2
    python tools/shop_balance_simulator.py --economy-only --tiers 8
"""
from __future__ import annotations

import argparse
import random
import statistics
from collections import Counter
import sys
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from randomizer.rewards.enemy_scaling import ENEMY_SCALING_BUFF_STACK_LIMITS
from randomizer.shop.config import RUN_PACING_SETTINGS, SHOP_CONFIG, run_shop_config
from randomizer.shop.economy import mission_reward, starting_run_coins
from randomizer.shop.missions import (
    difficulty_stage,
    enemy_buffs_for_stage,
    is_challenge_stage,
)
from randomizer.shop.model import MissionEconomyClass, ShopModeConfig
from randomizer.shop.modifiers import (
    format_difficulty,
    pacing_difficulty,
    pacing_gem_scale_percent,
)
from randomizer.shop.transitions import maximum_run_lives, unlocked_enemy_buff_ids

CLASSES = (
    MissionEconomyClass.ACT_1,
    MissionEconomyClass.ACT_2,
    MissionEconomyClass.OPERATION,
    MissionEconomyClass.FINALE,
)


class Challenge:
    """Stand-in for a challenge modifier, carrying no bonus of its own."""

    challenge = True
    bonus_run_coins = 0
    bonus_meta_coins = 0


@dataclass(frozen=True)
class WinModel:
    """How likely a mission is to be won. An assumption, not a measurement.

    Each permanent enemy buff the run has collected removes
    ``per_enemy_buff_percent`` from the win chance, which is what makes an
    endless run eventually end. ``floor_percent`` keeps a saturated run from
    becoming strictly impossible.
    """

    base_percent: int = 85
    per_enemy_buff_percent: float = 2.5
    challenge_penalty_percent: int = 15
    floor_percent: int = 15

    # Known blind spot: Ore is not an input. A setting that only starves the
    # run shop will look free here even where a player would feel it.

    def chance(self, enemy_buffs: int, challenge: bool) -> float:
        chance = self.base_percent - enemy_buffs * self.per_enemy_buff_percent
        if challenge:
            chance -= self.challenge_penalty_percent
        return max(self.floor_percent, chance) / 100


def _reward(config, stage, economy_class, challenge, settings):
    return mission_reward(
        economy_class,
        mission_modifier=Challenge() if challenge else None,
        stage=stage,
        gem_scale_percent=pacing_gem_scale_percent(settings),
        config=config,
    )


def economy_report(config: ShopModeConfig, settings, tiers: int) -> None:
    length = config.stage_length
    print('== Ekonomi (gercek deger, model yok) ==')
    print(f'{"tier":>4} {"gorev":>8}  ' + ' '.join(
        f'{cls.value:>11}' for cls in CLASSES) + f'{"challenge":>13}')
    for tier in range(1, tiers + 1):
        stage = (tier - 1) * length + 1
        cells = []
        for cls in CLASSES:
            reward = _reward(config, stage, cls, False, settings)
            cells.append(f'{reward.run_coins:>5}o {reward.meta_coins:>4}g')
        challenge = _reward(
            config, tier * length, MissionEconomyClass.ACT_1, True, settings
        )
        span = f'{stage}-{tier * length}'
        print(f'{tier:>4} {span:>8}  ' + ' '.join(cells)
              + f'{challenge.run_coins:>7}o {challenge.meta_coins:>4}g')

    print()
    print('== Bir tier tam kazanildiginda kazanc ==')
    print(f'{"tier":>4} {"Ore":>8} {"Gem":>8} {"kalici dusman buff":>20}')
    for tier in range(1, tiers + 1):
        ore = gems = 0
        for offset in range(length):
            stage = (tier - 1) * length + 1 + offset
            challenge = is_challenge_stage(stage, config)
            reward = _reward(
                config, stage, MissionEconomyClass.ACT_2, challenge, settings
            )
            ore += reward.run_coins
            gems += reward.meta_coins
        buffs = sum(
            enemy_buffs_for_stage(index * length, config)
            for index in range(1, tier + 1)
        )
        print(f'{tier:>4} {ore:>8} {gems:>8} {buffs:>20}')


def purchasing_power_report(config, settings, tiers: int) -> None:
    """What share of the offered shop a tier's Ore can actually buy.

    Fact, not a model. Measured against the whole slate on offer -- the
    stocked units, powers, and upgrades of one rotation -- rather than a
    single median item, because the shop stocks many things at once. A figure
    under 100% means Ore is still a real constraint and the player has to
    choose; over 100% means a tier can clear the shelves.

    It counts only what is for sale. Every victory also hands over a unit and
    a couple of upgrades for free, so a run's real gain per mission is higher
    than any Ore figure here.
    """
    def median(values):
        values = sorted(values)
        return values[len(values) // 2] if values else 0

    unit = median(
        price.run_access for price in config.unit_target_prices.values()
        if price.run_access
    )
    unit_buff = median(
        price.run_buff for price in config.unit_target_prices.values()
        if price.run_buff
    )
    power = median(
        price.run_access for price in config.power_target_prices.values()
        if price.run_access
    )
    slate = config.unit_inventory_size * unit
    slate += config.power_inventory_size * power
    slate += config.upgrade_inventory_size * unit_buff
    print()
    print(f'== Satin alma gucu (bir turluk stok ~{slate}o: '
          f'{config.unit_inventory_size} birim, '
          f'{config.power_inventory_size} guc, '
          f'{config.upgrade_inventory_size} upgrade) ==')
    print(f'{"tier":>4} {"tier Ore":>9} {"stogun %":>10}'
          f'{"gorev Ore":>12}{"alim/gorev":>12}')
    for tier in range(1, tiers + 1):
        ore = sum(
            _reward(
                config,
                (tier - 1) * config.stage_length + 1 + offset,
                MissionEconomyClass.ACT_2,
                is_challenge_stage(
                    (tier - 1) * config.stage_length + 1 + offset, config
                ),
                settings,
            ).run_coins
            for offset in range(config.stage_length)
        )
        per_mission = ore / config.stage_length
        print(f'{tier:>4} {ore:>9} {100 * ore / slate:>9.0f}%'
              f'{per_mission:>12.0f}{per_mission / unit:>12.1f}')
    print('   not: stok her gorevde yenilenir, yani gercek harcama tavani'
          ' bundan yuksek; ustelik her zafer 1 birim + '
          f'{config.mission_upgrade_reward_count} upgrade i bedava verir')


def career_report(config, settings, model, careers, runs_each, seed):
    """Spend Gems between runs and report how fast the profile fills up.

    Model-dependent twice over: it inherits the win model, and it assumes a
    player buys the cheapest upgrade level they can afford. Read it for the
    shape of progression, not for exact run counts.
    """
    rng = random.Random(f'{seed}:career')
    ladders = {
        upgrade_id: list(definition.prices)
        for upgrade_id, definition in config.permanent_upgrades.items()
        if definition.purchasable
    }
    total_levels = sum(len(prices) for prices in ladders.values())
    first_owned_run, completed = Counter(), []
    for _ in range(careers):
        owned, gems = Counter(), 0
        finished_at = None
        for run_index in range(1, runs_each + 1):
            gems += _play_one_run(config, settings, model, rng)
            while True:
                affordable = [
                    (prices[owned[key]], key)
                    for key, prices in ladders.items()
                    if owned[key] < len(prices)
                    and prices[owned[key]] <= gems
                ]
                if not affordable:
                    break
                price, key = min(affordable)
                gems -= price
                owned[key] += 1
                if owned[key] == 1:
                    first_owned_run[key] = first_owned_run.get(key, 0) or run_index
            if sum(owned.values()) == total_levels and finished_at is None:
                finished_at = run_index
        completed.append(finished_at or runs_each + 1)
    print()
    print(f'== Kariyer: {careers} oyuncu x {runs_each} run ==')
    median = sorted(completed)[len(completed) // 2]
    print(f'tum yukseltmeler ({total_levels} seviye) tamamlandi: '
          f'medyan {median} run'
          + ('' if median <= runs_each else ' (sinira takildi)'))


def _play_one_run(config, settings, model, rng):
    stage, lives, gems, buffs = 1, maximum_run_lives(None, config), 0, 0
    while lives > 0 and stage <= 200:
        challenge = is_challenge_stage(stage, config)
        if rng.random() < model.chance(buffs, challenge):
            gems += _reward(
                config, stage, MissionEconomyClass.ACT_2, challenge, settings
            ).meta_coins
            if challenge:
                buffs += enemy_buffs_for_stage(stage, config)
            stage += 1
        else:
            lives -= 1
    return gems


def upgrade_report(config: ShopModeConfig, gems_per_tier: int) -> None:
    print()
    print('== Kalici yukseltmeler: ilk seviye maliyeti ==')
    print(f'{"yukseltme":<26}{"1. seviye":>10}{"tam merdiven":>14}'
          f'{"~tier (1. sv)":>15}')
    rows = []
    for upgrade_id, definition in config.permanent_upgrades.items():
        if not definition.purchasable:
            continue
        first = definition.prices[0]
        total = sum(definition.prices)
        rows.append((first, upgrade_id, definition.display_name, total))
    for first, _upgrade_id, name, total in sorted(rows):
        tiers = first / gems_per_tier if gems_per_tier else float('inf')
        print(f'{name:<26}{first:>10}{total:>14}{tiers:>15.1f}')


def simulate_runs(config, settings, model, runs, seed, cap_missions):
    """Play runs to death and report how deep they get."""
    rng = random.Random(seed)
    lives_total = maximum_run_lives(None, config)
    depths, gem_totals, ore_peaks, death_tiers = [], [], [], []
    for _ in range(runs):
        stage, lives, gems, ore = 1, lives_total, 0, starting_run_coins(config=config)
        buffs = 0
        while lives > 0 and stage <= cap_missions:
            challenge = is_challenge_stage(stage, config)
            if rng.random() < model.chance(buffs, challenge):
                reward = _reward(
                    config, stage, MissionEconomyClass.ACT_2, challenge, settings
                )
                gems += reward.meta_coins
                ore += reward.run_coins
                if challenge:
                    buffs += enemy_buffs_for_stage(stage, config)
                stage += 1
            else:
                lives -= 1
        depths.append(stage - 1)
        gem_totals.append(gems)
        ore_peaks.append(ore)
        death_tiers.append(difficulty_stage(max(1, stage - 1), config))

    def spread(values):
        values = sorted(values)
        return (
            f'{statistics.mean(values):>7.1f}'
            f'{values[len(values) // 2]:>8}'
            f'{values[int(len(values) * 0.9)]:>8}'
            f'{values[-1]:>8}'
        )

    print()
    print(f'== {runs} run (kazanma modeli: taban %{model.base_percent}, '
          f'buff basina -%{model.per_enemy_buff_percent:g}, '
          f'challenge -%{model.challenge_penalty_percent}) ==')
    print(f'{"olcum":<22}{"ortalama":>7}{"medyan":>8}{"p90":>8}{"en iyi":>8}')
    print(f'{"kazanilan gorev":<22}{spread(depths)}')
    print(f'{"ulasilan tier":<22}{spread(death_tiers)}')
    print(f'{"run basina Gem":<22}{spread(gem_totals)}')
    print(f'{"biriken Ore":<22}{spread(ore_peaks)}')
    return statistics.mean(gem_totals)


def run_sweep(args):
    """Tabulate one pacing setting across its configured range."""
    if args.sweep not in RUN_PACING_SETTINGS:
        raise SystemExit(
            f'Bilinmeyen ayar {args.sweep!r}. Secenekler: '
            + ', '.join(RUN_PACING_SETTINGS)
        )
    field, low, high = RUN_PACING_SETTINGS[args.sweep]
    step = 10 if 'percent' in args.sweep else 1
    model = WinModel(
        base_percent=args.base_win_percent,
        per_enemy_buff_percent=args.per_buff_percent,
    )
    print(f'== {args.sweep} taramasi ({args.runs} run/deger) ==')
    if args.sweep == 'shop_stage_income_percent':
        # Worth stating outright: the win model has no notion of Ore, so a
        # column that only moves Gems is telling you the difficulty score
        # moved, not that the run got harder to survive.
        print('   not: kazanma modeli Ore u hesaba katmaz; bu ayarin '
              'hayatta kalmaya etkisi olculmez')
    print(f'{"deger":>7}{"zorluk":>8}{"Gem%":>7}{"gorev":>8}{"tier":>7}'
          f'{"run Gem":>10}{"tier1 Ore":>11}')
    for value in range(low, high + 1, step):
        settings = {args.sweep: value}
        config = run_shop_config(
            type('Run', (), {'reward_settings': settings})(), SHOP_CONFIG
        )
        rng = random.Random(f'{args.seed}:{value}')
        gems = [
            _play_one_run(config, settings, model, rng)
            for _ in range(args.runs)
        ]
        depths = []
        for _ in range(args.runs):
            depths.append(_run_depth(config, model, random.Random(
                f'{args.seed}:depth:{value}:{len(depths)}')))
        tier_one_ore = sum(
            _reward(
                config, 1 + offset, MissionEconomyClass.ACT_2,
                is_challenge_stage(1 + offset, config), settings,
            ).run_coins
            for offset in range(config.stage_length)
        )
        print(f'{value:>7}{format_difficulty(pacing_difficulty(settings)):>8}'
              f'{pacing_gem_scale_percent(settings):>6}%'
              f'{statistics.mean(depths):>8.1f}'
              f'{statistics.mean(depths) / config.stage_length:>7.1f}'
              f'{statistics.mean(gems):>10.0f}{tier_one_ore:>11}')


def _run_depth(config, model, rng):
    stage, lives, buffs = 1, maximum_run_lives(None, config), 0
    while lives > 0 and stage <= 200:
        challenge = is_challenge_stage(stage, config)
        if rng.random() < model.chance(buffs, challenge):
            if challenge:
                buffs += enemy_buffs_for_stage(stage, config)
            stage += 1
        else:
            lives -= 1
    return stage - 1


def parse_overrides(pairs):
    settings = {}
    for pair in pairs:
        key, _, raw = pair.partition('=')
        if key not in RUN_PACING_SETTINGS:
            raise SystemExit(
                f'Bilinmeyen ayar {key!r}. Secenekler: '
                + ', '.join(RUN_PACING_SETTINGS)
            )
        settings[key] = int(raw)
    return settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=1000)
    parser.add_argument('--tiers', type=int, default=6)
    parser.add_argument('--seed', default='balance')
    parser.add_argument('--cap-missions', type=int, default=200)
    parser.add_argument('--economy-only', action='store_true')
    parser.add_argument('--base-win-percent', type=int, default=85)
    parser.add_argument('--per-buff-percent', type=float, default=2.5)
    parser.add_argument(
        '--set', action='append', default=[], metavar='KEY=VALUE',
        help='Run pacing override, e.g. --set shop_stage_length=2',
    )
    parser.add_argument(
        '--sweep', metavar='KEY',
        help='Compare one pacing setting across its whole range',
    )
    parser.add_argument('--careers', type=int, default=0,
                        help='Simulate this many players buying upgrades')
    parser.add_argument('--runs-each', type=int, default=60)
    args = parser.parse_args()

    if args.sweep:
        run_sweep(args)
        return

    settings = parse_overrides(args.set)
    config = run_shop_config(
        type('Run', (), {'reward_settings': settings})(), SHOP_CONFIG
    )
    print(f'stage_length={config.stage_length}  lives={config.starting_lives}  '
          f'Ore/tier=+{config.stage_income_percent_per_stage}%  '
          f'Gem/tier=+{config.stage_gem_income_percent_per_stage}%  '
          f'challenge x{config.challenge_reward_multiplier_percent / 100:g}  '
          f'buff/challenge={config.permanent_enemy_buffs_per_challenge}'
          f'+1 her {config.enemy_buff_escalation_stages} stage')
    print(f'zorluk {format_difficulty(pacing_difficulty(settings))}  '
          f'Gem olcegi %{pacing_gem_scale_percent(settings)}')
    print(f'kalici buff havuzu: stage 1 icin '
          f'{len(unlocked_enemy_buff_ids(1, config))} buff, '
          f'doyum {sum(ENEMY_SCALING_BUFF_STACK_LIMITS[b] for b in unlocked_enemy_buff_ids(10 ** 6, config))} '
          f'cekilis')
    print()

    economy_report(config, settings, args.tiers)
    purchasing_power_report(config, settings, args.tiers)
    gems_per_tier = sum(
        _reward(
            config,
            (args.tiers - 1) * config.stage_length + 1 + offset,
            MissionEconomyClass.ACT_2,
            is_challenge_stage(
                (args.tiers - 1) * config.stage_length + 1 + offset, config
            ),
            settings,
        ).meta_coins
        for offset in range(config.stage_length)
    )
    upgrade_report(config, max(1, gems_per_tier))
    if not args.economy_only:
        model = WinModel(
            base_percent=args.base_win_percent,
            per_enemy_buff_percent=args.per_buff_percent,
        )
        simulate_runs(
            config, settings, model, args.runs, args.seed, args.cap_missions
        )
        if args.careers:
            career_report(
                config, settings, model, args.careers, args.runs_each, args.seed
            )


if __name__ == '__main__':
    main()
