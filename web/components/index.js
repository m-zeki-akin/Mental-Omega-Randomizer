/* The pieces every screen is built from.
 *
 * A component takes data and returns an element. It does not ask the
 * launcher anything, does not know a view exists, and reaches nothing
 * outside itself -- so a screen can be rearranged without touching one. */

import { el, fill, count } from './dom.js';

export { el, fill, count };

/** One fact, small. */
export function pill(text, variant) {
  return el('span', { class: variant ? `pill pill--${variant}` : 'pill', text });
}

/** A button. `variant` is one of primary, danger, quiet. */
export function button(label, { variant, onClick, disabled, title } = {}) {
  return el('button', {
    class: variant ? `button button--${variant}` : 'button',
    text: label,
    title,
    disabled: disabled ? true : null,
    onClick: disabled ? null : onClick,
  });
}

/**
 * The launcher's unit of choice.
 *
 * `title` and `body` are what it says; `figure` is a picture if it has
 * one; `pills` are the facts about it; `footer` is what it costs and what
 * you do about it.
 */
export function card({
  title,
  body,
  figure,
  pills = [],
  footer = [],
  state,
  onClick,
  title_attr,
} = {}) {
  const classes = ['card'];
  if (onClick) classes.push('card--actionable');
  if (state) classes.push(`card--${state}`);
  return el('article', {
    class: classes.join(' '),
    title: title_attr,
    onClick,
  }, [
    title && el('div', { class: 'card__title', text: title }),
    figure || null,
    body && el('div', { class: 'card__body', text: body }),
    pills.length ? el('div', { class: 'row' }, pills) : null,
    footer.length ? el('div', { class: 'card__footer' }, footer) : null,
  ]);
}

/** A picture, or a box saying there is not one. */
export function figure(source, alt) {
  if (!source) {
    return el('div', {
      class: 'card__figure card__figure--empty',
      text: 'no preview',
    });
  }
  return el('div', { class: 'card__figure' }, [
    el('img', { src: source, alt: alt || '', loading: 'lazy' }),
  ]);
}

/**
 * A titled box for what is not a list.
 *
 * `body` is what it says, as one string or several; `footer` is the row
 * along the bottom, where what a panel costs sits opposite what you do
 * about it. Both are slots because the callers were writing the card's
 * own class names to get them, which made every screen a place the card
 * could break.
 */
export function panel(title, { body, footer, children } = {}) {
  const lines = [].concat(body || []).filter(Boolean);
  return el('section', { class: 'panel' }, [
    title && el('div', { class: 'panel__title', text: title }),
    ...lines.map((line) => (
      line instanceof Node ? line : el('p', { class: 'panel__body', text: line })
    )),
    ...[].concat(children || []).filter(Boolean),
    footer && footer.length
      ? el('div', { class: 'panel__footer' }, footer)
      : null,
  ]);
}

/**
 * A row of things, side by side.
 *
 * `spread` pushes the last child to the far end -- what a screen wants
 * whenever a sentence sits opposite a button. Screens used to reach for
 * the title bar's own spacer to get it.
 */
export function row(children, { spread } = {}) {
  return el('div', { class: spread ? 'row row--spread' : 'row' }, children);
}

/** A band of one screen, with a name above it. */
export function section(title, children) {
  return el('section', { class: 'section' }, [
    title && el('div', { class: 'section__title', text: title }),
    ...[].concat(children).filter(Boolean),
  ]);
}

/**
 * A table. `columns` are `{key, label}`; `rows` are objects; `cell`
 * renders one, and returns a string or an element.
 */
export function table(columns, rows, { onSelect, selected, cell } = {}) {
  const render = cell || ((row, key) => row[key]);
  const body = rows.map((row, index) => el('tr', {
    'aria-selected': String(index) === String(selected) ? 'true' : null,
    onClick: onSelect ? () => onSelect(row, index) : null,
  }, columns.map((column) => {
    const value = render(row, column.key, index);
    return el('td', {}, value instanceof Node ? [value] : [String(value ?? '')]);
  })));
  return el('table', {
    class: onSelect ? 'table table--selectable' : 'table',
  }, [
    el('thead', {}, [
      el('tr', {}, columns.map((column) => el('th', { text: column.label }))),
    ]),
    el('tbody', {}, body),
  ]);
}

/** A screen with nothing on it says why. */
export function notice(text, { error } = {}) {
  return el('div', {
    class: error ? 'notice notice--error' : 'notice',
    text,
  });
}

/* One counter for every field ever built, so a label used twice on one
 * screen does not point both of them at the same control. */
let fields = 0;

/** A labelled control. `control` is the thing being labelled. */
export function field(label, control) {
  fields += 1;
  const named = (label || '').toLowerCase().replace(/[^a-z]+/g, '-');
  const id = `field-${named || 'control'}-${fields}`;
  control.setAttribute('id', id);
  return el('div', { class: 'field' }, [
    el('label', { class: 'field__label', text: label, for: id }),
    control,
  ]);
}

/**
 * A choice between named things.
 *
 * `options` are `{value, label}`; `value` is the one standing. The label
 * is set as text, never as markup: a country's name comes from the
 * installed rules, which a submod is free to write.
 */
export function select(options, { value, onChange } = {}) {
  return el('select', {
    onChange: onChange ? (event) => onChange(event.target.value) : null,
  }, options.map((option) => el('option', {
    value: option.value,
    text: option.label,
    selected: String(option.value) === String(value) ? true : null,
  })));
}

