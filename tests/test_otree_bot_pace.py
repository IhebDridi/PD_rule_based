"""Unit tests for bot pacing helpers (no oTree import required)."""

from __future__ import annotations

import unittest

from shared.otree_bot_pace import _rewrite_auto_submit_js, bot_submit_delay_ms


class BotPaceTests(unittest.TestCase):
    def test_rewrite_injects_settimeout(self):
        body = (
            b"<html><body>"
            b"<script>\n"
            b"var form = document.querySelector('#form');\n"
            b"    form.submit();\n"
            b"    // browser-bot-auto-submit\n"
            b"</script></body></html>"
        )
        out = _rewrite_auto_submit_js(body, 1500)
        self.assertIsNotNone(out)
        self.assertIn(b"setTimeout(function () { form.submit(); }, 1500);", out)
        self.assertNotIn(b"form.submit();\n    // browser-bot-auto-submit", out)

    def test_rewrite_noop_without_marker(self):
        body = b"var form = document.querySelector('#form');\n    form.submit();"
        self.assertIsNone(_rewrite_auto_submit_js(body, 1500))

    def test_delay_zero_disables(self):
        class _S:
            config = {"bot_submit_delay_ms": 0, "bot_submit_jitter_ms": 1000}

        self.assertEqual(bot_submit_delay_ms(_S(), None), 0)

    def test_delay_stable_jitter_by_participant(self):
        class _S:
            config = {"bot_submit_delay_ms": 1000, "bot_submit_jitter_ms": 500}

        class _P:
            id_in_session = 3

        a = bot_submit_delay_ms(_S(), _P())
        b = bot_submit_delay_ms(_S(), _P())
        self.assertEqual(a, b)
        self.assertGreaterEqual(a, 1000)
        self.assertLessEqual(a, 1500)


if __name__ == "__main__":
    unittest.main()
