#!/usr/bin/env python3
"""Static checks for a CyberNative Games submission folder.

Reads files only. Never executes, imports, or serves submitted code.
"""
import json
import os
import re
import subprocess
import sys

MAX_BYTES = 20 * 1024 * 1024  # 20 MiB
REQUIRED_MANIFEST_FIELDS = ["name", "slug", "version", "entry", "creator", "license"]
CODE_EXTS = {".html", ".htm", ".js", ".mjs", ".css"}

EXTERNAL_ORIGIN_PATTERNS = [
    re.compile(r"\bfetch\s*\(", re.IGNORECASE),
    re.compile(r"\bXMLHttpRequest\b", re.IGNORECASE),
    re.compile(r"\bWebSocket\s*\(", re.IGNORECASE),
    re.compile(r"\bEventSource\s*\(", re.IGNORECASE),
    re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//""", re.IGNORECASE),
    re.compile(r"""url\(\s*["']?\s*(?:https?:)?//""", re.IGNORECASE),
    re.compile(r"@import\s+(?:url\()?\s*['\"]?\s*(?:https?:)?//", re.IGNORECASE),
]

INLINE_SCRIPT_TAG = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>\s*[^<\s]", re.IGNORECASE)
EVENT_HANDLER_ATTR = re.compile(r"""\son[a-z]+\s*=\s*["']""", re.IGNORECASE)


def _git_changed_paths(base_ref):
    """Return paths changed on HEAD relative to base_ref, or None on failure."""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            capture_output=True, text=True, check=True, cwd=os.getcwd(),
        ).stdout
    except Exception:
        return None
    return [line for line in out.splitlines() if line]


def find_changed_submission_dirs(base_ref):
    """Return submission dirs touched by this PR, or all of them if that fails."""
    paths = _git_changed_paths(base_ref)
    if paths is not None:
        dirs = set()
        for line in paths:
            if line.startswith("submissions/"):
                parts = line.split("/")
                if len(parts) >= 2:
                    dirs.add(os.path.join("submissions", parts[1]))
        if dirs:
            return sorted(dirs)
    return sorted(
        os.path.join("submissions", d)
        for d in os.listdir("submissions")
        if os.path.isdir(os.path.join("submissions", d))
    )


def find_out_of_scope_paths(base_ref):
    """Changed paths that are not under submissions/. Empty if git is unavailable."""
    paths = _git_changed_paths(base_ref)
    if not paths:
        return []
    return [
        p for p in paths
        if p != "submissions" and not p.startswith("submissions/")
    ]


def advisory_out_of_scope_note(base_ref):
    """Advisory text only — never changes pass/fail."""
    paths = find_out_of_scope_paths(base_ref)
    if not paths:
        return None
    listed = ", ".join(f"`{p}`" for p in paths)
    return (
        f"This PR changes files outside `submissions/`: {listed}. "
        "A submission PR should only add files under `submissions/<your-folder>/`. "
        "A reviewer will treat other changes as out of scope."
    )


def check_manifest(sub_dir):
    path = os.path.join(sub_dir, "game-manifest.json")
    if not os.path.isfile(path):
        return False, "game-manifest.json is missing at the root of the submission folder."
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return False, f"game-manifest.json is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return False, "game-manifest.json must contain a JSON object."
    missing = [field for field in REQUIRED_MANIFEST_FIELDS if not data.get(field)]
    if missing:
        return False, f"game-manifest.json is missing required field(s): {', '.join(missing)}."
    return True, "game-manifest.json present with all required fields.", data


def check_license(sub_dir):
    path = os.path.join(sub_dir, "LICENSE")
    if os.path.isfile(path):
        return True, "LICENSE file present."
    return False, "LICENSE file is missing from the submission folder."


def check_size(sub_dir):
    total = 0
    for root, _dirs, files in os.walk(sub_dir):
        for name in files:
            total += os.path.getsize(os.path.join(root, name))
    mib = total / (1024 * 1024)
    if total <= MAX_BYTES:
        return True, f"Submission is {mib:.2f} MiB, within the 20 MiB cap."
    return False, f"Submission is {mib:.2f} MiB, over the 20 MiB cap."


