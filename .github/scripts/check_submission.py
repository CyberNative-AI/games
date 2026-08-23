#!/usr/bin/env python3
"""Static checks for a CyberNative Games submission folder.

Reads files only. Never executes, imports, or serves submitted code.
"""
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser

MAX_BYTES = 20 * 1024 * 1024  # 20 MiB
REQUIRED_MANIFEST_FIELDS = ["name", "slug", "version", "entry", "creator", "license"]
CODE_EXTS = {".html", ".htm", ".js", ".mjs", ".css"}
HTML_EXTS = {".html", ".htm"}
JS_EXTS = {".js", ".mjs"}
CSS_EXTS = {".css"}

EXTERNAL_ORIGIN_PATTERNS = [
    re.compile(r"\bfetch\s*\(", re.IGNORECASE),
    re.compile(r"\bXMLHttpRequest\b", re.IGNORECASE),
    re.compile(r"\bWebSocket\s*\(", re.IGNORECASE),
    re.compile(r"\bEventSource\s*\(", re.IGNORECASE),
    re.compile(
        r"""(?:src|srcset|href|poster)\s*=\s*["']\s*(?:https?:)?//""",
        re.IGNORECASE,
    ),
    re.compile(r"""url\(\s*["']?\s*(?:https?:)?//""", re.IGNORECASE),
    re.compile(r"@import\s+(?:url\()?\s*['\"]?\s*(?:https?:)?//", re.IGNORECASE),
]

# An absolute URL written as a string literal. The patterns above match the
# *syntax* of a load, so they only see a URL that sits directly after `src=`
# or inside `url(`; `new Audio("https://…")`, `import(CDN)` and
# `img.src = u` all route the same load through a plain string and slip past.
# This pattern matches the URL itself, so it catches every one of them —
# which is why it is scanned only against code a browser executes. In a data
# block a quoted absolute URL is ordinary data, not a load: our own pages
# ship `{"@context":"https://schema.org"}` in a JSON-LD script.
# `(?:\\?/){2}` also accepts the `https:\/\/` form legal in a JS string, and
# the trailing class requires a host character so `"//"` alone is not a URL.
ABSOLUTE_URL_LITERAL = re.compile(
    r"""["'`]\s*(?:https?:)?(?:\\?/){2}[^\s"'`]""", re.IGNORECASE
)

EVENT_HANDLER_ATTR = re.compile(r"""\son[a-z]+\s*=\s*["']""", re.IGNORECASE)

# HTML's "JavaScript MIME type essence match" list, plus the three inline
# script kinds a `script-src 'self'` policy still blocks. A <script> whose
# type is outside this set is a data block: the browser never executes it and
# production CSP allows it — e.g. <script type="application/ld+json">.
EXECUTABLE_SCRIPT_TYPES = {
    "application/ecmascript",
    "application/javascript",
    "application/x-ecmascript",
    "application/x-javascript",
    "text/ecmascript",
    "text/javascript",
    "text/javascript1.0",
    "text/javascript1.1",
    "text/javascript1.2",
    "text/javascript1.3",
    "text/javascript1.4",
    "text/javascript1.5",
    "text/jscript",
    "text/livescript",
    "text/x-ecmascript",
    "text/x-javascript",
    "module",
    "importmap",
    "speculationrules",
}

_WORD_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)
# After one of these a `/` starts a regular expression, not a division.
_KEYWORDS_BEFORE_REGEX = {
    "await", "case", "delete", "do", "else", "in", "instanceof", "new", "of",
    "return", "throw", "typeof", "void", "yield",
}


# --- comment stripping -------------------------------------------------
#
# The origin rules describe what a game *does*, so they are scanned against
# code with comments removed: a submission that says "no fetch() here" in a
# comment is complying with the rule, not breaking it. String literals are
# still scanned — a real reference can hide in one, a comment cannot run.
#
# The strippers are string- and regex-literal-aware so that a quote or a
# `/*` inside a literal can never make live code look commented out. When
# they cannot tell, they keep the text: keeping text can only cost a false
# positive, dropping it would cost a false negative.


