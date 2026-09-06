/* The campaign's setup: how the next run will be generated.
 *
 * One screen for Classic, Mission List and Grid, because they are the
 * same campaign in a different order and share all but three of their
 * settings. Which rows those three are is the launcher's to say, not this
 * screen's: it draws the sections it is given, in the order it is given
 * them, and a row it has never heard of would still be drawn.
 *
 * Generating the seed is still the classic window's, and the panel on the
 * tab beside this one says so. */

import { act, call, register } from '../app.js';
import {
  el, grid, notice, panel, row, section, select, stepper, textField,
  toggle,
} from '../components/index.js';

/** One setting, whatever kind it is: what it is, and what changes it. */
function control(setting) {
  const change = (value) => act('campaign.use_setting', {
    name: setting.key, value,
  });
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
  if (setting.kind === 'set') {
    // Several at once, each its own on and off. The whole list is sent
    // rather than the one that changed: what the launcher keeps is the
    // list, and sending it whole is what makes a stale screen harmless.
    const on = new Set(setting.value);
    return grid(setting.catalogue.map((entry) => row([
      el('span', { text: entry.label }),
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
    ], { spread: true })));
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

function line(setting) {
  return row([
    el('div', {}, [
      el('div', { text: setting.label }),
      setting.help ? el('div', { class: 'faint', text: setting.help }) : null,
    ]),
    control(setting),
  ], { spread: true });
}

/* A setting whose control is a list of its own gets the width of the
 * panel: its name above it, and the catalogue under that. */
function block(setting) {
  return section(null, [
    el('div', { text: setting.label }),
    setting.help ? el('div', { class: 'faint', text: setting.help }) : null,
    control(setting),
  ]);
}

function settingsPanel(part) {
  const listed = part.settings.filter((setting) => setting.kind === 'set');
  const plain = part.settings.filter((setting) => setting.kind !== 'set');
  return panel(part.name, {
    // In columns rather than one row each: a label at one end of a wide
    // window and the control that changes it at the other is a setting
    // the player has to look for twice.
    children: [
      plain.length ? grid(plain.map(line), { wide: true }) : null,
      ...listed.map(block),
    ].filter(Boolean),
  });
}

async function render(root) {
  const answer = await call('campaign.settings');
  root.replaceChildren(
    section('The next run', [
      notice(
        answer.mode
          ? `These are ${answer.mode}'s settings. Generating the seed they `
            + 'describe is still done in the classic window.'
          : 'The campaign settings, shared by Classic, Mission List and Grid.',
      ),
      // Why the seed box is empty when a run is standing. The classic
      // window empties it for the same reason and says nothing; here
      // there is room to say it.
      answer.generated_seed
        ? notice(
          `A seed is standing: ${answer.generated_seed}. The box below is `
          + 'empty on purpose, so that generating again does not replay '
          + 'the run in progress.',
        )
        : null,
      ...answer.sections.map(settingsPanel),
    ]),
  );
}

register('campaign', render);
