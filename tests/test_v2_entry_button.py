"""Task 8: 구버전 입장 버튼 한 번 누르기 (ui/v2_entry.py) — Streamlit 은 mock 으로 대신."""
import unittest
from unittest import mock

import ui.v2_entry as entry
import utils.v2_entry_token as et


class OneClickEntryTests(unittest.TestCase):
    def _run(self, user_id="alice", mode="LIVE", allowed=True, pressed=True):
        st = mock.MagicMock()
        st.button.return_value = pressed
        with mock.patch.object(entry, "st", st), \
                mock.patch.object(et, "is_allowed", return_value=allowed), \
                mock.patch.object(et, "read_secret", return_value=b"x" * 48), \
                mock.patch.object(et, "make_token", return_value="TOK123") as mk:
            entry.render_v2_entry(user_id, mode)
        return st, mk

    def test_label_has_mode_and_full_width(self):
        st, _ = self._run(pressed=False)
        st.button.assert_called_once()
        self.assertEqual(st.button.call_args.args[0], "신버전 대시보드 입장 (LIVE)")
        self.assertTrue(st.button.call_args.kwargs["use_container_width"])

    def test_no_press_makes_no_token_and_no_redirect(self):
        st, mk = self._run(pressed=False)
        mk.assert_not_called()
        st.markdown.assert_not_called()
        st.stop.assert_not_called()

    def test_press_redirects_with_token_then_stops(self):
        st, mk = self._run(pressed=True)
        mk.assert_called_once_with("alice", "LIVE")
        st.markdown.assert_called_once()
        html = st.markdown.call_args.args[0]
        self.assertIn('http-equiv="refresh"', html)
        self.assertIn("url=/v2/?t=TOK123", html)
        self.assertTrue(st.markdown.call_args.kwargs["unsafe_allow_html"])
        st.stop.assert_called_once()
        st.link_button.assert_not_called()

    def test_not_allowed_calls_no_button(self):
        st, mk = self._run(allowed=False)
        st.button.assert_not_called()
        mk.assert_not_called()


if __name__ == "__main__":
    unittest.main()
