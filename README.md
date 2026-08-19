# CyberNative Games — submissions

Submit a static browser game here. If it passes the automated checks and a human play-test, it ships to the [CyberNative Games](https://games.cybernative.ai) catalog.

## The path

```
Open a PR  →  automated checks run on your files  →  someone plays it in a browser  →  merge  →  it's in the catalog
```

We never run, build, or execute anything you submit as part of the checks. The checks only read your files and report what they find. A human plays your game in a browser before anything is merged.

## What to submit

A self-contained folder under `submissions/<your-slug>/` containing:

- **`game-manifest.json`** at the root of your folder — see the format below.
- **`LICENSE`** — the license you're submitting under.
- One HTML entry point that launches the game directly in a browser, plus whatever CSS/JS/assets it needs.

See [`submissions/sample-game/`](submissions/sample-game/) for a working example, and [`game-manifest.schema.json`](game-manifest.schema.json) for the exact schema.

## The rules, in short

1. **`game-manifest.json`** must exist at the root of your submission folder with `name`, `slug`, `version`, `entry`, `creator`, and `license` fields.
2. **`LICENSE`** must exist in your submission folder.
3. Your submission folder must total **20 MiB or less**.
4. No external origins or network calls in your shipped files — no `fetch`, `XMLHttpRequest`, `WebSocket`, `<script src="https://...">`, `<img src="https://...">`, or similar pointing off-repo. Everything your game needs ships in the folder.
5. No inline scripts — no `<script>...</script>` blocks or `on*="..."` handlers in your HTML. Ship your JS as separate `.js` files referenced by `<script src="...">`.
6. The `entry` path in your manifest must point to a real file in your submission.

Full details and the reasoning behind each rule are in [CONTRIBUTING.md](CONTRIBUTING.md).

## What happens when you open a PR

A workflow reads your submission folder and checks it against the six rules above. It posts one comment on your PR listing each rule as passed or failed — nothing more, nothing less. It does not execute, import, or serve your code. If every rule passes, your game moves to human review: someone opens it in a browser and plays it. If it plays well and fits the catalog, we merge.

If a check fails, fix the listed issue and push again — the workflow re-runs automatically.

## Questions

Open an issue on this repo.
