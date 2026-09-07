"""Turning a table of settings into a reply, and a reply back into one.

Two screens describe how a run is set up: the campaign's and the shop's.
What they describe is different; how they describe it is not. A row says
where a value lives and what kind of thing it is, a screen draws the kind,
and this is the piece in the middle -- the one that reads a value out of
the player's settings, says what a control may do with it, and writes back
what the control did.

It knows nothing about campaigns or shops. Give it a table and it answers
for that table.
"""

from randomizer.ui.settings_rows import (
    CHOICE,
    GROUPS,
    LIMITS,
    MAP,
    NUMBER,
    SEARCH,
    SET,
    SWITCH,
    TEXT,
    WEIGHTS,
    by_key,
    full_key,
    rows_for,
)

from .contract import ApiError


# What a named list may hold. Longer than any catalogue the installed
# rules offer, and short enough that a settings file cannot be filled
# with one by a screen that has gone wrong.
MAXIMUM_NAMED = 1000
MAXIMUM_NAME_LENGTH = 128


def block(config, row, *, make=False):
    """Return the block of the settings a row lives in.

    A row says where it lives as a path, because some of them live in a
    block inside a block. Reading a block that is not there answers an
    empty one; writing makes it.
    """
    held = config
    for step in filter(None, str(row['where']).split('.')):
        inside = held.get(step)
        if not isinstance(inside, dict):
            if not make:
                return {}
            inside = {}
            held[step] = inside
        held = inside
    return held


