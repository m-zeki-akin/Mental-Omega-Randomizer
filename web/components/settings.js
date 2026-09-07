/* A table of settings, drawn.
 *
 * Two screens set up a run -- the campaign's and the shop's -- and a row
 * is the same thing on both: what it is called, what kind of thing it is,
 * and what it may be. So the drawing is here, once, and a screen brings
 * what only it knows: how to change a setting, the long lists a search
 * picks out of, and what has been typed into each search box.
 *
 * Pure, like everything else in this folder: it asks the launcher nothing
 * and reaches nothing outside itself. `onChange(key, value)` is the whole
 * of what a screen has to hand it. */

import {
  button, el, grid, limits, panel, picker, row, section, select, stepper,
  textField, toggle, weights,
} from './index.js';

/* The kinds whose control is a list of its own. They get the width of the
 * panel: a name above, and the list under it. */
const WIDE = new Set(['set', 'search', 'weights', 'limits', 'map']);

/** One setting, whatever kind it is: what it is, and what changes it. */
function control(setting, { onChange, catalogues, queries, pending, refresh }) {
  const change = (value) => onChange(setting.key, value);
  if (setting.kind === 'switch') {
    return toggle({ value: setting.value, onChange: change });
  }
  if (setting.kind === 'text') {
    return textField({
      value: setting.value,
      placeholder: 'a new one each time',
      maximum: setting.maximum_length,
      onChange: change,
    });
  }
  if (setting.kind === 'limits') {
    // Two settings under one control: whether a thing may be given at
    // all, and how much of it. Nought is both answers at once, and the
    // launcher is what keeps the two in step.
    return limits({ entries: setting.entries, onChange });
  }
  if (setting.kind === 'weights') {
    // Every weight is a setting of its own; the group is how they are
    // read, not how they are written. One press writes one of them, so
    // two presses in a row cannot send back a stale neighbour.
    return weights({ entries: setting.entries, onChange });
  }
  if (setting.kind === 'search') {
    return picker({
      chosen: setting.chosen || [],
      catalogue: (catalogues && catalogues.get(setting.catalogue_name)) || [],
      query: (queries && queries.get(setting.key)) || '',
      placeholder: `Search ${setting.catalogue_size} of them`,
      onQuery: (text) => queries && queries.set(setting.key, text),
      onChange: change,
    });
  }
  if (setting.kind === 'map') {
    // Two questions in one control: which things this is about, and what
    // is turned off for each. A thing with nothing turned off says the
    // same as not being here at all, so the launcher does not keep one
    // -- which is why a thing just named is remembered by the screen
    // until something is turned off for it.
    const waiting = (pending && pending.get(setting.key)) || new Set();
    const off = new Map(
      (setting.chosen || []).map((entry) => [entry.id, new Set(entry.types)]),
    );
    // A thing just named is named the way the rest of them are: the
    // launcher has nothing to call it by yet, so the list it was picked
    // out of is what says what it is called.
    const known = (catalogues && catalogues.get(setting.catalogue_name)) || [];
    const callsIt = (id) => {
      const entry = known.find((item) => item.id === id);
      return entry ? entry.label : id;
    };
    const listed = [
      ...(setting.chosen || []),
      ...[...waiting]
        .filter((id) => !off.has(id))
        .map((id) => ({ id, label: callsIt(id), types: [] })),
    ];
    const send = () => change(Object.fromEntries(
      [...off].map(([id, types]) => [id, [...types]]),
    ));
    const subject = (entry) => {
      const turned = off.get(entry.id) || new Set();
      return panel(entry.label, {
        children: [grid(setting.catalogue.map((type) => row([
          el('span', { text: type.label }),
          toggle({
            value: !turned.has(type.id),
            on: 'Allow',
            off: 'Never',
            onChange: (allowed) => {
              const next = new Set(turned);
              if (allowed) next.delete(type.id);
              else next.add(type.id);
              off.set(entry.id, next);
              if (!next.size) off.delete(entry.id);
              return send();
            },
          }),
        ], { spread: true })), { wide: true })],
        footer: [
          el('span', {
            class: 'muted',
            text: turned.size
              ? `${turned.size} never offered`
              : 'nothing turned off yet',
          }),
          button('Take out', {
            variant: 'quiet',
            onClick: () => {
              off.delete(entry.id);
              if (waiting.has(entry.id)) waiting.delete(entry.id);
              return send();
            },
          }),
        ],
      });
    };
    return el('div', { class: 'stack' }, [
      listed.length
        ? null
        : el('div', { class: 'faint', text: 'Nothing named yet.' }),
      ...listed.map(subject),
      picker({
        chosen: listed.map((entry) => ({ id: entry.id, label: entry.label })),
        catalogue: known,
        query: (queries && queries.get(setting.key)) || '',
        placeholder: `Search ${setting.catalogue_size} of them`,
        pills: false,
        onQuery: (text) => queries && queries.set(setting.key, text),
        onChange: (ids) => {
          const added = ids[ids.length - 1];
          if (!added) return null;
          // Nothing is turned off for it yet, so the launcher has
          // nothing to keep. The screen remembers it until there is.
          waiting.add(added);
          if (pending) pending.set(setting.key, waiting);
          return refresh ? refresh() : null;
        },
      }),
    ]);
  }
  if (setting.kind === 'set') {
    // Several at once, each its own on and off. The whole list is sent
    // rather than the one that changed: what the launcher keeps is the
    // list, and a press is turned away while one is landing, so what is
    // sent is never a list read off a stale screen.
    const on = new Set(setting.value);
    const one = (entry) => row([
      el('div', {}, [
        el('div', { text: entry.label }),
        entry.note ? el('div', { class: 'faint', text: entry.note }) : null,
      ]),
      toggle({
        value: on.has(entry.id),
        on: 'On',
        off: 'Off',
        onChange: (wanted) => {
          const next = new Set(on);
          if (wanted) next.add(entry.id);
          else next.delete(entry.id);
          return change([...next]);
        },
      }),
    ], { spread: true });
    // A catalogue that names its own groups is drawn in them: forty-eight
    // switches in one block is a list nobody finds anything in.
    const groups = [];
    for (const entry of setting.catalogue) {
      const name = entry.group || '';
      const last = groups[groups.length - 1];
      if (last && last.name === name) last.entries.push(entry);
      else groups.push({ name, entries: [entry] });
    }
    return el('div', { class: 'stack' }, groups.map((group) => el('div', {
      class: 'stack',
    }, [
      group.name ? el('div', { class: 'faint', text: group.name }) : null,
      grid(group.entries.map(one), { wide: true }),
    ])));
  }
  if (setting.kind === 'number') {
    return stepper({
      value: setting.value,
      minimum: setting.minimum,
      maximum: setting.maximum,
      step: setting.step,
      onChange: change,
    });
  }
  return select(
    (setting.choices || []).map((choice) => ({
      value: choice, label: choice,
    })),
    { value: setting.value, onChange: change },
  );
}

