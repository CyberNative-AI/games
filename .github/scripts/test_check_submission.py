#!/usr/bin/env python3
"""Fixture tests for the submission checker.

Run from the repository root:

    python3 .github/scripts/test_check_submission.py

Every test builds a throwaway submission folder in a temp directory and runs
the real checker against it. Nothing here executes submitted code.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKER_PATH = os.path.join(SCRIPT_DIR, "check_submission.py")
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

_spec = importlib.util.spec_from_file_location("check_submission", CHECKER_PATH)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

MANIFEST = """{
  "name": "Fixture",
  "slug": "fixture",
  "version": "1.0.0",
  "entry": "index.html",
  "creator": "Fixture Author",
  "license": "MIT"
}
"""

PLAIN_HTML = (
    '<!doctype html><html><head><meta charset="utf-8"><title>t</title></head>'
    '<body><script src="game.js"></script></body></html>\n'
)

ORIGINS_RULE = "No external origins or network APIs"
INLINE_RULE = "No inline scripts or event handlers"


class SubmissionCase(unittest.TestCase):
    """Base class that materialises a submission folder and runs the checker."""

    def build(self, files, manifest=MANIFEST, license_text="MIT\n"):
        """Return {rule name: (passed, message)} for a submission of `files`."""
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        sub_dir = os.path.join(root, "submissions", "fixture")
        os.makedirs(sub_dir)
        if manifest is not None:
            files = dict(files, **{"game-manifest.json": manifest})
        if license_text is not None:
            files = dict(files, LICENSE=license_text)
        for name, text in files.items():
            path = os.path.join(sub_dir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return {
            name: (ok, msg) for name, ok, msg in checker.run_checks(sub_dir)
        }

    def assertRulePasses(self, results, rule):
        ok, msg = results[rule]
        self.assertTrue(ok, f"expected {rule!r} to pass, got: {msg}")

    def assertRuleFails(self, results, rule):
        ok, msg = results[rule]
        self.assertFalse(ok, f"expected {rule!r} to fail, but it passed: {msg}")

    def assertAllPass(self, results):
        failed = [f"{name}: {msg}" for name, (ok, msg) in results.items() if not ok]
        self.assertEqual(failed, [], "expected all six checks to pass")


class DefectOneOfflineNote(SubmissionCase):
    """A comment that names a network API is compliance, not a violation."""

    def test_offline_note_passes_all_six(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": (
                "// This game is fully offline: no fetch() and no "
                "XMLHttpRequest anywhere.\nconst s=0;\n"
            ),
        })
        self.assertAllPass(results)

    def test_block_comment_and_css_comment_are_ignored(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": "/* no fetch(), no WebSocket(), no EventSource() */\nvar a=1;\n",
            "style.css": "/* never url(https://cdn.example.com/x.png) */\nbody{color:#000}\n",
        })
        self.assertRulePasses(results, ORIGINS_RULE)

    def test_html_comment_naming_an_origin_is_ignored(self):
        results = self.build({
            "index.html": (
                '<!doctype html><html><head><meta charset="utf-8"><title>t</title>\n'
                '<!-- no <script src="https://cdn.example.com/x.js"></script> here -->\n'
                '</head><body><script src="game.js"></script></body></html>\n'
            ),
            "game.js": "var a=1;\n",
        })
        self.assertRulePasses(results, ORIGINS_RULE)

    def test_real_network_call_still_fails(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": "// no comment here\nfetch('scores.json');\n",
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_string_literal_reference_still_fails(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": 'var code = "fetch(1)";\n',
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_offsite_anchor_still_fails(self):
        results = self.build({
            "index.html": (
                '<!doctype html><html><body>'
                '<a href="https://example.com/leaderboard">board</a>'
                '<script src="game.js"></script></body></html>\n'
            ),
            "game.js": "var a=1;\n",
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_offsite_script_src_still_fails(self):
        results = self.build({
            "index.html": (
                '<!doctype html><html><body>'
                '<script src="https://cdn.example.com/engine.js"></script>'
                '</body></html>\n'
            ),
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_offsite_css_url_and_import_still_fail(self):
        for css in (
            'body{background:url("https://cdn.example.com/bg.png")}\n',
            '@import url("https://fonts.example.com/f.css");\nbody{color:#000}\n',
        ):
            with self.subTest(css=css):
                results = self.build({"index.html": PLAIN_HTML, "style.css": css})
                self.assertRuleFails(results, ORIGINS_RULE)

    def test_comment_marker_inside_a_string_cannot_hide_code(self):
        # A naive stripper would treat the "//" in the string as a line
        # comment and swallow the fetch( that follows it.
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": 'var protocolRelative = "//"; fetch(protocolRelative);\n',
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_regex_literal_cannot_hide_code(self):
        # The "/*" lives inside a character class, not a comment, so the
        # fetch( after it must still be seen.
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": 'var re = /[/*]/; fetch("x"); var q = 1 /* real comment */;\n',
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_html_comment_inside_a_script_element_cannot_hide_code(self):
        # `<!--` only comments out the rest of its own line; line two runs.
        results = self.build({
            "index.html": (
                "<!doctype html><html><body>\n<script><!--\n"
                'fetch("scores.json");\n-->\n</script>\n</body></html>\n'
            ),
        })
        self.assertRuleFails(results, ORIGINS_RULE)


class DefectTwoDataBlocks(SubmissionCase):
    """A <script> the browser never executes is not an inline script."""

    def test_json_ld_passes_all_six(self):
        results = self.build({
            "index.html": (
                '<!doctype html><html><head><meta charset="utf-8"><title>t</title>\n'
                '<script type="application/ld+json">'
                '{"@context":"https://schema.org","@type":"VideoGame","name":"t"}'
                '</script>\n'
                '</head><body><script src="game.js"></script></body></html>\n'
            ),
            "game.js": "const a=1;\n",
        })
        self.assertAllPass(results)

    def test_other_data_block_types_pass(self):
        for type_value in ("text/template", "application/json", "text/plain"):
            with self.subTest(type=type_value):
                results = self.build({
                    "index.html": (
                        f'<!doctype html><html><body><script type="{type_value}">'
                        "some data</script>"
                        '<script src="game.js"></script></body></html>\n'
                    ),
                    "game.js": "var a=1;\n",
                })
                self.assertRulePasses(results, INLINE_RULE)

    def test_html_comment_holding_an_event_handler_is_ignored(self):
        results = self.build({
            "index.html": (
                '<!doctype html><html><body>\n'
                '<!-- was: <button onclick="start()">Play</button> -->\n'
                '<button id="play">Play</button>\n'
                '<script src="game.js"></script></body></html>\n'
            ),
            "game.js": "var a=1;\n",
        })
        self.assertRulePasses(results, INLINE_RULE)

    def test_empty_and_whitespace_scripts_pass(self):
        results = self.build({
            "index.html": (
                "<!doctype html><html><body><script></script>\n"
                "<script>\n\n  \n</script>\n"
                '<script src="game.js"></script></body></html>\n'
            ),
            "game.js": "var a=1;\n",
        })
        self.assertRulePasses(results, INLINE_RULE)


class DefectThreeHiddenInlineScripts(SubmissionCase):
    """Anything a `script-src 'self'` policy would block must fail."""

    def test_legacy_comment_wrapped_script_fails(self):
        results = self.build({
            "index.html": (
                '<!doctype html><html><head><meta charset="utf-8"><title>t</title>'
                "</head><body>\n<script><!--\n"
                'var score=0; document.title="started";\n-->\n</script>\n'
                "</body></html>\n"
            ),
        })
        self.assertRuleFails(results, INLINE_RULE)

    def test_legacy_comment_wrapped_script_fails_only_that_rule(self):
        results = self.build({
            "index.html": (
                '<!doctype html><html><head><meta charset="utf-8"><title>t</title>'
                "</head><body>\n<script><!--\n"
                'var score=0; document.title="started";\n-->\n</script>\n'
                "</body></html>\n"
            ),
        })
        failed = [name for name, (ok, _msg) in results.items() if not ok]
        self.assertEqual(failed, [INLINE_RULE])

    def test_plain_inline_script_fails(self):
        results = self.build({
            "index.html": (
                "<!doctype html><html><body><script>var score=0;</script>"
                "</body></html>\n"
            ),
        })
        self.assertRuleFails(results, INLINE_RULE)

    def test_cdata_wrapped_script_fails(self):
        results = self.build({
            "index.html": (
                "<!doctype html><html><body><script>\n//<![CDATA[\n"
                "var score=0;\n//]]>\n</script></body></html>\n"
            ),
        })
        self.assertRuleFails(results, INLINE_RULE)

    def test_inline_module_and_importmap_fail(self):
        for type_value in ("module", "importmap", "text/javascript", "TEXT/JavaScript",
                           "text/javascript;charset=utf-8", ""):
            with self.subTest(type=type_value):
                results = self.build({
                    "index.html": (
                        f'<!doctype html><html><body><script type="{type_value}">'
                        "var score=0;</script></body></html>\n"
                    ),
                })
                self.assertRuleFails(results, INLINE_RULE)

    def test_self_closing_script_tag_fails(self):
        # A browser treats `<script/>` as an open tag, so the code after it runs.
        results = self.build({
            "index.html": (
                "<!doctype html><html><body><script/>var score=0;</script>"
                "</body></html>\n"
            ),
        })
        self.assertRuleFails(results, INLINE_RULE)

    def test_event_handler_attribute_fails(self):
        results = self.build({
            "index.html": (
                '<!doctype html><html><body>'
                '<button onclick="start()">Play</button>'
                '<script src="game.js"></script></body></html>\n'
            ),
            "game.js": "var a=1;\n",
        })
        self.assertRuleFails(results, INLINE_RULE)

    def test_event_handler_built_in_a_script_element_fails(self):
        results = self.build({
            "index.html": (
                "<!doctype html><html><body><script>\n"
                "document.body.innerHTML = '<b onclick=\"go()\">x</b>';\n"
                "</script></body></html>\n"
            ),
        })
        self.assertRuleFails(results, INLINE_RULE)


class RemoteLoadsThroughStrings(SubmissionCase):
    """A remote load hidden in a string literal is still a remote load.

    The load-syntax patterns only see a URL sitting directly after `src=` or
    inside `url(`, so anything that routes the URL through a variable or a
    constructor argument used to ship green and then break under the
    production CSP. These four are the fixtures from the report.
    """

    def test_string_origin_assigned_to_src_fails(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": (
                'const u = "https://cdn.example.com/tracker.js";\n'
                "new Image().src = u;\n"
            ),
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_dynamic_import_of_a_string_constant_fails(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": (
                'const CDN = "https://cdn.jsdelivr.net/npm/pkg/x.mjs";\n'
                "import(CDN).then(m => m.init());\n"
            ),
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_remote_audio_constructor_fails(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": 'new Audio("https://cdn.example.com/theme.mp3").play();\n',
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_injected_script_src_fails(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": (
                'const s = document.createElement("script");\n'
                's.src = "https://analytics.example.com/a.js";\n'
                "document.head.appendChild(s);\n"
            ),
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_protocol_relative_escaped_and_template_forms_fail(self):
        for js in (
            'const u = "//cdn.example.com/x.js";\nnew Image().src = u;\n',
            'const u = "https:\\/\\/cdn.example.com/x.js";\nnew Image().src = u;\n',
            "const u = `https://cdn.example.com/x.js`;\nnew Image().src = u;\n",
        ):
            with self.subTest(js=js):
                results = self.build({"index.html": PLAIN_HTML, "game.js": js})
                self.assertRuleFails(results, ORIGINS_RULE)

    def test_scheme_only_prefix_string_fails(self):
        # The URL is assembled at runtime, but the literal still carries the
        # scheme, so the load is as remote as a whole URL would be.
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": (
                'const base = "https://";\n'
                'new Image().src = base + "cdn.example.com/x.png";\n'
            ),
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    def test_srcset_and_poster_attributes_fail(self):
        for tag in (
            '<img srcset="https://cdn.example.com/a.png 2x" alt="a">',
            '<video poster="https://cdn.example.com/p.jpg"></video>',
        ):
            with self.subTest(tag=tag):
                results = self.build({
                    "index.html": (
                        f"<!doctype html><html><body>{tag}"
                        '<script src="game.js"></script></body></html>\n'
                    ),
                    "game.js": "var a=1;\n",
                })
                self.assertRuleFails(results, ORIGINS_RULE)

    def test_inline_style_block_with_a_remote_font_fails(self):
        results = self.build({
            "index.html": (
                "<!doctype html><html><head><style>\n"
                '@font-face{font-family:x;src:url("https://fonts.example.com/x.woff2")}\n'
                '</style></head><body><script src="game.js"></script></body></html>\n'
            ),
            "game.js": "var a=1;\n",
        })
        self.assertRuleFails(results, ORIGINS_RULE)

    # --- what the new rule must NOT catch ------------------------------

    def test_url_in_a_data_block_still_passes(self):
        # The regression guard: a quoted absolute URL is ordinary data in a
        # <script> the browser never runs, and our own pages ship one.
        for type_value in ("application/ld+json", "text/template", "application/json"):
            with self.subTest(type=type_value):
                results = self.build({
                    "index.html": (
                        "<!doctype html><html><head>"
                        f'<script type="{type_value}">'
                        '{"@context":"https://schema.org","name":"t"}'
                        "</script></head><body>"
                        '<script src="game.js"></script></body></html>\n'
                    ),
                    "game.js": "const a=1;\n",
                })
                self.assertAllPass(results)

    def test_url_in_a_comment_still_passes(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": (
                "// Fully offline: nothing is fetched.\n"
                "/* Not even https://example.com/ is contacted. */\nconst c=1;\n"
            ),
        })
        self.assertAllPass(results)

    def test_bare_double_slash_string_still_passes(self):
        # "//" with no host after it is a separator, not an origin.
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": 'const sep = "//";\nconst path = ["a", "b"].join(sep);\n',
        })
        self.assertAllPass(results)

    def test_relative_paths_still_pass(self):
        results = self.build({
            "index.html": PLAIN_HTML,
            "game.js": (
                'const sprites = "./assets/sprites.png";\n'
                'new Image().src = sprites;\n'
            ),
        })
        self.assertAllPass(results)


class UnchangedRules(SubmissionCase):
    """Rules the fix must not have moved."""

    def test_sample_game_passes_all_six(self):
        sub_dir = os.path.join(REPO_ROOT, "submissions", "sample-game")
        if not os.path.isdir(sub_dir):
            self.skipTest("submissions/sample-game is not present")
        results = {name: (ok, msg) for name, ok, msg in checker.run_checks(sub_dir)}
        self.assertAllPass(results)

    def test_missing_license_fails(self):
        results = self.build({"index.html": PLAIN_HTML}, license_text=None)
        self.assertRuleFails(results, "LICENSE file present")

    def test_missing_manifest_field_fails(self):
        results = self.build(
            {"index.html": PLAIN_HTML},
            manifest='{"name":"Fixture","slug":"fixture","entry":"index.html"}\n',
        )
        self.assertRuleFails(results, "game-manifest.json has required fields")

    def test_missing_entry_fails(self):
        results = self.build({"other.html": PLAIN_HTML})
        self.assertRuleFails(results, "Entry path exists")

    def test_entry_outside_the_folder_fails(self):
        results = self.build(
            {"index.html": PLAIN_HTML},
            manifest=MANIFEST.replace('"index.html"', '"../sample-game/index.html"'),
        )
        self.assertRuleFails(results, "Entry path exists")


class EndToEndRepro(unittest.TestCase):
    """The repro from CYBA-7067, run through the real command line."""

    def test_repro_exit_codes_and_report(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        shutil.copytree(
            os.path.join(REPO_ROOT, ".github"), os.path.join(root, ".github")
        )
        subs = os.path.join(root, "submissions")
        os.makedirs(subs)

        fixtures = {
            "offline-note": {
                "index.html": PLAIN_HTML,
                "game.js": (
                    "// This game is fully offline: no fetch() and no "
                    "XMLHttpRequest anywhere.\nconst s=0;\n"
                ),
            },
            "jsonld": {
                "index.html": (
                    '<!doctype html><html><head><meta charset="utf-8"><title>t</title>\n'
                    '<script type="application/ld+json">'
                    '{"@context":"https://schema.org","@type":"VideoGame","name":"t"}'
                    "</script>\n"
                    '</head><body><script src="game.js"></script></body></html>\n'
                ),
                "game.js": "const a=1;\n",
            },
            "legacy-inline": {
                "index.html": (
                    '<!doctype html><html><head><meta charset="utf-8"><title>t</title>'
                    "</head><body>\n<script><!--\n"
                    'var score=0; document.title="started";\n-->\n</script>\n'
                    "</body></html>\n"
                ),
            },
        }
        for slug, files in fixtures.items():
            folder = os.path.join(subs, slug)
            os.makedirs(folder)
            with open(os.path.join(folder, "LICENSE"), "w", encoding="utf-8") as f:
                f.write("MIT\n")
            with open(os.path.join(folder, "game-manifest.json"), "w", encoding="utf-8") as f:
                f.write(MANIFEST.replace("fixture", slug))
            for name, text in files.items():
                with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                    f.write(text)

        proc = subprocess.run(
            [sys.executable, ".github/scripts/check_submission.py"],
            cwd=root, capture_output=True, text=True,
        )
        report = proc.stdout
        self.assertEqual(proc.returncode, 1, report)

        sections = {}
        current = None
        for line in report.splitlines():
            if line.startswith("### "):
                current = line.strip("# `").strip("`")
                sections[current] = []
            elif current and line.startswith("- "):
                sections[current].append(line)

        for slug in ("offline-note", "jsonld"):
            self.assertEqual(
                [ln for ln in sections[f"submissions/{slug}"] if "❌" in ln], [],
                f"{slug} should pass all six:\n{report}",
            )
        failed = [
            ln for ln in sections["submissions/legacy-inline"] if "❌" in ln
        ]
        self.assertEqual(len(failed), 1, report)
        self.assertIn("No inline scripts or event handlers", failed[0])


class Strippers(unittest.TestCase):
    """Unit-level cover for the comment strippers."""

    def test_js_line_and_block_comments(self):
        self.assertNotIn("secret", checker.strip_js_comments("// secret\nvar a=1;\n"))
        self.assertNotIn("secret", checker.strip_js_comments("/* secret */var a=1;\n"))

    def test_js_strings_are_preserved(self):
        for source in ('var a = "// keep";\n', "var a = '/* keep */';\n",
                       "var a = `// keep`;\n"):
            with self.subTest(source=source):
                self.assertIn("keep", checker.strip_js_comments(source))

    def test_unterminated_block_comment_does_not_crash(self):
        self.assertEqual(checker.strip_js_comments("var a=1; /* open").strip(), "var a=1;")

    def test_html_comment_form_only_applies_inside_script_elements(self):
        source = "<!-- x\nvar a=1;\n"
        self.assertIn("<!--", checker.strip_js_comments(source))
        self.assertNotIn("<!--", checker.strip_js_comments(source, html_comments=True))

    def test_css_strings_are_preserved(self):
        self.assertIn("keep", checker.strip_css_comments('a{content:"/* keep */"}'))
        self.assertNotIn("drop", checker.strip_css_comments("/* drop */a{color:red}"))

    def test_script_type_classification(self):
        self.assertTrue(checker.script_is_executable([]))
        self.assertTrue(checker.script_is_executable([("type", "module")]))
        self.assertTrue(checker.script_is_executable([("type", " Text/JavaScript ")]))
        self.assertFalse(checker.script_is_executable([("type", "application/ld+json")]))
        self.assertFalse(checker.script_is_executable([("type", "text/template")]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
