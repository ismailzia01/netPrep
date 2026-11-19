"""Menu-bar tray icon and popup menu for netPrep."""

from __future__ import annotations

import logging
import sys
from typing import Callable

from netprep.config import AppConfig
from netprep.subjects import SubjectPack, list_subject_packs

logger = logging.getLogger(__name__)

try:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QMenu, QSystemTrayIcon

    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False


if HAS_PYSIDE6:

    def create_default_tray_icon() -> QIcon:
        """Create a programmatic menu-bar icon (32x32 template) for macOS."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded badge background
        painter.setBrush(QColor(41, 128, 185))
        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

        # Draw letter 'N'
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Helvetica", 28, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), 0x0084, "N")  # Qt.AlignmentFlag.AlignCenter

        painter.end()
        icon = QIcon(pixmap)
        icon.setIsMask(False)
        return icon

    class NetPrepTray(QSystemTrayIcon):
        """macOS menu-bar tray item with actions and subject switching submenu."""

        def __init__(
            self,
            config: AppConfig,
            on_scan: Callable[[], None] | None = None,
            on_subject_changed: Callable[[str], None] | None = None,
            on_pause_toggled: Callable[[bool], None] | None = None,
            on_quit: Callable[[], None] | None = None,
            parent: QObject | None = None,
        ) -> None:
            super().__init__(create_default_tray_icon(), parent)
            self.config = config
            self.on_scan = on_scan
            self.on_subject_changed = on_subject_changed
            self.on_pause_toggled = on_pause_toggled
            self.on_quit = on_quit

            self.setToolTip("netPrep")
            self.menu = QMenu()
            self.subject_menu = QMenu("Subject", self.menu)
            self.subject_action_group = QActionGroup(self)
            self.subject_action_group.setExclusive(True)

            self.pause_action: QAction | None = None
            self._build_menu()
            self.setContextMenu(self.menu)

        def _build_menu(self) -> None:
            """Construct the tray menu items."""
            self.menu.clear()

            # 1. Scan now
            scan_action = QAction("Scan now", self.menu)
            scan_action.triggered.connect(self._handle_scan)
            self.menu.addAction(scan_action)

            # 2. Pause / Resume hotkey
            self.pause_action = QAction("Pause hotkey", self.menu)
            self.pause_action.setCheckable(True)
            self.pause_action.setChecked(False)
            self.pause_action.toggled.connect(self._handle_pause_toggle)
            self.menu.addAction(self.pause_action)

            self.menu.addSeparator()

            # 3. Subject submenu
            self._populate_subject_menu()
            self.menu.addMenu(self.subject_menu)

            self.menu.addSeparator()

            # 4. Quit
            quit_action = QAction("Quit", self.menu)
            quit_action.triggered.connect(self._handle_quit)
            self.menu.addAction(quit_action)

        def _populate_subject_menu(self) -> None:
            """Populate the Subject submenu with available subject packs."""
            self.subject_menu.clear()
            for act in self.subject_action_group.actions():
                self.subject_action_group.removeAction(act)

            packs = list_subject_packs(self.config.subjects_dir)
            if not packs:
                disabled_action = QAction("(No subjects found)", self.subject_menu)
                disabled_action.setEnabled(False)
                self.subject_menu.addAction(disabled_action)
                return

            for pack in packs:
                action = QAction(pack.name, self.subject_menu)
                action.setCheckable(True)
                action.setData(pack.id)
                if pack.id == self.config.active_subject or pack.name == self.config.active_subject:
                    action.setChecked(True)

                action.triggered.connect(lambda checked, p=pack: self._handle_select_subject(p))
                self.subject_action_group.addAction(action)
                self.subject_menu.addAction(action)

        def _handle_scan(self) -> None:
            logger.info("Tray: 'Scan now' clicked.")
            if self.on_scan:
                self.on_scan()

        def _handle_pause_toggle(self, is_paused: bool) -> None:
            if self.pause_action:
                self.pause_action.setText("Resume hotkey" if is_paused else "Pause hotkey")
            logger.info("Tray: Hotkey pause state toggled to %s.", is_paused)
            if self.on_pause_toggled:
                self.on_pause_toggled(is_paused)

        def _handle_select_subject(self, pack: SubjectPack) -> None:
            self.config.active_subject = pack.id
            logger.info("Tray: Switched active subject to '%s' (%s).", pack.name, pack.id)
            if self.on_subject_changed:
                self.on_subject_changed(pack.id)

        def _handle_quit(self) -> None:
            logger.info("Tray: 'Quit' clicked.")
            if self.on_quit:
                self.on_quit()

        def update_pause_state(self, is_paused: bool) -> None:
            if self.pause_action and self.pause_action.isChecked() != is_paused:
                self.pause_action.blockSignals(True)
                self.pause_action.setChecked(is_paused)
                self.pause_action.setText("Resume hotkey" if is_paused else "Pause hotkey")
                self.pause_action.blockSignals(False)

else:

    class NetPrepTray:  # type: ignore[no-redef]
        """Console fallback tray controller when PySide6 is not yet installed."""

        def __init__(
            self,
            config: AppConfig,
            on_scan: Callable[[], None] | None = None,
            on_subject_changed: Callable[[str], None] | None = None,
            on_pause_toggled: Callable[[bool], None] | None = None,
            on_quit: Callable[[], None] | None = None,
            parent: Any = None,
        ) -> None:
            self.config = config
            self.on_scan = on_scan
            self.on_subject_changed = on_subject_changed
            self.on_pause_toggled = on_pause_toggled
            self.on_quit = on_quit
            self._is_paused = False
            self._is_visible = False

        def show(self) -> None:
            self._is_visible = True
            packs = list_subject_packs(self.config.subjects_dir)
            pack_names = [f"[*] {p.name}" if p.id == self.config.active_subject else f"[ ] {p.name}" for p in packs]
            print("\n" + "=" * 55)
            print(" [netPrep Menu-Bar Tray Initialized]")
            print(" Menu Actions:")
            print("   1. Scan now")
            print(f"   2. {'Resume' if self._is_paused else 'Pause'} hotkey")
            print(f"   3. Subject Submenu: {', '.join(pack_names) if pack_names else '(none)'}")
            print("   4. Quit")
            print("=" * 55 + "\n")

        def hide(self) -> None:
            self._is_visible = False

        def _handle_scan(self) -> None:
            logger.info("Tray: 'Scan now' triggered.")
            if self.on_scan:
                self.on_scan()

        def _handle_pause_toggle(self, is_paused: bool) -> None:
            self._is_paused = is_paused
            logger.info("Tray: Hotkey pause state toggled to %s.", is_paused)
            if self.on_pause_toggled:
                self.on_pause_toggled(is_paused)

        def _handle_select_subject(self, pack_id: str) -> None:
            self.config.active_subject = pack_id
            logger.info("Tray: Switched active subject to '%s'.", pack_id)
            if self.on_subject_changed:
                self.on_subject_changed(pack_id)

        def _handle_quit(self) -> None:
            logger.info("Tray: 'Quit' triggered.")
            if self.on_quit:
                self.on_quit()

        def update_pause_state(self, is_paused: bool) -> None:
            self._is_paused = is_paused
