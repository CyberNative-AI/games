# Contributing a game

## 1. Build your submission folder

Create `submissions/<your-slug>/` in a fork of this repo. Use a lowercase, hyphenated slug that matches the `slug` field in your manifest (e.g. `submissions/star-drift/`).

Inside it, put:

- `game-manifest.json`
- `LICENSE`
- your game's HTML entry point and any assets it needs (CSS, JS, images, audio, fonts)

Look at [`submissions/sample-game/`](submissions/sample-game/) for a minimal working layout.

## 2. Write your manifest

`game-manifest.json` sits at the root of your submission folder:

```json
{
  "name": "Star Drift",
  "slug": "star-drift",
  "version": "1.0.0",
  "entry": "index.html",
  "creator": "Jane Doe",
  "license": "MIT",
  "description": "A short drift-racing arcade game."
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Display name shown in the catalog. |
| `slug` | yes | Lowercase letters, numbers, and hyphens only. Should match your folder name. |
| `version` | yes | Any version string, e.g. `1.0.0`. |
| `entry` | yes | Path to your HTML entry file, relative to the manifest — e.g. `index.html` or `play/game.html`. |
| `creator` | yes | Your name or handle, shown in the catalog. |
| `license` | yes | License identifier or short name, e.g. `MIT`, `CC-BY-4.0`, `All rights reserved`. |
| `description` | no | One or two sentences shown in the catalog. |

The full schema is in [`game-manifest.schema.json`](game-manifest.schema.json).

## 3. Open a pull request

Open a PR with your submission folder added. A workflow runs automatically and posts one comment on your PR checking your submission against six rules:

### The manifest exists and has the required fields
`game-manifest.json` must be present at the root of your submission folder and include `name`, `slug`, `version`, `entry`, `creator`, and `license`.

### A LICENSE file is present
Every submission needs a `LICENSE` file in its folder so players and the catalog know the terms it's shared under.

### Total size is 20 MiB or less
Keep your submission folder — all HTML, CSS, JS, and assets combined — at or under 20 MiB. Compress art and audio before submitting if you're close to the limit.

### No external origins or network calls
Your shipped files can't reach outside the repo: no `fetch(...)`, `XMLHttpRequest`, `WebSocket`, `EventSource`, or tags like `<script src="https://...">` / `<img src="https://...">` pointing at an external URL. Bundle everything your game needs — fonts, libraries, art, audio — inside your submission folder. This keeps games playable offline and reviewable from static files alone.

An absolute URL written anywhere the browser runs code — a `.js`, `.mjs` or `.css` file, or a `<style>` or inline `<script>` body — fails this check even when it isn't sitting next to `src=`, because the load happens all the same: `new Audio("https://…")`, `import(CDN)`, `img.src = url`. Use a relative path (`./assets/theme.mp3`) and ship the file. Two places are exempt, because neither loads anything: comments, and data blocks such as `<script type="application/ld+json">`.

### No inline scripts
No `<script>...your code...</script>` blocks and no `on*="..."` event-handler attributes (`onclick`, `onload`, etc.) in your HTML. Put your JavaScript in `.js` files and load them with `<script src="your-file.js"></script>`. This is also exactly what the production site's content-security policy allows — code that passes this check will actually run when it ships.

### The entry file exists
The `entry` path in your manifest must point to a file that actually exists in your submission folder.

## 4. What we don't do

We don't execute, build, bundle, transpile, or import anything from your submission during checks. The checks only read file names, sizes, and text content. This means the checks can't catch a runtime bug or a game that doesn't actually work — that's what the human play-test after checks pass is for.

## 5. After checks pass

Someone opens your game in a browser and plays it. If it works, fits the catalog, and doesn't violate the rules above in a way the automated checks missed, we merge your PR and it ships to [games.cybernative.ai](https://games.cybernative.ai).

If checks fail, the PR comment tells you exactly which rule failed. Fix it and push again — the workflow re-runs on every push.
