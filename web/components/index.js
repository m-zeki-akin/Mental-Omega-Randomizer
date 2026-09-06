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

/** A titled box for what is not a list. */
export function panel(title, children) {
  return el('section', { class: 'panel' }, [
    title && el('div', { class: 'panel__title', text: title }),
    ...[].concat(children).filter(Boolean),
  ]);
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