def iter_code_files(sub_dir):
    for root, _dirs, files in os.walk(sub_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in CODE_EXTS:
                yield os.path.join(root, name)


def check_external_origins(sub_dir):
    offenders = []
    for path in iter_code_files(sub_dir):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        for pattern in EXTERNAL_ORIGIN_PATTERNS:
            if pattern.search(text):
                offenders.append(os.path.relpath(path, sub_dir))
                break
    if offenders:
        return False, "External origin or network API reference found in: " + ", ".join(sorted(offenders))
    return True, "No external origins or network APIs found in shipped files."


def check_inline_scripts(sub_dir):
    offenders = []
    for path in iter_code_files(sub_dir):
        if os.path.splitext(path)[1].lower() not in (".html", ".htm"):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        has_inline = bool(INLINE_SCRIPT_TAG.search(text)) or bool(EVENT_HANDLER_ATTR.search(text))
        if has_inline:
            offenders.append(os.path.relpath(path, sub_dir))
    if offenders:
        return False, "Inline script or event-handler attribute found in: " + ", ".join(sorted(offenders))
    return True, "No inline scripts or event-handler attributes found."


def check_entry(sub_dir, manifest):
    entry = manifest.get("entry") if manifest else None
    if not entry:
        return False, "No entry path to check (manifest missing or invalid)."
    entry_path = os.path.normpath(os.path.join(sub_dir, entry))
    sub_dir_abs = os.path.normpath(sub_dir)
    if not entry_path.startswith(sub_dir_abs + os.sep) and entry_path != sub_dir_abs:
        return False, f"entry path '{entry}' resolves outside the submission folder."
    if os.path.isfile(entry_path):
        return True, f"entry path '{entry}' exists."
    return False, f"entry path '{entry}' does not exist in the submission folder."


def run_checks(sub_dir):
    results = []

    manifest_result = check_manifest(sub_dir)
    if len(manifest_result) == 3:
        ok, msg, manifest = manifest_result
    else:
        ok, msg = manifest_result
        manifest = None
    results.append(("game-manifest.json has required fields", ok, msg))

    ok, msg = check_license(sub_dir)
    results.append(("LICENSE file present", ok, msg))

    ok, msg = check_size(sub_dir)
    results.append(("Submission is 20 MiB or less", ok, msg))

    ok, msg = check_external_origins(sub_dir)
    results.append(("No external origins or network APIs", ok, msg))

    ok, msg = check_inline_scripts(sub_dir)
    results.append(("No inline scripts or event handlers", ok, msg))

    ok, msg = check_entry(sub_dir, manifest)
    results.append(("Entry path exists", ok, msg))

    return results


def emit_report_and_exit(report, exit_code):
    """Write the report to stdout, the step summary, and REPORT_OUTPUT_PATH, then exit."""
    print(report)

    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a", encoding="utf-8") as f:
        f.write(report + "\n")

    out_path = os.environ.get("REPORT_OUTPUT_PATH")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)

    sys.exit(exit_code)


def _heading_with_advisory(base_ref, fallback_body=None):
    """Build the report heading, inserting the out-of-scope note above the rules."""
    note = advisory_out_of_scope_note(base_ref)
    if fallback_body is not None:
        parts = ["## Submission check results", ""]
        if note:
            parts.extend([note, ""])
        parts.append(fallback_body)
        return "\n".join(parts)
    lines = ["## Submission check results\n"]
    if note:
        lines.append(note + "\n")
    return lines


def main():
    base_ref = os.environ.get("BASE_REF", "origin/main")
    submissions_root = "submissions"
    if not os.path.isdir(submissions_root):
        emit_report_and_exit(
            _heading_with_advisory(base_ref, "No submissions/ directory found."),
            0,
        )

    sub_dirs = find_changed_submission_dirs(base_ref)
    sub_dirs = [d for d in sub_dirs if os.path.isdir(d)]
    if not sub_dirs:
        emit_report_and_exit(
            _heading_with_advisory(base_ref, "No submission folders found to check."),
            0,
        )

    all_passed = True
    report_lines = _heading_with_advisory(base_ref)

    for sub_dir in sub_dirs:
        report_lines.append(f"### `{sub_dir}`\n")
        try:
            results = run_checks(sub_dir)
        except Exception as exc:
            all_passed = False
            report_lines.append(
                f"- ❌ **Checker error** — Unexpected {type(exc).__name__} while checking `{sub_dir}`."
            )
            report_lines.append("")
            continue
        for name, ok, msg in results:
            icon = "✅" if ok else "❌"
            report_lines.append(f"- {icon} **{name}** — {msg}")
            if not ok:
                all_passed = False
        report_lines.append("")

    if all_passed:
        report_lines.append("All checks passed. This submission is ready for human play-test review.")
    else:
        report_lines.append("One or more checks failed. Fix the issues above and push again — checks re-run automatically.")

    emit_report_and_exit("\n".join(report_lines), 0 if all_passed else 1)


if __name__ == "__main__":
    main()
