/* The campaign run standing, as far as it has got.
 *
 * A player opens the launcher to ask two things about a run they are in
 * the middle of: which mission is next, and how much is behind them. Both
 * were only answerable by opening the classic window, which is a lot of
 * window for a question.
 *
 * So this screen reads and does not touch. The run is still played over
 * there, and the screen says so rather than offering a button that would
 * have to refuse. */

import { call, register } from '../app.js';
import { el, notice, panel, section, stats, table } from '../components/index.js';

const COLUMNS = [
  { key: 'name', label: 'Mission' },
  { key: 'side', label: 'Side' },
  { key: 'progress', label: 'Rewards' },
  { key: 'standing', label: '' },
];

/** What one mission is, in a word. */
function standing(mission) {
  if (mission.complete) return 'Finished';
  if (mission.started) return 'Started';
  if (!mission.installed) return 'Not installed';
  return mission.unlocked ? 'Open' : 'Locked';
}

function missionRows(run) {
  return run.missions.map((mission) => ({
    ...mission,
    progress: mission.total ? `${mission.done} / ${mission.total}` : '--',
    standing: standing(mission),
    next: mission.code === run.next,
  }));
}

/* A locked mission is still worth listing -- the order is the run -- but
 * it is not what the eye should land on. The one that is next is. */
function cell(row, key) {
  const text = String(row[key] ?? '');
  if (key === 'name' && row.next) {
    return el('div', {}, [
      el('span', { text }),
      el('span', { class: 'pill', text: 'next' }),
    ]);
  }
  const faint = !row.unlocked && !row.complete;
  return el('span', { class: faint ? 'muted' : null, text });
}

function header(run) {
  const lines = [
    `Seed ${run.seed}`,
    // Named as what it was made as, because that is not always what the
    // launcher is set to now. A run keeps the order it was dealt.
    run.mode ? `Made as ${run.mode}` : '',
    run.campaign,
    `${run.won} of ${run.goal} missions finished`,
    `${run.rewards} rewards earned`,
  ];
  return panel('This run', { children: [stats(lines.filter(Boolean))] });
}

async function render(root) {
  const answer = await call('campaign.run');
  const run = answer.run;
  if (!run) {
    root.replaceChildren(section('This run', notice(
      answer.refused
      || 'No run has been generated yet. Set one up on the Setup tab, '
      + 'then generate it in the classic window.',
    )));
    return;
  }
  const parts = [section(null, header(run))];
  if (run.standing_mode && run.mode && run.standing_mode !== run.mode) {
    // Worth saying plainly rather than leaving two words to contradict
    // each other: the control above says one mode and the run says
    // another, and both are true.
    parts.push(section(null, notice(
      `The launcher is set to ${run.standing_mode}, and this run was made `
      + `as ${run.mode}. It keeps the order it was dealt; generating a `
      + 'new run is what changes that.',
    )));
  }
  if (run.finished) {
    parts.push(section(null, notice(
      'This run is finished. Generate another to keep playing.',
    )));
  }
  parts.push(section('Missions', table(COLUMNS, missionRows(run), { cell })));
  parts.push(section(null, notice(
    'Read only for now: a campaign mission is launched in the classic '
    + 'window, which is what the tab beside this one opens.',
  )));
  root.replaceChildren(...parts);
}

register('run', render);