class Settings:
    """One table of settings, and everything a boundary does with it.

    ``catalogues`` answers what a search may name: ``entries(name)`` for
    the whole list and ``labels(name, ids)`` for what has been picked,
    named. ``ceilings`` are the ones a row cannot state as a number
    because they depend on the other settings; a row names one and this
    works it out.
    """

    def __init__(self, sections, *, catalogues=None, ceilings=None):
        self.sections = tuple(sections)
        self.by_key = by_key(self.sections)
        self.catalogues = catalogues
        self.ceilings = dict(ceilings or {})

    # --- reading -------------------------------------------------------

    def ceiling(self, config, row):
        """Return the highest a number may go as the rest of it stands."""
        wanted = self.ceilings.get(row.get('ceiling'))
        return row['maximum'] if wanted is None else wanted(config, row)

    def value(self, config, row):
        """Return what a row holds, as the kind of thing it says it is."""
        held = block(config, row).get(row['key'])
        if row['kind'] == SWITCH:
            return bool(held)
        if row['kind'] == NUMBER:
            # A number that was never written answers what the launcher
            # would use, not the bottom of its range: an unset weight is
            # a full one, and reading it as zero would say the opposite.
            default = row.get('default', row['minimum'])
            try:
                number = int(held)
            except (TypeError, ValueError):
                number = default
            number = max(row['minimum'], min(self.ceiling(config, row), number))
            return self._gated(config, row, number)
        if row['kind'] == TEXT:
            return str(held or '').strip()[:row['maximum_length']]
        if row['kind'] == SET:
            known = [entry['id'] for entry in row['catalogue']]
            if not isinstance(held, (list, tuple)):
                return list(known)
            chosen = {str(item) for item in held}
            # A list that says everything means everything there is now,
            # which is the whole point of writing it that way.
            if row.get('wildcard') and row['wildcard'] in chosen:
                return list(known)
            return [item for item in known if item in chosen]
        if row['kind'] == SEARCH:
            if not isinstance(held, (list, tuple)):
                return []
            return [entry['id'] for entry in self._named(row, held)]
        if row['kind'] == MAP:
            return self._mapped(row, held)
        if row['kind'] == CHOICE:
            wanted = str(held or '')
            return wanted if wanted in row['choices'] else row['choices'][0]
        # Every kind is named above. A group holds nothing of its own,
        # and asking one for a value used to fall through to the choices
        # it has none of -- a KeyError, which is a screen that says
        # nothing at all.
        raise ApiError(f'{row["label"]} is not one setting with one value')

    def _gated(self, config, row, number):
        """Return a number a list can veto, as the list has it.

        A limit whose subject is turned off reads as nought however far
        it was wound up, because nought is what it does. The number
        itself is left where the player put it: turning the subject back
        on should give back the limit they chose, not the bottom of it.
        """
        gate = row.get('gated_by')
        if not gate:
            return number
        other = self.by_key.get(gate)
        if other is None:
            return number
        return number if row['key'] in self.value(config, other) else 0

    def _mapped(self, row, held):
        """Return what is turned off for each thing named, in order.

        A subject with nothing turned off is not a subject: it says the
        same as not being here at all, and two ways of saying one thing
        is a setting that can disagree with itself.
        """
        if not isinstance(held, dict):
            return {}
        known = [entry['id'] for entry in row['catalogue']]
        mapped = {}
        for subject, turned_off in held.items():
            if not isinstance(turned_off, (list, tuple, set)):
                continue
            wanted = {str(item) for item in turned_off}
            kept = [item for item in known if item in wanted]
            if kept:
                mapped[str(subject)] = kept
        return mapped

    def _named(self, row, ids):
        if self.catalogues is None:
            return [{'id': str(item), 'label': str(item)} for item in ids or ()]
        return self.catalogues.labels(row['catalogue_name'], ids)

    def _entries(self, config, row):
        """Return the settings a group draws, each read as its own row."""
        drawn = []
        for key in row['entries']:
            other = self.by_key.get(key)
            if other is None:
                continue
            drawn.append({
                'key': key,
                'label': other['label'],
                'help': other['help'],
                'group': other.get('group', ''),
                'note': other.get('note', ''),
                'value': self.value(config, other),
                'minimum': other['minimum'],
                'maximum': self.ceiling(config, other),
                'step': other['step'],
            })
        return drawn

    def _weights(self, config, row):
        """Return one group of weights, each with its share of the group.

        The share is what a weight means: 50 beside two 100s comes up a
        fifth of the time, and neither the 50 nor the 100 says so on its
        own. A group that is all zeroes has no shares -- nothing in it
        comes up at all.
        """
        drawn = self._entries(config, row)
        total = sum(entry['value'] for entry in drawn)
        for entry in drawn:
            entry['share'] = round(100 * entry['value'] / total) if total else 0
        return drawn

    def shown(self, config, row, blank=False):
        """Return one row as the reply a screen draws."""
        seen = {
            'key': full_key(row),
            'label': row['label'],
            'kind': row['kind'],
            'help': row['help'],
        }
        if row['kind'] in GROUPS:
            seen['entries'] = (
                self._weights(config, row) if row['kind'] == WEIGHTS
                else self._entries(config, row)
            )
            return seen
        seen['value'] = (
            '' if blank and row.get('blank_while_generated')
            else self.value(config, row)
        )
        if row['kind'] == NUMBER:
            seen.update(
                minimum=row['minimum'],
                maximum=self.ceiling(config, row),
                step=row['step'],
            )
        elif row['kind'] == CHOICE:
            seen['choices'] = list(row['choices'])
        elif row['kind'] == TEXT:
            seen['maximum_length'] = row['maximum_length']
        elif row['kind'] == SET:
            seen['catalogue'] = [dict(entry) for entry in row['catalogue']]
        elif row['kind'] == MAP:
            # The subjects by name, each with what is turned off for it,
            # and the whole list of what may be turned off. The names the
            # subjects are picked from are asked for the way a search
            # asks: by name, once.
            seen['catalogue'] = [dict(entry) for entry in row['catalogue']]
            seen['catalogue_name'] = row['catalogue_name']
            seen['catalogue_size'] = len(
                self.catalogues.catalogue(row['catalogue_name'])
                if self.catalogues else ()
            )
            seen['chosen'] = [
                dict(entry, types=seen['value'][entry['id']])
                for entry in self._named(row, list(seen['value']))
            ]
        elif row['kind'] == SEARCH:
            # The list itself does not come with the settings: it is a
            # few hundred entries, it is the same on every reading, and a
            # screen asks for it once. What comes is what has been
            # picked, named.
            seen['catalogue_name'] = row['catalogue_name']
            seen['catalogue_size'] = len(
                self.catalogues.catalogue(row['catalogue_name'])
                if self.catalogues else ()
            )
            seen['chosen'] = self._named(row, seen['value'])
        return seen

    def needed(self, config, row):
        """Whether a row means anything as the other settings stand.

        A row can name another setting it depends on: True for "holds
        anything at all", or a value it has to hold. Hidden rather than
        greyed out, because a control that cannot do anything is one more
        thing on a screen to read past.
        """
        wanted = row.get('needs')
        if not wanted:
            return True
        key, expected = wanted
        other = self.by_key.get(key)
        if other is None or other['kind'] in GROUPS:
            return True
        held = self.value(config, other)
        return bool(held) if expected is True else held == expected

    def answer(self, config, *, mode='', blank=False):
        """Return every section this table shows for one mode."""
        return [
            {
                'name': name,
                'settings': [
                    self.shown(config, row, blank) for row in shown
                ],
            }
            for name, shown in (
                (name, [row for row in rows if self.needed(config, row)])
                for name, rows in rows_for(self.sections, mode)
            )
            # A section whose every row is about something turned off is
            # a heading with nothing under it.
            if shown
        ]

    # --- writing -------------------------------------------------------

    def write(self, config, name, value):
        """Keep one setting, as the kind of thing its row says it is.

        A number out of range is clamped rather than refused -- a control
        cannot ask for what the launcher would not offer, and a settings
        file already holding one is worth quietly correcting. A choice
        that is not one of the choices is a refusal, because there is
        nothing sensible to correct it to.
        """
        key = str(name or '')
        row = self.by_key.get(key)
        if row is None:
            raise ApiError(f'There is no {key or "unnamed"} setting')
        kept = self._kept(config, row, value)
        block(config, row, make=True)[row['key']] = kept
        self._ungate(config, row, kept)
        return row

    def _kept(self, config, row, value):
        if row['kind'] == SWITCH:
            if value is None:
                raise ApiError(f'Say whether {row["label"]} is on or off')
            return bool(value)
        if row['kind'] == NUMBER:
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise ApiError(f'{row["label"]} needs a number') from None
            return max(row['minimum'], min(self.ceiling(config, row), number))
        if row['kind'] == TEXT:
            # Trimmed and capped rather than refused: what a player typed
            # is worth keeping even with a space at the end of it.
            return str(value or '').strip()[:row['maximum_length']]
        if row['kind'] == SET:
            if not isinstance(value, (list, tuple)):
                raise ApiError(f'{row["label"]} needs a list of what is on')
            wanted = {str(item) for item in value}
            kept = [
                entry['id'] for entry in row['catalogue']
                if entry['id'] in wanted
            ]
            # All of them is kept as all of them, rather than as a list
            # of everything there happens to be today.
            if row.get('wildcard') and len(kept) == len(row['catalogue']):
                return [row['wildcard']]
            return kept
        if row['kind'] == SEARCH:
            if not isinstance(value, (list, tuple)):
                raise ApiError(f'{row["label"]} needs a list of names')
            # A name the installed rules do not know is kept rather than
            # dropped: a submod that renames a unit should not quietly
            # empty a list somebody built, and the screen shows the name
            # as it is so it can be taken out on purpose.
            return [
                entry['id'] for entry in self._named(row, value)
                if len(entry['id']) <= MAXIMUM_NAME_LENGTH
            ][:MAXIMUM_NAMED]
        if row['kind'] == MAP:
            if not isinstance(value, dict):
                raise ApiError(
                    f'{row["label"]} needs what is turned off, by name'
                )
            named = {
                str(subject): turned_off
                for subject, turned_off in list(value.items())[:MAXIMUM_NAMED]
                if len(str(subject)) <= MAXIMUM_NAME_LENGTH
            }
            return self._mapped(row, named)
        if row['kind'] == CHOICE:
            kept = str(value or '')
            if kept not in row['choices']:
                raise ApiError(
                    f'{row["label"]} has no {kept or "unnamed"} choice'
                )
            return kept
        raise ApiError(
            f'{row["label"]} is a group of settings; change one of them '
            'by its own name'
        )

    def _ungate(self, config, row, kept):
        """Keep a list in step with the limit a screen just moved.

        Two settings, one control: a bonus the enemy may be given, and
        how many of it. A screen shows one number with nought meaning
        never, so writing nought takes the bonus off the list and writing
        anything else puts it back. Which is what makes the two agree --
        a bonus allowed with a limit of nought and a bonus not allowed
        are the same enemy, and only one of them is worth storing.
        """
        gate = row.get('gated_by')
        if not gate or row['kind'] != NUMBER:
            return
        other = self.by_key.get(gate)
        if other is None:
            return
        allowed = set(self.value(config, other))
        if kept:
            allowed.add(row['key'])
        else:
            allowed.discard(row['key'])
        self.write(config, gate, sorted(allowed))
