"""Global hotkey listener with graceful macOS permission checking."""

from __future__ import annotations

import ctypes
import logging
import platform
import sys
import threading
from typing import Callable

logger = logging.getLogger(__name__)


def check_macos_accessibility_permission() -> bool:
    """Check if the current process has macOS Accessibility permissions."""
    if platform.system() != "Darwin":
        return True

    try:
        # Check ApplicationServices AXIsProcessTrusted
        app_services = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        ax_is_process_trusted = app_services.AXIsProcessTrusted
        ax_is_process_trusted.restype = ctypes.c_bool
        return bool(ax_is_process_trusted())
    except Exception as exc:
        logger.debug("Failed to check AXIsProcessTrusted: %s", exc)
        return True  # Fall back to letting pynput attempt binding


def check_macos_listen_event_permission() -> bool:
    """Check if the current process has macOS Input Monitoring/Listen Event permissions."""
    if platform.system() != "Darwin":
        return True

    try:
        core_graphics = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        if hasattr(core_graphics, "CGPreflightListenEventAccess"):
            cg_preflight = core_graphics.CGPreflightListenEventAccess
            cg_preflight.restype = ctypes.c_bool
            return bool(cg_preflight())
    except Exception as exc:
        logger.debug("Failed to check CGPreflightListenEventAccess: %s", exc)
    return True


class HotkeyListener:
    """Listens for a global hotkey across all applications on macOS."""

    def __init__(
        self,
        hotkey: str = "<ctrl>+<alt>+s",
        callback: Callable[[], None] | None = None,
    ) -> None:
        self.hotkey_combination = hotkey
        self.callback = callback
        self._paused = False
        self._running = False
        self._listener: Any = None
        self._lock = threading.Lock()

    @property
    def is_paused(self) -> bool:
        """Return whether hotkey triggering is currently paused."""
        return self._paused

    def pause(self) -> None:
        """Pause hotkey response without stopping the background listener."""
        with self._lock:
            self._paused = True
        logger.info("Hotkey listener paused.")

    def resume(self) -> None:
        """Resume hotkey response."""
        with self._lock:
            self._paused = False
        logger.info("Hotkey listener resumed.")

    def toggle_pause(self) -> bool:
        """Toggle paused state and return new paused state."""
        with self._lock:
            self._paused = not self._paused
            current_paused = self._paused
        logger.info("Hotkey listener is now %s.", "paused" if current_paused else "active")
        return current_paused

    def _on_hotkey_triggered(self) -> None:
        """Internal callback invoked when hotkey combination is pressed."""
        with self._lock:
            if self._paused:
                logger.debug("Hotkey pressed, but listener is paused; ignoring.")
                return

        logger.info("hotkey pressed")
        if self.callback is not None:
            try:
                self.callback()
            except Exception as exc:
                logger.error("Error executing hotkey callback: %s", exc, exc_info=True)

    def trigger_manually(self) -> None:
        """Manually trigger the hotkey action (e.g. from tray menu or test)."""
        logger.info("Manual scan triggered via tray/API.")
        self._on_hotkey_triggered()

    def start(self) -> bool:
        """Start listening for the global hotkey in a background thread.

        Handles missing macOS Accessibility / Input Monitoring permissions gracefully.
        """
        if self._running:
            return True

        # Preflight permission check on macOS
        has_ax = check_macos_accessibility_permission()
        has_input = check_macos_listen_event_permission()
        if not (has_ax and has_input):
            sys.stderr.write(
                "\n"
                "====================================================================\n"
                "[netPrep] NOTICE: macOS Accessibility or Input Monitoring\n"
                "permissions are not yet granted for this terminal/app.\n"
                "Global hotkeys may not detect keystrokes outside this window.\n"
                "To enable: Open System Settings -> Privacy & Security ->\n"
                "Accessibility (and Input Monitoring), then enable your terminal/Python.\n"
                "The app will continue running; you can also click 'Scan now' in the tray.\n"
                "====================================================================\n\n"
            )
            logger.warning(
                "Missing macOS Accessibility (ax=%s) or Input Monitoring (input=%s) permission.",
                has_ax,
                has_input,
            )

        try:
            from pynput import keyboard

            # Normalize hotkey format for pynput
            hotkey_str = self.hotkey_combination
            # Map <cmd> or <command> or <super>
            mapping = {hotkey_str: self._on_hotkey_triggered}
            self._listener = keyboard.GlobalHotKeys(mapping)
            self._listener.daemon = True
            self._listener.start()
            self._running = True
            logger.info("Global hotkey listener started for combination: %s", self.hotkey_combination)
            return True
        except ImportError:
            logger.warning("pynput is not installed. Global hotkey listener disabled.")
            return False
        except Exception as exc:
            logger.warning(
                "Failed to initialize global hotkey listener (%s). "
                "Ensure Accessibility permissions are granted in System Settings.",
                exc,
            )
            return False

    def stop(self) -> None:
        """Stop the background listener thread."""
        with self._lock:
            self._running = False
            if self._listener is not None:
                try:
                    self._listener.stop()
                except Exception as exc:
                    logger.debug("Error stopping listener: %s", exc)
                self._listener = None
        logger.info("Global hotkey listener stopped.")
