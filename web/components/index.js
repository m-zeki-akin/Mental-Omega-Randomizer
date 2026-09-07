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

/* Whether every word typed is somewhere in one entry.
 *
 * Word by word rather than as one string: "allied dog" should find the
 * Allied Attack Dog, and it does not appear anywhere as those two words
 * together. Each word may land in the name, the id, or the faction and
 * kind -- so "soviet naval" is a search for a group and "mtnk" is a
 * search for one thing, in the same box. */
function matches(entry, words) {
  const hay = `${entry.label} ${entry.id} ${entry.group || ''}`.toLowerCase();
  return words.every((word) => hay.includes(word));
}

/* The picture for one row, and the box it sits in whether or not there
 * is one yet. The box is there from the start on purpose: a picture
 * arriving into a row with no room for it moves every row below it, and
 * a list that moves while it is being read is a list nothing can be
 * clicked in. */
function cameoBox(entry, cameos) {
  const wanted = entry.cameo && (entry.cameo.unit || entry.cameo.power)
    ? entry.cameo : null;
  const held = wanted && cameos && cameos.get ? cameos.get(wanted) : '';
  const box = el('span', { class: 'cameo' });
  if (held) box.append(el('img', { src: held, alt: '' }));
  else if (wanted) box.dataset.wanted = JSON.stringify(wanted);
  return box;
}

/* Ask for the pictures of the rows somebody can actually see.
 *
 * Three hundred rows is three hundred pictures and a megabyte and a
 * half; a screenful is twenty. So a row asks for its own as it scrolls
 * into view, the answers arrive together, and each picture is put into
 * the row that wanted it rather than by drawing the list again -- which
 * would put the list away mid-read. */
function watchForCameos(box, cameos) {
  if (!cameos || !cameos.load || typeof IntersectionObserver !== 'function') {
    return null;
  }
  let waiting = [];
  let asked = null;
  const settle = async () => {
    asked = null;
    const rows = waiting;
    waiting = [];
    const found = await cameos.load(
      rows.map((row) => JSON.parse(row.dataset.wanted)),
    );
    if (!found) return;
    for (const row of rows) {
      const uri = found.get(row.dataset.wanted);
      if (!uri || !row.isConnected) continue;
      delete row.dataset.wanted;
      row.replaceChildren(el('img', { src: uri, alt: '' }));
    }
  };
  const watcher = new IntersectionObserver((seen) => {
    for (const row of seen) {
      if (!row.isIntersecting || !row.target.dataset.wanted) continue;
      watcher.unobserve(row.target);
      waiting.push(row.target);
    }
    if (waiting.length && asked === null) asked = setTimeout(settle, 60);
  }, { root: box });
  return watcher;
}

/**
 * Picking several out of a list too long to read at once.
 *
 * What is picked is shown as itself and taken out by pressing it. What
 * could be picked is under the box: the whole list, in the order the
 * installed rules read it, scrolling on its own -- and typing narrows it
 * rather than being the only way to see anything. Showing nothing until
 * something was typed was a bigger mistake than it looks: it meant you
 * could only exclude what you already knew the name of, which is not
 * what an exclusion list is for.
 *
 * Filtered here rather than by the launcher, because a search that has
 * to ask something is a search that answers a letter late. The launcher
 * sends each list once and this reads it.
 *
 * `chosen` are `{id, label}`, `catalogue` are `{id, label, group, cameo}`,
 * `query` is what was last typed and `open` whether the list was down --
 * both kept by the caller, because picking one entry draws the screen
 * again and neither should be lost when it does.
 */
