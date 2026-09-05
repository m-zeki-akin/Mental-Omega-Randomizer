"""How a finished skirmish reports what happened.

A campaign mission is watched for markers named after its own TeamTypes. A
skirmish has none of those, and the question of what it does have instead was
answered by playing one of each outcome and reading the game's log.

What both games wrote, at the end and nowhere else, is a score block naming
every house and whether it won:

    Commander: Winner
     Scheme: 1
     Lost = 101
     Kills = 518
     Built = 195
     Score = 478701
    Computer: Loser

The player's house is named by ``Name`` in the spawn file, so the launcher
already knows which line is the player's; every computer house is
``Computer``.

Two things that look like answers and are not. ``MPlayer_Defeated()`` is
written when *any* house is defeated -- it appears in a won game, about the
opponent. And ``Saw game completion due to player defeat`` says the same
thing about the same event. The score block is the only line that says who
actually won, so it is what this reads.
"""

from dataclasses import dataclass
import re


_HEADER = re.compile(r'^(?P<name>\S[^:\r\n]*): (?P<outcome>Winner|Loser)\s*$')
_STAT = re.compile(
    r'^\s+(?P<key>Scheme|Lost|Kills|Built|Score)\s*[:=]\s*(?P<value>-?\d+)\s*$'
)


@dataclass(frozen=True)
class HouseResult:
    name: str
    won: bool
    scheme: int = 0
    lost: int = 0
    kills: int = 0
    built: int = 0
    score: int = 0

    def to_dict(self):
        return {
            'name': self.name,
            'won': self.won,
            'scheme': self.scheme,
            'lost': self.lost,
            'kills': self.kills,
            'built': self.built,
            'score': self.score,
        }


def result_blocks(text):
    """Return each finished game's score block, in the order they were played.

    One block is the houses of one game, written one after another. A block
    ends where the score lines stop.
    """
    lines = str(text or '').splitlines()
    blocks = []
    current = []
    index = 0
    previous_end = None
    while index < len(lines):
        header = _HEADER.match(lines[index])
        if not header:
            index += 1
            continue
        stats = {}
        cursor = index + 1
        while cursor < len(lines):
            stat = _STAT.match(lines[cursor])
            if not stat:
                break
            stats[stat.group('key').lower()] = int(stat.group('value'))
            cursor += 1
        if not stats:
            # A line that reads like a header but carries no score is not
            # one: the log is full of ordinary text.
            index += 1
            continue
        if current and previous_end != index:
            blocks.append(tuple(current))
            current = []
        current.append(HouseResult(
            name=header.group('name').strip(),
            won=header.group('outcome') == 'Winner',
            scheme=stats.get('scheme', 0),
            lost=stats.get('lost', 0),
            kills=stats.get('kills', 0),
            built=stats.get('built', 0),
            score=stats.get('score', 0),
        ))
        previous_end = cursor
        index = cursor
    if current:
        blocks.append(tuple(current))
    return tuple(blocks)


def last_game_result(text, player_name='Commander'):
    """Return the player's result in the most recent finished game.

    ``None`` when the log holds no finished game -- which is what a player
    who closed the game from the menu, or crashed out of it, leaves behind.
    """
    blocks = result_blocks(text)
    if not blocks:
        return None
    wanted = str(player_name or '').strip().lower()
    for house in blocks[-1]:
        if house.name.strip().lower() == wanted:
            return house
    return None


def read_debug_log_tail(path, offset=0):
    """Return what the game wrote to its log since the battle started.

    A game that recreates its log leaves it shorter than it was, and reading
    from the old offset would then read from the middle of the new file, so
    that case starts again from the beginning.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return ''
    start = 0 if size < offset else int(offset)
    try:
        with path.open('r', encoding='utf-8', errors='ignore') as handle:
            handle.seek(start)
            return handle.read()
    except OSError:
        return ''
