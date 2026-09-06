"""What a skirmish run remembers.

A run is a sequence of battles against an opposition that grows. It owns
everything it has: there is no profile behind it and nothing it does reaches
another run, which is why the mode keeps a list of runs and no meta state at
all.

Maps are held as paths relative to ``MapsMO`` -- ``Standard/northsea.map`` --
so a run survives the game being moved or reinstalled, and so the pool a map
came from is still readable from what was stored.
"""

from dataclasses import dataclass, field, field, replace
from typing import Any

from randomizer.shop.model import RunStatus

from .stats import RunStats


SKIRMISH_RUN_SCHEMA_VERSION = 1
SKIRMISH_RUN_COLLECTION_SCHEMA_VERSION = 1

# How many battles share one difficulty tier, and which battle in that group
# is fought on a challenge map. The two are the same number on purpose: the
# challenge is what closes a tier.
BATTLES_PER_TIER = 5
# How many tiers one walk through the run is. The tenth tier does not
# exist: finishing the ninth starts the walk again, harder.
TIER_COUNT = 9
# The battle number a run opens on. Everything counted from one is a tier
# battle; zero is the warmup, which is none of them.
WARMUP_BATTLE = 0
DEFAULT_LIVES = 3


@dataclass(frozen=True)
class BattleOffer:
    """One battle the player may take, complete enough to launch as it is."""

    map_path: str
    map_name: str
    enemy_countries: tuple[int, ...]
    # The headline difficulty: what the ally plays at, and which of the
    # client's three challenge modes a challenge is fought under.
    handicap: int
    seed: int
    ally: bool = True
    challenge: bool = False
    # One difficulty per enemy, because a tier mixes them: two trained and
    # one hardened is a different battle from three of either.
    handicaps: tuple[int, ...] = ()
    # Whether this battle is fought with Mental Omega's AI boost on.
    mental_ai: bool = False
    # What taking the harder of the offers is worth, as a percentage on
    # top of what the battle pays. Zero is the plain offer.
    bonus_percent: int = 0

    @property
    def houses(self):
        """How many computer players this battle seats."""
        return len(self.enemy_countries) + (1 if self.ally else 0)

    def enemy_handicaps(self):
        """Return one difficulty per enemy, however old the stored offer is."""
        if len(self.handicaps) == len(self.enemy_countries):
            return self.handicaps
        return tuple(self.handicap for _ in self.enemy_countries)

    @property
    def seats(self):
        return self.houses + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            'map_path': self.map_path,
            'map_name': self.map_name,
            'enemy_countries': list(self.enemy_countries),
            'handicap': self.handicap,
            'handicaps': list(self.handicaps),
            'mental_ai': self.mental_ai,
            'bonus_percent': self.bonus_percent,
            'seed': self.seed,
            'ally': self.ally,
            'challenge': self.challenge,
        }


@dataclass(frozen=True)
class UpgradePurchase:
    """How many times one upgrade has been bought in a run."""

    unit: str
    buff_type: str
    stacks: int = 1

    @property
    def key(self):
        return (self.unit, self.buff_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            'unit': self.unit,
            'buff_type': self.buff_type,
            'stacks': self.stacks,
        }


