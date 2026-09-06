/* Shop Mode's setup: what the next run will be started with.
 *
 * The run itself is played in the classic window, and the panel next door
 * says so. This screen is here anyway, because the setup is not part of a
 * run: it outlives the run it was used for, both windows read it from one
 * place, and a mode's settings belong on that mode's screen rather than
 * in a window the player has to open to find them.
 *
 * Nothing here can reach a run that has already begun. A run freezes its
 * pacing when it starts, which is why moving a control is safe. */

import { act, call, register } from '../app.js';
import {
  button, card, el, grid, notice, panel, pill, row, section,
} from '../components/index.js';

/** One pacing control: what it is, where it stands, and two presses. */
function control(setting) {
  const at = (value) => act('shop.use_pacing', {
    name: setting.key, value,
  });
  const shown = [pill(String(setting.value), 'accent')];
  if (setting.value !== setting.baseline) {
    shown.push(el('span', {
      class: 'faint', text: `was ${setting.baseline}`,
    }));
  }
  return row([
    el('span', { text: setting.label }),
    row([
      ...shown,
      button('−', {
        variant: 'quiet',
        title: `Down ${setting.step}`,
        disabled: setting.value <= setting.minimum,
        onClick: () => at(Math.max(
          setting.minimum, setting.value - setting.step,
        )),
      }),
      button('+', {
        variant: 'quiet',
        title: `Up ${setting.step}`,
        disabled: setting.value >= setting.maximum,
        onClick: () => at(Math.min(
          setting.maximum, setting.value + setting.step,
        )),
      }),
    ]),
  ], { spread: true });
}

function pacingPanel(settings) {
  return panel('Pacing', {
    body: 'How fast a run goes, and how hard the enemy answers it. The '
      + 'run you are in keeps the pacing it started with; this is for the '
      + 'next one.',
    // In a grid rather than five full-width rows: a label at one end of a
    // wide window and the two presses that change it at the other is a
    // control the player has to look for twice.
    children: [grid(settings.pacing.map(control), { wide: true })],
    footer: [
      el('span', { class: 'muted' }, [
        'Run difficulty ', pill(settings.difficulty, 'accent'),
        ` — Gems ×${(settings.gem_scale_percent / 100).toFixed(2)}`,
      ]),
      button('Back to defaults', {
        variant: 'quiet',
        disabled: settings.default,
        onClick: () => act('shop.reset_setup'),
      }),
    ],
  });
}

/** One optional trade, on or off. */
function modifierCard(modifier) {
  return card({
    title: modifier.name,
    body: modifier.description,
    state: modifier.enabled ? 'selected' : null,
    pills: modifier.enabled ? [pill('on', 'accent')] : [],
    footer: [
      button(modifier.enabled ? 'Turn off' : 'Turn on', {
        variant: modifier.enabled ? 'quiet' : 'primary',
        onClick: () => act('shop.use_modifier', {
          name: modifier.id, enabled: !modifier.enabled,
        }),
      }),
    ],
  });
}

async function render(root) {
  const settings = await call('shop.settings');
  root.replaceChildren(
    section('The next run', pacingPanel(settings)),
    section('Optional run modifiers', [
      notice(
        'Each one pairs an advantage with a drawback, so none of them '
        + 'counts towards the run difficulty above.',
      ),
      grid(settings.modifiers.map(modifierCard), { wide: true }),
    ]),
  );
}

register('shop', render);