/**
 * Something typed.
 *
 * Reported when the player is done rather than on every keystroke: what a
 * control changes is saved, and saving redraws the screen, which would
 * take the cursor out from under them mid-word. A field is done on Enter
 * or when it loses focus, which is what `change` means.
 */
export function textField({ value, placeholder, maximum, onChange }) {
  return el('input', {
    class: 'input',
    type: 'text',
    value: value || '',
    placeholder: placeholder || '',
    maxlength: maximum || null,
    onChange: (event) => onChange(event.target.value),
  });
}

/**
 * A number with two presses, the way a launcher window spins one.
 *
 * The value is sent whole rather than as a step, so the caller decides
 * how far a press moves and the launcher decides what is allowed. Both
 * setup screens use this: a run's pacing and a campaign's length are the
 * same control over different numbers.
 */
export function stepper({ value, minimum, maximum, step = 1, onChange }) {
  const at = (wanted) => onChange(Math.max(minimum, Math.min(maximum, wanted)));
  return row([
    pill(String(value), 'accent'),
    button('−', {
      variant: 'quiet',
      title: `Down ${step}`,
      disabled: value <= minimum,
      onClick: () => at(value - step),
    }),
    button('+', {
      variant: 'quiet',
      title: `Up ${step}`,
      disabled: value >= maximum,
      onClick: () => at(value + step),
    }),
  ]);
}

/**
 * On or off, as a button rather than a box.
 *
 * A button says what pressing it will do; a checkbox says what is true and
 * leaves the player to work out the rest. Both are here: the state is the
 * pill, the action is the button.
 */
export function toggle({ value, onChange, on = 'Turn on', off = 'Turn off' }) {
  return row([
    pill(value ? 'on' : 'off', value ? 'accent' : null),
    button(value ? off : on, {
      variant: value ? 'quiet' : 'primary',
      onClick: () => onChange(!value),
    }),
  ]);
}

/** A grid of cards. */
export function grid(children, { wide } = {}) {
  return el('div', { class: wide ? 'grid grid--wide' : 'grid' }, children);
}

/** Totals, laid out to be read rather than counted. */
export function stats(lines) {
  return el('div', { class: 'stats' }, lines.map(
    (line) => el('div', { text: line }),
  ));
}

/**
 * Picking several out of a list too long to draw.
 *
 * What is picked is shown as itself and taken out by pressing it; what
 * could be picked is found by typing. The list is filtered here rather
 * than by the launcher, because a search that has to ask something is a
 * search that answers a letter late.
 *
 * `chosen` are `{id, label}`, `catalogue` are `{id, label, group}`, and
 * `query` is what was last typed -- kept by the caller, so that adding
 * one entry does not clear the word that found it.
 */
export function picker({
  chosen = [], catalogue = [], query = '', limit = 20,
  placeholder, onQuery, onChange,
} = {}) {
  const ids = chosen.map((entry) => entry.id);
  const taken = new Set(ids);
  const matches = el('div', { class: 'picker__matches' });
  const show = (typed) => {
    const wanted = String(typed || '').trim().toLowerCase();
    const found = catalogue.filter((entry) => !taken.has(entry.id) && (
      !wanted
      || String(entry.label).toLowerCase().includes(wanted)
      || String(entry.id).toLowerCase().includes(wanted)
      || String(entry.group || '').toLowerCase().includes(wanted)
    ));
    const rest = found.length - limit;
    fill(matches, [
      ...found.slice(0, limit).map((entry) => el('button', {
        class: 'button picker__match',
        onClick: () => onChange([...ids, entry.id]),
      }, [
        el('span', { text: entry.label }),
        el('span', { class: 'faint', text: entry.group || entry.id }),
      ])),
      el('div', {
        class: 'faint',
        text: found.length === 0
          ? 'Nothing here is called that.'
          : (rest > 0 ? `${rest} more; type to narrow it down.` : ''),
      }),
    ]);
  };
  show(query);
  return el('div', { class: 'picker' }, [
    chosen.length
      ? row(chosen.map((entry) => el('span', {
        class: 'pill pill--accent picker__taken',
      }, [
        entry.label,
        el('button', {
          class: 'picker__drop',
          text: '×',
          title: `Take ${entry.label} out`,
          onClick: () => onChange(ids.filter((id) => id !== entry.id)),
        }),
      ])))
      : el('div', { class: 'faint', text: 'None named.' }),
    el('input', {
      class: 'input',
      type: 'search',
      value: query,
      placeholder: placeholder || 'Search',
      onInput: (event) => {
        if (onQuery) onQuery(event.target.value);
        show(event.target.value);
      },
    }),
    matches,
  ]);
}

/**
 * Numbers that only mean anything against each other.
 *
 * Each says what share of its group it is, because that is the question a
 * weight answers and no single number answers it. `onChange` is given the
 * one that moved, by name: the group is how they are read, not how they
 * are written.
 */
export function weights({ entries = [], onChange } = {}) {
  return grid(entries.map((entry) => row([
    el('div', {}, [
      el('div', { text: entry.label }),
      el('div', {
        class: 'faint',
        text: entry.value
          ? `${entry.share}% of this group`
          : 'never comes up',
      }),
    ]),
    stepper({
      value: entry.value,
      minimum: entry.minimum,
      maximum: entry.maximum,
      step: entry.step,
      onChange: (value) => onChange(entry.key, value),
    }),
  ], { spread: true })), { wide: true });
}