@dataclass(frozen=True)
class SkirmishRun:
    run_id: str
    seed: str
    player_country: int
    ally_country: int
    created: str = ''
    status: RunStatus = RunStatus.ACTIVE
    # The battle about to be played. Zero is the warmup: one fight to
    # find the mouse again, with no shop and nothing riding on it, which
    # the player may skip outright.
    battle: int = WARMUP_BATTLE
    lives: int = DEFAULT_LIVES
    revivals_used: int = 0
    coins: int = 0
    purchases: tuple[UpgradePurchase, ...] = ()
    # The ally shops for itself, out of its own earnings and its own
    # faction's list, so the two armies grow apart over a run.
    ally_coins: int = 0
    ally_purchases: tuple[UpgradePurchase, ...] = ()
    offers: tuple[BattleOffer, ...] = ()
    # What the shop is offering this battle, as ``unit:buff_type`` keys.
    # Stored rather than redrawn, so buying from the shelf does not
    # reshuffle the shelf: the six stand for the whole battle and a bought
    # one stays where it was, marked as bought.
    shelf: tuple[str, ...] = ()
    committed_offer: int | None = None
    won_battles: int = 0
    # How many times the nine tiers have been walked. Zero is the first
    # run through; one and up are Nightmare, where the enemies keep
    # everything they have and both your armies start again with nothing.
    nightmare: int = 0
    # What the run has done, added up as it happens.
    stats: 'RunStats' = field(default_factory=lambda: RunStats())
    # Relative paths, so a challenge is not offered twice until the pool has
    # been through once.
    used_challenge_maps: tuple[str, ...] = ()
    schema_version: int = SKIRMISH_RUN_SCHEMA_VERSION

    @property
    def cycle_battles(self):
        """How many battles one walk through the tiers is."""
        return TIER_COUNT * BATTLES_PER_TIER

    @property
    def warmup(self):
        return self.battle <= WARMUP_BATTLE

    @property
    def tier(self):
        """Which tier this battle belongs to. The warmup is tier zero."""
        if self.warmup:
            return WARMUP_BATTLE
        return (self.battle - 1) // BATTLES_PER_TIER + 1

    @property
    def challenge_battle(self):
        """Whether this battle closes a tier. The warmup closes nothing."""
        if self.warmup:
            return False
        return self.battle % BATTLES_PER_TIER == 0

    @property
    def lives_left(self):
        return max(0, self.lives - self.revivals_used)

    def committed(self):
        if self.committed_offer is None:
            return None
        if not 0 <= self.committed_offer < len(self.offers):
            return None
        return self.offers[self.committed_offer]

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'run_id': self.run_id,
            'seed': self.seed,
            'created': self.created,
            'status': self.status.value,
            'player_country': self.player_country,
            'ally_country': self.ally_country,
            'battle': self.battle,
            'lives': self.lives,
            'revivals_used': self.revivals_used,
            'coins': self.coins,
            'purchases': [item.to_dict() for item in self.purchases],
            'ally_coins': self.ally_coins,
            'ally_purchases': [
                item.to_dict() for item in self.ally_purchases
            ],
            'offers': [offer.to_dict() for offer in self.offers],
            'shelf': list(self.shelf),
            'committed_offer': self.committed_offer,
            'won_battles': self.won_battles,
            'nightmare': self.nightmare,
            'stats': self.stats.to_dict(),
            'used_challenge_maps': list(self.used_challenge_maps),
        }


@dataclass(frozen=True)
class SkirmishRunCollection:
    """Every stored run, and which one the player is in.

    The same shape as the Shop run list, and for the same reason: a player
    keeps several open and returns to whichever they choose. ``active_run_id``
    may be ``None``; nothing is selected on their behalf.
    """

    runs: tuple[SkirmishRun, ...] = ()
    active_run_id: str | None = None
    schema_version: int = SKIRMISH_RUN_COLLECTION_SCHEMA_VERSION

    def active(self):
        return self.run(self.active_run_id)

    def run(self, run_id):
        if not run_id:
            return None
        for run in self.runs:
            if run.run_id == run_id:
                return run
        return None

    def with_run(self, run, *, activate=True):
        replaced = False
        runs = []
        for stored in self.runs:
            if stored.run_id == run.run_id:
                runs.append(run)
                replaced = True
            else:
                runs.append(stored)
        if not replaced:
            runs.append(run)
        return replace(
            self,
            runs=tuple(runs),
            active_run_id=run.run_id if activate else self.active_run_id,
        )

    def without_run(self, run_id):
        return replace(
            self,
            runs=tuple(
                stored for stored in self.runs if stored.run_id != run_id
            ),
            active_run_id=(
                None if self.active_run_id == run_id else self.active_run_id
            ),
        )

    def selecting(self, run_id):
        if run_id is not None and self.run(run_id) is None:
            raise KeyError(run_id)
        return replace(self, active_run_id=run_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'active_run_id': self.active_run_id,
            'runs': [run.to_dict() for run in self.runs],
        }
