/* Starting a Skirmish Shop run, and choosing between the ones started.
 *
 * One mode's screen: everything on it is about a run of this mode. What
 * the launcher itself is set to -- the interface, the theme -- is not,
 * and lives on the Launcher screen instead. */

import { act, call, register, show } from '../app.js';
import {
  button, el, field, notice, panel, pill, row, section, select, table,
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

/* What the two dropdowns stand at. Kept between redraws -- a run started,
 * a run forgotten -- so a choice half made is not thrown away, and dropped
 * whenever it stops naming installed countries. A stale index would
 * otherwise sit in the control selecting nothing at all. */
let picked = null;

function armies(countries) {
  const indexes = countries.map((country) => country.index);
  const installed = (value) => indexes.includes(value);
  if (picked && installed(picked.army) && installed(picked.ally)) {
    return picked;
  }
  picked = {
    army: indexes[0],
    // Somebody else's side to begin with: the fourth installed country,
    // which is what the classic window opens on too.
    ally: indexes[Math.min(3, indexes.length - 1)],
  };
  return picked;
}

function chooser(countries) {
  const options = countries.map((country) => ({
    value: country.index,
    label: country.display,
  }));
  const standing = armies(countries);
  return panel('New run', {
    children: row([
      field('Army', select(options, {
        value: standing.army,
        onChange: (value) => { standing.army = Number(value); },
      })),
      field('Ally', select(options, {
        value: standing.ally,
        onChange: (value) => { standing.ally = Number(value); },
      })),
    ]),
    body: 'A run begins with a warmup you may skip. The ally shops with '
      + 'you, out of what your victories pay.',
    footer: [
      el('span', { class: 'muted', text: 'The seed is drawn for you.' }),
      button('Start run', {
        variant: 'primary',
        onClick: async () => {
          const started = await act('skirmish.start', {
            player: standing.army, ally: standing.ally,
          });
          // Straight to the battle it just dealt. Starting a run and then
          // having to find it is a step nobody wants twice.
          if (started) show('skirmish');
        },
      }),
    ],
  });
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

function stateCell(entry, active) {
  if (entry.run_id === active) return pill('playing', 'accent');
  if (entry.state === 'active') return pill('open');
  return pill(entry.state, 'danger');
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
  const playing = rows.some((entry) => entry.run_id === active);
  return [
    table(COLUMNS, rows, {
      selected: rows.findIndex((entry) => entry.run_id === active),
      cell: (entry, key) => {
        if (key === 'state') return stateCell(entry, active);
        if (key === 'forget') {
          return forgetButton(() => act('skirmish.delete', {
            run_id: entry.run_id,
          }));
        }
        return entry[key];
      },
      onSelect: async (entry) => {
        if (entry.run_id === active) return;
        await act('skirmish.resume', { run_id: entry.run_id });
      },
    }),
    row([
      el('span', { class: 'muted', text:
        playing
          ? 'Selecting another run resumes it.'
          : 'Select a run to resume it.' }),
    ]),
  ];
}

async function render(root) {
  const countries = await call('skirmish.countries');
  const { runs, active } = await call('skirmish.runs');
  root.replaceChildren(
    section('Start', chooser(countries)),
    section('Runs', runList(runs, active)),
  );
}

register('setup', render);
