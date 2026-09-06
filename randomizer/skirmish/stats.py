"""What a run did, kept while it happens and kept after it ends.

A run's headline says where it is; this says what it has been. Every battle
the game finishes writes a score block -- kills, losses, buildings, score --
and those add up into something worth keeping: the run that reached
Nightmare 2 is a different story from the one that died in tier three, and
neither is legible from a battle number alone.

The totals live on the run, so they survive being put down and picked up
again. When a run ends they are written to a board of their own, which is
the only place a finished run still exists.
"""

from dataclasses import dataclass, replace
from typing import Any


STATS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RunStats:
    """Everything a run has done, added up."""

    battles: int = 0
    won: int = 0
    lost: int = 0
    kills: int = 0
    losses: int = 0
    built: int = 0
    score: int = 0
    best_score: int = 0
    ore_earned: int = 0
    upgrades_bought: int = 0
    challenges_won: int = 0
    bonus_battles: int = 0
    best_tier: int = 0
    best_nightmare: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            'battles': self.battles,
            'won': self.won,
            'lost': self.lost,
            'kills': self.kills,
            'losses': self.losses,
            'built': self.built,
            'score': self.score,
            'best_score': self.best_score,
            'ore_earned': self.ore_earned,
            'upgrades_bought': self.upgrades_bought,
            'challenges_won': self.challenges_won,
            'bonus_battles': self.bonus_battles,
            'best_tier': self.best_tier,
            'best_nightmare': self.best_nightmare,
        }


def record_battle(
    stats, *, won, result=None, offer=None, reward=0, tier=0, nightmare=0,
):
    """Return the totals after one finished battle.

    ``result`` is the game's own score block, which is absent when a battle
    was closed before it ended. That still counts as a battle and as a
    defeat; what it does not do is add kills nobody made.
    """
    stats = stats or RunStats()
    score = int(getattr(result, 'score', 0) or 0)
    return replace(
        stats,
        battles=stats.battles + 1,
        won=stats.won + (1 if won else 0),
        lost=stats.lost + (0 if won else 1),
        kills=stats.kills + int(getattr(result, 'kills', 0) or 0),
        losses=stats.losses + int(getattr(result, 'lost', 0) or 0),
        built=stats.built + int(getattr(result, 'built', 0) or 0),
        score=stats.score + score,
        best_score=max(stats.best_score, score),
        ore_earned=stats.ore_earned + max(0, int(reward or 0)),
        challenges_won=stats.challenges_won + (
            1 if won and getattr(offer, 'challenge', False) else 0
        ),
        bonus_battles=stats.bonus_battles + (
            1 if won and getattr(offer, 'bonus_percent', 0) else 0
        ),
        # Where the run reached, not where it is: a run that fell back to
        # the warmup still got as far as it got.
        best_tier=max(stats.best_tier, int(tier or 0)),
        best_nightmare=max(stats.best_nightmare, int(nightmare or 0)),
    )


def record_purchase(stats, *, stacks=1):
    stats = stats or RunStats()
    return replace(
        stats, upgrades_bought=stats.upgrades_bought + max(1, int(stacks))
    )


def normalize_stats(document, field='stats'):
    """Read stored totals, tolerating a run written before they existed."""
    if not isinstance(document, dict):
        return RunStats()
    values = {}
    for name in RunStats().to_dict():
        raw = document.get(name, 0)
        try:
            values[name] = max(0, int(raw))
        except (TypeError, ValueError):
            values[name] = 0
    return RunStats(**values)


def stats_lines(stats):
    """Return the totals as lines, for showing a run that is over."""
    stats = stats or RunStats()
    won = f'{stats.won} won, {stats.lost} lost'
    return (
        f'Battles: {stats.battles} ({won})',
        f'Challenges won: {stats.challenges_won}',
        f'Bonus battles taken: {stats.bonus_battles}',
        f'Kills: {stats.kills:,}   Losses: {stats.losses:,}',
        f'Built: {stats.built:,}',
        f'Score: {stats.score:,}   Best battle: {stats.best_score:,}',
        f'Ore earned: {stats.ore_earned:,}',
        f'Upgrades bought: {stats.upgrades_bought}',
    )
