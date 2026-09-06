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
  el, grid, notice, panel, row, section, select, stepper, toggle,
} from '../components/index.js';

/** One setting, whatever kind it is: what it is, and what changes it. */
function control(setting) {
  const change = (value) => act('campaign.use_setting', {
    name: setting.key, value,
  });
  if (setting.kind === 'switch') {
    return toggle({ value: setting.value, onChange: change });
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

function settingsPanel(part) {
  return panel(part.name, {
    // In columns rather than one row each: a label at one end of a wide
    // window and the control that changes it at the other is a setting
    // the player has to look for twice.
    children: [grid(part.settings.map(line), { wide: true })],
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
      ...answer.sections.map(settingsPanel),
    ]),
  );
}

register('campaign', render);
