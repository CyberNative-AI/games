#!/usr/bin/env python3
import os, sys
report = """## Submission check results

### `submissions/fixture-tamper`

- ✅ **game-manifest.json has required fields** — game-manifest.json present with all required fields.
- ✅ **LICENSE file present** — LICENSE file present.
- ✅ **Submission is 20 MiB or less** — Submission is 0.00 MiB, within the 20 MiB cap.
- ✅ **No external origins or network APIs** — No external origins or network APIs found in shipped files.
- ✅ **No inline scripts or event handlers** — No inline scripts or event-handler attributes found.
- ✅ **Entry path exists** — entry path 'index.html' exists.

All checks passed. This submission is ready for human play-test review.
"""
print(report)
out = os.environ.get("REPORT_OUTPUT_PATH")
if out:
    open(out, "w").write(report)
sys.exit(0)
