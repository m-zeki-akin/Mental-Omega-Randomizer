/* The Shop Mode run: the stage, what it may be played on, and the shelf.
 *
 * The setup screen beside this one describes the *next* run. This is the
 * one being played, and it is the same shape the skirmish run has --
 * choose a battle, buy what you can afford, play it -- because they are
 * the same game with a campaign mission in the middle of it. */

import { act, call, refresh, register, status } from '../app.js';
import {
  button, card, count, el, grid, notice, pill, row, section, stats,
} from '../components/index.js';

const DIFFICULTY_VARIANT = {
  Casual: null,
  Normal: 'trained',
  Hard: 'hardened',
  Brutal: 'danger',
};

function offerCard(offer, run) {
  const chosen = offer.chosen;
  return card({
    title: offer.name,
    body: offer.code,
    pills: [
      pill(offer.difficulty, DIFFICULTY_VARIANT[offer.difficulty] || null),
      pill(offer.economy),
      chosen ? pill('chosen', 'accent') : null,
    ].filter(Boolean),
    state: chosen ? 'taken' : null,
    footer: [
      button(chosen ? 'Chosen' : 'Choose', {
        variant: chosen ? 'quiet' : null,
        // Committed means the stage is settled and the mission with it:
        // choosing another would be choosing after the fact.
        disabled: chosen || run.committed || !run.active,
        onClick: () => act('shop.select', { code: offer.code }),
      }),
    ],
  });
}

function shelfCard(entry, run) {
  return card({
    title: entry.bought ? `Owned — ${entry.name}` : entry.name,
    body: entry.target || entry.kind,
    state: entry.bought ? 'taken' : null,
    footer: [
      el('span', {
        class: entry.bought ? 'muted' : 'ore',
        text: entry.bought ? 'Bought' : `${count(entry.price)} Ore`,
      }),
      button(entry.bought ? 'Bought' : 'Buy', {
        disabled: entry.bought || !run.active || run.coins < entry.price,
        onClick: () => act('shop.buy', { reward_id: entry.reward_id }),
      }),
    ],
  });
}

/** A button that asks once, the way the skirmish run's does. */
function giveUpButton(run) {
  let asked = false;
  const node = button('Give up run', {
    variant: 'danger',
    disabled: !run.active,
    onClick: async () => {
      if (!asked) {
        asked = true;
        node.textContent = 'End this run?';
        return;
      }
      await act('shop.give_up');
    },
  });
  return node;
}

function header(run) {
  return row([
    el('div', { class: 'row' }, [
      el('strong', { text: run.progress }),
      pill(`${run.lives - run.lives_used} lives`),
      el('span', { class: 'ore', text: `${count(run.coins)} Ore` }),
    ]),
    el('div', { class: 'row' }, [
      button('Play the mission', {
        variant: 'primary',
        disabled: !run.active || !run.selected,
        onClick: async () => {
          if (await act('shop.launch')) watch();
        },
      }),
      giveUpButton(run),
    ]),
  ], { spread: true });
}

/* While a mission is up there is nothing to decide, so the screen says
 * so and keeps asking: the game reports what it did through its own log
 * and the reading is what records it. */
const POLL_MS = 2000;
let polling = null;

function watch() {
  if (polling) return;
  polling = setInterval(async () => {
    let session;
    try {
      session = await call('shop.session');
    } catch {
      return;
    }
    if (session.playing) return;
    clearInterval(polling);
    polling = null;
    await refresh();
    if (session.finished) status(session.finished.message || '');
  }, POLL_MS);
}

function startPanel(profile) {
  return section('No run', [
    notice(
      'No Shop run is being played. Starting one deals its first three '
      + 'missions and opens the shelf.',
    ),
    row([
      button('Start a run', {
        variant: 'primary',
        onClick: () => act('shop.start'),
      }),
      el('span', {
        class: 'muted',
        text: `${count(profile.meta_coins)} kept, `
          + `${profile.runs_completed} runs finished`,
      }),
    ]),
  ]);
}

async function render(root) {
  const session = await call('shop.session');
  if (session.playing) {
    watch();
    root.replaceChildren(notice(
      'A mission is being played. This screen comes back when the game '
      + 'closes.',
    ));
    return;
  }
  const run = await call('shop.run');
  if (!run) {
    root.replaceChildren(startPanel(await call('shop.profile')));
    return;
  }
  const parts = [section(null, header(run))];
  if (!run.active) {
    parts.push(section(null, notice(
      `This run is over — ${run.status}. Start another below.`,
    )));
    parts.push(startPanel(await call('shop.profile')));
  }
  if (run.offers.length) {
    parts.push(section(
      run.committed ? 'Playing' : 'Choose a mission',
      grid(run.offers.map((offer) => offerCard(offer, run)), { wide: true }),
    ));
  }
  const shelf = run.shelf;
  for (const [name, entries] of [
    ['Units', shelf.units],
    ['Powers', shelf.powers],
    ['Upgrades', shelf.upgrades],
  ]) {
    if (entries.length) {
      parts.push(section(
        name, grid(entries.map((entry) => shelfCard(entry, run))),
      ));
    }
  }
  parts.push(section('This run', stats(run.summary)));
  root.replaceChildren(...parts);
}

register('shoprun', render);
