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
import sys
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from randomizer.rewards.enemy_scaling import ENEMY_SCALING_BUFF_STACK_LIMITS
from randomizer.shop.config import RUN_PACING_SETTINGS, SHOP_CONFIG, run_shop_config
from randomizer.shop.economy import mission_reward, starting_run_coins
from randomizer.shop.missions import difficulty_stage, is_challenge_stage
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
        buffs = tier * config.permanent_enemy_buffs_per_challenge
        print(f'{tier:>4} {ore:>8} {gems:>8} {buffs:>20}')


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
                    buffs += config.permanent_enemy_buffs_per_challenge
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
    args = parser.parse_args()

    settings = parse_overrides(args.set)
    config = run_shop_config(
        type('Run', (), {'reward_settings': settings})(), SHOP_CONFIG
    )
    print(f'stage_length={config.stage_length}  lives={config.starting_lives}  '
          f'Ore/tier=+{config.stage_income_percent_per_stage}%  '
          f'Gem/tier=+{config.stage_gem_income_percent_per_stage}%  '
          f'challenge x{config.challenge_reward_multiplier_percent / 100:g}  '
          f'buff/challenge={config.permanent_enemy_buffs_per_challenge}')
    print(f'zorluk {format_difficulty(pacing_difficulty(settings))}  '
          f'Gem olcegi %{pacing_gem_scale_percent(settings)}')
    print(f'kalici buff havuzu: stage 1 icin '
          f'{len(unlocked_enemy_buff_ids(1, config))} buff, '
          f'doyum {sum(ENEMY_SCALING_BUFF_STACK_LIMITS[b] for b in unlocked_enemy_buff_ids(10 ** 6, config))} '
          f'cekilis')
    print()

    economy_report(config, settings, args.tiers)
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


if __name__ == '__main__':
    main()