def _skip_string(text, index):
    """Return the index just past the string literal starting at `index`."""
    quote = text[index]
    i = index + 1
    n = len(text)
    while i < n:
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == quote:
            return i + 1
        if char == "\n" and quote != "`":
            return i  # unterminated: stop at the line break
        i += 1
    return n


def _skip_regex_literal(text, index):
    """Return the index just past the regex literal at `index`, or None."""
    i = index + 1
    n = len(text)
    in_class = False
    while i < n:
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "\n":
            return None  # regex literals cannot span lines
        if in_class:
            if char == "]":
                in_class = False
        elif char == "[":
            in_class = True
        elif char == "/":
            i += 1
            while i < n and text[i].isalpha():
                i += 1  # flags
            return i
        i += 1
    return None


def _regex_can_start(prev_char, prev_word):
    if prev_char is None:
        return True
    if prev_char in _WORD_CHARS:
        return prev_word in _KEYWORDS_BEFORE_REGEX
    return prev_char not in (")", "]")


def strip_js_comments(text, html_comments=False):
    """Remove JavaScript comments, leaving string and regex literals intact.

    `html_comments` also treats the legacy `<!--` / `-->` forms as comments,
    which is what a browser does inside an HTML <script> element.
    """
    out = []
    i = 0
    n = len(text)
    prev_char = None
    prev_word = ""
    at_line_start = True

    def line_end(start):
        stop = text.find("\n", start)
        return n if stop == -1 else stop

    while i < n:
        char = text[i]

        if html_comments and text.startswith("<!--", i):
            i = line_end(i)
            continue
        if html_comments and at_line_start and text.startswith("-->", i):
            i = line_end(i)
            continue

        if char == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                i = line_end(i)
                continue
            if nxt == "*":
                stop = text.find("*/", i + 2)
                i = n if stop == -1 else stop + 2
                out.append(" ")
                continue
            if _regex_can_start(prev_char, prev_word):
                stop = _skip_regex_literal(text, i)
                if stop is not None:
                    out.append(text[i:stop])
                    prev_char, prev_word, at_line_start = "/", "", False
                    i = stop
                    continue

        if char in "\"'`":
            stop = _skip_string(text, i)
            out.append(text[i:stop])
            prev_char, prev_word, at_line_start = char, "", False
            i = stop
            continue

        out.append(char)
        if char == "\n":
            at_line_start = True
        elif not char.isspace():
            at_line_start = False
            prev_char = char
            prev_word = prev_word + char if char in _WORD_CHARS else ""
        i += 1

    return "".join(out)


def strip_css_comments(text):
    """Remove CSS block comments, leaving string literals intact."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if char == "/" and text.startswith("/*", i):
            stop = text.find("*/", i + 2)
            i = n if stop == -1 else stop + 2
            out.append(" ")
            continue
        if char in "\"'":
            stop = _skip_string(text, i)
            out.append(text[i:stop])
            i = stop
            continue
        out.append(char)
        i += 1
    return "".join(out)


# --- HTML scanning -----------------------------------------------------


class _HtmlScan(HTMLParser):
    """Collect the parts of an HTML file the origin/inline rules apply to.

    `tags` holds the raw source of every start tag and `scripts` holds one
    entry per <script> element. Element bodies arrive with their comments
    stripped and split by whether the browser runs them: `embedded_code` for
    <style> and executable <script> bodies, `embedded_data` for the bodies of
    data blocks such as <script type="application/ld+json">. Comments and
    text nodes are deliberately left out: neither can reference an origin or
    execute.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.scripts = []
        self.embedded_code = []
        self.embedded_data = []
        self._open_script = None
        self._in_style = False

    @property
    def embedded(self):
        return self.embedded_code + self.embedded_data

    def handle_starttag(self, tag, attrs):
        source = self.get_starttag_text() or ""
        self.tags.append(source)
        if tag == "script":
            self._open_script = {"attrs": attrs, "content": ""}
            self.scripts.append(self._open_script)
        elif tag == "style":
            self._in_style = True

    def handle_startendtag(self, tag, attrs):
        # A browser treats `<script/>` as an open tag whose content runs, so
        # mirror that instead of letting a stray slash hide inline code.
        self.handle_starttag(tag, attrs)
        if tag in self.CDATA_CONTENT_ELEMENTS:
            self.set_cdata_mode(tag)
        else:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "script":
            self._open_script = None
        elif tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._open_script is not None:
            self._open_script["content"] += data
            stripped = strip_js_comments(data, html_comments=True)
            if script_is_executable(self._open_script["attrs"]):
                self.embedded_code.append(stripped)
            else:
                self.embedded_data.append(stripped)
        elif self._in_style:
            self.embedded_code.append(strip_css_comments(data))