function line(setting, tools) {
  return row([
    el('div', {}, [
      el('div', { text: setting.label }),
      setting.help ? el('div', { class: 'faint', text: setting.help }) : null,
    ]),
    control(setting, tools),
  ], { spread: true });
}

function block(setting, tools) {
  return section(null, [
    el('div', { text: setting.label }),
    setting.help ? el('div', { class: 'faint', text: setting.help }) : null,
    control(setting, tools),
  ]);
}

/** One section of a table, as a panel. */
export function settingsPanel(part, tools) {
  const listed = part.settings.filter((setting) => WIDE.has(setting.kind));
  const plain = part.settings.filter((setting) => !WIDE.has(setting.kind));
  return panel(part.name, {
    // In columns rather than one row each: a label at one end of a wide
    // window and the control that changes it at the other is a setting
    // the player has to look for twice.
    children: [
      plain.length
        ? grid(plain.map((setting) => line(setting, tools)), { wide: true })
        : null,
      ...listed.map((setting) => block(setting, tools)),
    ].filter(Boolean),
  });
}

/** Every section of a table, in the order the launcher gave them. */
export function settingsSections(sections, tools) {
  return (sections || []).map((part) => settingsPanel(part, tools));
}

/** The catalogue names the searches in a table ask for. */
export function searchesIn(sections) {
  const wanted = new Set();
  for (const part of sections || []) {
    for (const setting of part.settings) {
      if (setting.kind === 'search') wanted.add(setting.catalogue_name);
    }
  }
  return [...wanted];
}
