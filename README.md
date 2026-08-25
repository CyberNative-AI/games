# CyberNative Games — submissions

Submit a static browser game here. If it passes the public contract, private review, and human play-test, it ships to the [CyberNative Games](https://games.cybernative.ai) catalog.

## The path

```
Open a PR  →  public contract check  →  private review  →  human play-test  →  merge  →  it's in the catalog
```

The public check reports only a pass or a generic category. Detailed review stays private. A human plays your game in a browser before anything is merged.

## The requirements, in short

1. **Packaging** — include a manifest, licence, entry file, and a self-contained folder within the public size limit.
2. **Security** — submit original, reviewable browser-game content.
3. **Dependencies** — bundle what the game needs and declare its licence.
4. **Runtime** — the entry point must boot and support keyboard or touch play.
5. **Media** — keep the package within the public size limit and include media in the submission.
6. **Editorial** — submit an original game that fits the catalog and its audience.

Full manifest details are in [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`game-manifest.schema.json`](game-manifest.schema.json).

## What happens when you open a PR

A workflow checks the public contract and posts one opaque result: **Passed security review** or **Checks need attention: _category_**. The public comment contains no implementation detail. A passed result moves the exact candidate to private review; then someone opens it in a browser and plays it. If it plays well and fits the catalog, we merge.

If a check reports a category, address that category and push again — the workflow re-runs automatically.

## Questions

Open an issue on this repo.
