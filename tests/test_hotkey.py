"""Unit tests for hotkey listener and pause/resume logic."""

import unittest

from netprep.hotkey import (
    HotkeyListener,
    check_macos_accessibility_permission,
    check_macos_listen_event_permission,
)


class TestHotkey(unittest.TestCase):
    def test_permission_checks_do_not_crash(self) -> None:
        ax = check_macos_accessibility_permission()
        self.assertIsInstance(ax, bool)
        inp = check_macos_listen_event_permission()
        self.assertIsInstance(inp, bool)

    def test_hotkey_listener_pause_and_resume(self) -> None:
        called = False

        def callback() -> None:
            nonlocal called
            called = True

        listener = HotkeyListener(hotkey="<ctrl>+<alt>+s", callback=callback)
        self.assertFalse(listener.is_paused)

        # Trigger while active
        listener.trigger_manually()
        self.assertTrue(called)

        # Pause
        called = False
        listener.pause()
        self.assertTrue(listener.is_paused)
        listener.trigger_manually()
        self.assertFalse(called)

        # Resume
        listener.resume()
        self.assertFalse(listener.is_paused)
        listener.trigger_manually()
        self.assertTrue(called)

    def test_hotkey_toggle_pause(self) -> None:
        listener = HotkeyListener(hotkey="<ctrl>+<alt>+s")
        self.assertFalse(listener.is_paused)
        new_state = listener.toggle_pause()
        self.assertTrue(new_state)
        self.assertTrue(listener.is_paused)
        new_state = listener.toggle_pause()
        self.assertFalse(new_state)
        self.assertFalse(listener.is_paused)


if __name__ == "__main__":
    unittest.main()
