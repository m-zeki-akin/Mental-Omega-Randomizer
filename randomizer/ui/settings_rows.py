"""What a setting is, before anything decides which settings there are.

Two screens describe a run's setup now -- the campaign's and the shop's --
and they were about to describe it twice. A row is the same thing in both:
where the value lives, what it is called, what kind of thing it is, and
what it may be. The kinds are the same, the conditions between rows are
the same, and the boundary that turns a table into a reply is the same.

So the vocabulary is here and the tables are elsewhere. Nothing in this
file knows a campaign or a shop exists; nothing in it draws anything.
"""


SWITCH = 'switch'
NUMBER = 'number'
CHOICE = 'choice'
TEXT = 'text'
# Several of one catalogue at once, each on or off. A list rather than a
# choice: turning one off is not picking another.
SET = 'set'
# Several out of a list too long to draw: what has been picked, and a box
# to find the next one in. The list itself is asked for by name, because
# there are a few hundred units and a screen filtering them as somebody
# types must not ask the launcher once per letter.
SEARCH = 'search'
# One group of numbers that only mean anything against each other. A
# weight of 50 is not half of anything until you know what it sits
# beside, so they are drawn together and each says its share.
WEIGHTS = 'weights'
# One group of numbers that each mean something on their own, drawn
# together because they are one question asked of a list: how far each of
# these may go, with nought meaning never.
LIMITS = 'limits'
# A search and a set at once: which things this is about, and what is
# turned off for each of them. One unit may be barred from one kind of
# upgrade without barring the kind or the unit, which is a sentence with
# two subjects and no single control for it.
MAP = 'map'

KINDS = frozenset({
    SWITCH, NUMBER, CHOICE, TEXT, SET, SEARCH, WEIGHTS, LIMITS, MAP,
})
# The kinds that hold no value of their own: what they have is the
# settings they draw, each of which is written by its own name.
GROUPS = frozenset({WEIGHTS, LIMITS})

# Where a value lives: at the top of the player's settings, or inside a
# block of it. Written as a path because some of them live in a block
# inside a block.
TOP = ''


def row(key, label, kind, help_text, *, where=TOP, mode=None, needs=None,
        **rest):
    """Return one row of a settings table."""
    return {
        'key': key,
        'where': where,
        'label': label,
        'kind': kind,
        'help': help_text,
        # None means every mode the table is for. A mode name means that
        # one only, which is how one mode's own settings stay off the
        # others' screen.
        'mode': mode,
        # What has to be true of another setting for this one to mean
        # anything: that setting's full name, and either the value it has
        # to hold or True for "anything at all". A setting that means
        # nothing right now is a setting worth not showing -- a limit's
        # size says nothing while the limit is off, and neither does
        # which kinds a starting reward may be when there are none.
        'needs': needs,
        **rest,
    }


def hidden(kept):
    """Return a row a screen never draws on its own.

    Every weight and every limit is a setting like any other -- written
    by name, clamped by its row -- but forty-six of them one under
    another is a wall rather than a screen. The group above draws them,
    and this is what keeps them out of the list of things drawn twice.
    """
    return dict(kept, hidden=True)


def full_key(entry):
    """Return one name for a row, since two blocks both have 'units'."""
    return f'{entry["where"]}.{entry["key"]}' if entry['where'] else entry['key']


def by_key(sections):
    """Return every row of a table by its own full name."""
    return {full_key(entry): entry for _name, rows in sections for entry in rows}


def rows_for(sections, mode):
    """Return the settings one mode shows, section by section."""
    wanted = str(mode or '')
    shown = []
    for name, rows in sections:
        kept = [
            entry for entry in rows
            if entry['mode'] in (None, wanted) and not entry.get('hidden')
        ]
        if kept:
            shown.append((name, kept))
    return shown
