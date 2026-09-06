/* Starting a run, and choosing between the ones already started. */

import { act, call, register, show } from '../app.js';
import {
  button, el, field, notice, panel, pill, section, select, table,
} from '../components/index.js';

const COLUMNS = [
  { key: 'seed', label: 'Seed' },
  { key: 'army', label: 'Army' },
  { key: 'ally', label: 'Ally' },
  { key: 'progress', label: 'Reached' },
  { key: 'state', label: 'State' },
  { key: 'started', label: 'Started' },
  { key: 'forget', label: '' },
];

/* What the two dropdowns stand at. Kept while the screen is open so a
 * redraw -- a run started, a run deleted -- does not throw the choice
 * away. The first drawing takes them from the run being played, which is
 * the nearest thing to what this player last chose. */
let army = null;
let ally = null;

function chooser(countries) {
  const options = countries.map((country) => ({
    value: country.index,
    label: country.display,
  }));
  return panel('New run', [
    el('div', { class: 'row' }, [
      field('Army', select(options, {
        value: army,
        onChange: (value) => { army = Number(value); },
      })),
      field('Ally', select(options, {
        value: ally,
        onChange: (value) => { ally = Number(value); },
      })),
    ]),
    el('div', { class: 'card__body', text:
      'A run begins with a warmup you may skip. The ally shops with you, '
      + 'out of what your victories pay.' }),
    el('div', { class: 'card__footer' }, [
      el('span', { class: 'muted', text: 'The seed is drawn for you.' }),
      button('Start run', {
        variant: 'primary',
        onClick: async () => {
          const started = await act('skirmish.start', { player: army, ally });
          // Straight to the battle it just dealt. Starting a run and then
          // having to find it is a step nobody wants twice.
          if (started) show('skirmish');
        },
      }),
    ]),
  ]);
}

function runRows(runs, active) {
  return runs.map((run) => ({
    run_id: run.run_id,
    seed: run.seed,
    army: run.player.display,
    ally: run.ally.display,
    progress: run.progress,
    state: run.run_id === active ? 'playing' : run.status,
    started: run.created,
  }));
}

function stateCell(row, active) {
  if (row.run_id === active) return pill('playing', 'accent');
  if (row.state === 'active') return pill('open');
  return pill(row.state, 'danger');
}

/**
 * A button that asks once.
 *
 * Forgetting a run cannot be undone and there is no dialog on this screen,
 * so the button becomes the question and the second press is the answer.
 */
function forgetButton(onConfirm) {
  let asked = false;
  const node = button('Forget', {
    variant: 'quiet',
    title: 'Delete this run. What it did stays on the board if it ended.',
    onClick: async (event) => {
      // The row resumes the run it names. This press is about the button.
      event.stopPropagation();
      if (!asked) {
        asked = true;
        node.textContent = 'Sure?';
        node.className = 'button button--danger';
        return;
      }
      await onConfirm();
    },
  });
  return node;
}

function runList(runs, active) {
  if (!runs.length) {
    return notice('No run has been started yet.');
  }
  const rows = runRows(runs, active);
  const chosen = rows.find((row) => row.run_id === active) || null;
  return [
    table(COLUMNS, rows, {
      selected: rows.findIndex((row) => row.run_id === active),
      cell: (row, key) => {
        if (key === 'state') return stateCell(row, active);
        if (key === 'forget') {
          return forgetButton(() => act('skirmish.delete', {
            run_id: row.run_id,
          }));
        }
        return row[key];
      },
      onSelect: async (row) => {
        if (row.run_id === active) return;
        await act('skirmish.resume', { run_id: row.run_id });
      },
    }),
    el('div', { class: 'row' }, [
      el('span', { class: 'muted', text:
        chosen
          ? 'Selecting another run resumes it.'
          : 'Select a run to resume it.' }),
    ]),
  ];
}

/* The rest of the launcher is still the old window: the campaign, the
 * Campaign Shop, Archipelago and the settings. Until they are here too,
 * going back has to be one press rather than a command line. */
function interfacePanel(chosen) {
  return panel('Interface', [
    el('div', { class: 'card__body', text:
      'This interface draws the Skirmish Shop mode. The campaign, the '
      + 'Campaign Shop, Archipelago and the settings are still in the '
      + 'classic window.' }),
    el('div', { class: 'card__footer' }, [
      el('span', { class: 'muted', text:
        chosen.new
          ? 'This interface opens at start.'
          : 'The classic window opens at start.' }),
      button(chosen.new ? 'Open the classic window at start' : 'Open this one at start', {
        variant: 'quiet',
        onClick: () => act('launcher.use_interface', {
          name: chosen.new ? 'classic' : 'new',
        }),
      }),
    ]),
  ]);
}

async function render(root) {
  const countries = await call('skirmish.countries');
  const { runs, active } = await call('skirmish.runs');
  const chosen = await call('launcher.interface');
  if (army === null) {
    const playing = runs.find((run) => run.run_id === active);
    army = playing ? playing.player.index : (countries[0] || {}).index;
    ally = playing
      ? playing.ally.index
      : (countries[Math.min(3, countries.length - 1)] || {}).index;
  }
  root.replaceChildren(
    section('Start', chooser(countries)),
    section('Runs', runList(runs, active)),
    section(null, interfacePanel(chosen)),
  );
}

const root = document.getElementById('view-setup');
register('setup', { root, render: () => render(root) });
