---
name: launcher-ui
description: How the launcher's interface is built - the web front end in a WebView2 window, the API boundary it talks across, the design tokens and components it is made of, and the rules that keep the domain free of it. Use when writing or changing anything under web/ or randomizer/api/.
---

# The launcher's interface

The interface is HTML, CSS and ES modules in a WebView2 window that
pywebview opens. The launcher's 68,000 lines of domain code have never
imported a toolkit and never will; everything a screen needs crosses one
boundary as plain data.

## The boundary

`randomizer/api/` is the only place the two meet.

```python
from randomizer.api.contract import action

@action('skirmish.run', 'The run being played, or nothing')
def run():
    return run_view(...)          # dicts, lists, strings, numbers, bools
```

Rules, all checked by `randomizer/api/self_check.py`:

- **Plain data only.** If it cannot be written as JSON it cannot cross.
  No dataclasses, no enums, no `Path`, no `None` where a screen expects a
  shape - give it `''` or `[]`.
- **A failure is a reply**, never an exception: there is a bridge in the
  middle that cannot carry one. `call()` returns
  `{'ok': False, 'error': ..., 'kind': ...}`.
- **No toolkit import** under `randomizer/api/`, and no domain module
  imports the api package. The rules never learn what draws them.
- A view function (`run_view`, `offer_view`, `upgrade_view`) is where an
  object becomes a reading. Screens never reach past them.

## The front end

```
web/
  index.html          the shell: header, tabs, one <main> per view
  styles/
    tokens.css        the only place a colour or a size is decided
    base.css          resets, typography, the shell's own layout
    components.css    card, table, button, pill, panel, field
  components/*.js     one file per component, no framework
  views/*.js          one file per screen; asks the api, renders, binds
  app.js              routing between views, the api wrapper
```

- **No npm, no bundler, no framework.** Plain ES modules with
  `<script type="module">`. The build stays PowerShell + PyInstaller and
  the output stays one file.
- **Tokens or nothing.** Never write a hex colour or a pixel size in a
  component or a view. If a value is missing, add a token.
- Components take data and return an element. They do not fetch, do not
  know about the api, and do not reach outside themselves.
- A view owns one screen: it asks the api, hands data to components, and
  binds events back to api calls. It is the only place that knows both.

## Talking to the launcher

```js
import { call } from './app.js';
const run = await call('skirmish.run');       // throws with .message on failure
```

`call` unwraps the reply: it returns `result` or throws an `Error` carrying
`error` and `kind`. A view catches it and shows the message; it never shows
a stack trace and never fails silently.

## Style

- Dark first. The launcher sits beside a game that is dark.
- Motion is small and fast: 120-160ms, opacity and 1-2px of transform.
  Nothing slides across the screen.
- Density over decoration. This is a tool someone uses between matches,
  not a landing page.
- Every number a player might act on gets a unit or a label. `62 Ore`,
  not `62`.

## When adding a screen

1. Add the reading to `randomizer/api/<mode>.py` as an `@action`, with a
   view function if it returns objects.
2. Check it: `call('<name>')` answers, and the reply is JSON-safe.
3. Add the view under `web/views/`, built from existing components.
4. Add a component only when two views need it.
5. Register the view in `app.js` and give it a tab in `index.html`.