export function picker({
  chosen = [], catalogue = [], query = '', open = false, limit = 400,
  placeholder, pills = true, cameos, onQuery, onOpen, onChange,
} = {}) {
  const ids = chosen.map((entry) => entry.id);
  const taken = new Set(ids);
  const matchBox = el('div', { class: 'picker__matches' });
  const watcher = watchForCameos(matchBox, cameos);
  const field = el('input', {
    class: 'input',
    type: 'search',
    value: query,
    placeholder: placeholder || 'Search',
  });

  const show = (typed) => {
    // The rows about to be thrown away are still being watched for
    // scrolling into view, and a watcher holding onto rows that are no
    // longer anywhere would ask for their pictures forever.
    if (watcher) watcher.disconnect();
    const words = String(typed || '').trim().toLowerCase().split(/\s+/)
      .filter(Boolean);
    const found = catalogue.filter((entry) => (
      !taken.has(entry.id) && (!words.length || matches(entry, words))
    ));
    const rest = found.length - limit;
    const rows = found.slice(0, limit).map((entry) => {
      const box = cameoBox(entry, cameos);
      const line = el('button', {
        class: 'button picker__match',
        type: 'button',
        // Not a click: pressing a row takes the focus off the box, and
        // the box losing focus is what puts the list away -- so by the
        // time a click landed there was nothing under the pointer. This
        // fires first and keeps the focus where it was, which is also
        // what lets several be picked without reaching for the box
        // again between them.
        onMousedown: (event) => {
          event.preventDefault();
          onChange([...ids, entry.id]);
        },
      }, [
        box,
        el('span', { class: 'picker__name', text: entry.label }),
        el('span', { class: 'faint', text: entry.group || entry.id }),
      ]);
      if (watcher && box.dataset.wanted) watcher.observe(box);
      return line;
    });
    fill(matchBox, [
      ...rows,
      el('div', {
        class: 'faint',
        text: found.length === 0
          ? 'Nothing here is called that.'
          : (rest > 0 ? `${rest} more; type to narrow it down.` : ''),
      }),
    ]);
  };

  const setOpen = (wanted) => {
    matchBox.hidden = !wanted;
    if (onOpen) onOpen(wanted);
  };
  field.addEventListener('focus', () => setOpen(true));
  field.addEventListener('input', (event) => {
    if (onQuery) onQuery(event.target.value);
    show(event.target.value);
    setOpen(true);
  });
  field.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      setOpen(false);
      field.blur();
    }
  });

  show(query);
  matchBox.hidden = !open;
  const node = el('div', { class: 'picker' }, [
    // What is picked is drawn here unless the screen is drawing it
    // itself -- which it does when each pick is a block of its own
    // rather than a name.
    !pills ? null : chosen.length
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
    el('div', { class: 'picker__field' }, [field, matchBox]),
  ]);
  // Away when the focus leaves the picker altogether, and not when it
  // moves about inside it.
  node.addEventListener('focusout', (event) => {
    if (!node.contains(event.relatedTarget)) setOpen(false);
  });
  if (open) {
    // The box is not in the page yet, so it cannot be focused yet. After
    // one frame it is -- and it has to be, because the list was left
    // down, and a list under a box nobody is typing in closes on the
    // next thing that takes the focus.
    requestAnimationFrame(() => {
      if (field.isConnected) field.focus();
    });
  }
  return node;
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
  return numbers({
    entries,
    onChange,
    under: (entry) => (
      entry.value ? `${entry.share}% of this group` : 'never comes up'
    ),
  });
}

/**
 * Numbers that each mean something on their own, asked of a list.
 *
 * One question about many things -- how far each of these may go -- so
 * they are drawn together, in whatever groups the launcher names them in.
 * Nought is spelled out as never, because that is what it does and a
 * player should not have to work it out from a zero.
 */
export function limits({ entries = [], onChange } = {}) {
  const groups = [];
  for (const entry of entries) {
    const name = entry.group || '';
    const last = groups[groups.length - 1];
    if (last && last.name === name) last.entries.push(entry);
    else groups.push({ name, entries: [entry] });
  }
  return el('div', { class: 'stack' }, groups.map((group) => el('div', {
    class: 'stack',
  }, [
    group.name ? el('div', { class: 'faint', text: group.name }) : null,
    numbers({
      entries: group.entries,
      onChange,
      under: (entry) => (entry.value ? entry.note || '' : 'never'),
    }),
  ])));
}

/** A grid of named numbers, each with a line saying what it means. */
function numbers({ entries = [], onChange, under }) {
  return grid(entries.map((entry) => row([
    el('div', {}, [
      el('div', { text: entry.label }),
      el('div', { class: 'faint', text: under(entry) }),
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
