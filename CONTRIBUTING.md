# Contributing a game

## 1. Build your submission folder

Create `submissions/<your-slug>/` in a fork of this repo. Use a lowercase, hyphenated slug that matches the `slug` field in your manifest.

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

The required fields are `name`, `slug`, `version`, `entry`, `creator`, and `license`. The full schema is in [`game-manifest.schema.json`](game-manifest.schema.json).

## 3. Open a pull request

The public requirements are grouped into six categories:

### Packaging

Include the manifest, licence, entry point, and a self-contained folder within the public size limit.

### Security

Submit original, reviewable browser-game content.

### Dependencies

Bundle what the game needs and declare its licence.

### Runtime

The entry point must boot and support keyboard or touch play.

### Media

Keep the package within the public size limit and include media in the submission.

### Editorial

Submit an original game that fits the catalog and its audience.

## 4. Public check and private review

The public check does not execute, build, bundle, transpile, or import your submission. It posts one opaque conclusion: **Passed security review** or **Checks need attention: _category_**. Detailed review is private, and public comments contain no implementation detail.

## 5. After checks pass

Someone opens your game in a browser and plays it. If it works, fits the catalog, and clears private review, we merge your PR and it ships to [games.cybernative.ai](https://games.cybernative.ai).

If checks report a category, address that category and push again — the workflow re-runs on every push.