def scan_html(text):
    """Parse `text`, or return a scan flagged as failed if it cannot be."""
    scan = _HtmlScan()
    try:
        scan.feed(text)
        scan.close()
    except Exception:
        return scan, False
    return scan, True


def script_has_src(attrs):
    return any(name == "src" for name, _value in attrs)


def script_is_executable(attrs):
    """True if a browser would run this <script>, or CSP would block it."""
    type_value = None
    for name, value in attrs:
        if name == "type":
            type_value = value or ""
    if type_value is None:
        return True  # no type attribute: classic JavaScript
    essence = type_value.split(";")[0].strip().lower()
    if not essence:
        return True  # type="" is also classic JavaScript
    return essence in EXECUTABLE_SCRIPT_TYPES


def scannable_code(path, text):
    """The text of `path` the external-origin rules apply to, in two parts.

    The first part is what a browser executes — a .js/.mjs or .css file, and
    the <style> and executable <script> bodies of an HTML file. The second is
    everything else the rules still read: start tags, and the bodies of data
    blocks. Only the executable part is scanned for absolute-URL literals.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in JS_EXTS:
        return strip_js_comments(text), ""
    if ext in CSS_EXTS:
        return strip_css_comments(text), ""
    if ext in HTML_EXTS:
        scan, ok = scan_html(text)
        if not ok:
            # Unparseable: scan the whole file, but only for load syntax. It
            # already fails the inline-script rule, so nothing is let through.
            return "", text
        return "\n".join(scan.embedded_code), "\n".join(scan.tags + scan.embedded_data)
    return "", text


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


def read_text(path):
    """File contents, or None if it cannot be read."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return None


def check_external_origins(sub_dir):
    offenders = []
    for path in iter_code_files(sub_dir):
        text = read_text(path)
        if text is None:
            continue
        executable, other = scannable_code(path, text)
        hit = any(
            pattern.search(executable) or pattern.search(other)
            for pattern in EXTERNAL_ORIGIN_PATTERNS
        ) or ABSOLUTE_URL_LITERAL.search(executable)
        if hit:
            offenders.append(os.path.relpath(path, sub_dir))
    if offenders:
        return False, "External origin or network API reference found in: " + ", ".join(sorted(offenders))
    return True, "No external origins or network APIs found in shipped files."


def check_inline_scripts(sub_dir):
    offenders = []
    for path in iter_code_files(sub_dir):
        if os.path.splitext(path)[1].lower() not in HTML_EXTS:
            continue
        text = read_text(path)
        if text is None:
            continue
        scan, parsed = scan_html(text)
        if not parsed:
            offenders.append(os.path.relpath(path, sub_dir))
            continue
        # A <script> is inline only if it has no src and the browser would
        # execute it. Content that is only whitespace is a no-op the CSP
        # never sees; anything else — including a legacy <!-- --> wrapper,
        # whose body still runs — is inline JavaScript.
        has_inline = any(
            not script_has_src(script["attrs"])
            and script_is_executable(script["attrs"])
            and script["content"].strip()
            for script in scan.scripts
        )
        if not has_inline:
            has_inline = any(
                EVENT_HANDLER_ATTR.search(chunk)
                for chunk in scan.tags + scan.embedded
            )
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
