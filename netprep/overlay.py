"""PySide6 OverlayRenderer implementation for netPrep.

Renders an on-screen visual answer indicator and error message overlay.

DESIGN RULE (NON-NEGOTIABLE):
The overlay is a normal, visible macOS window. Under no circumstances will
netPrep implement or accept features intended to hide, disguise, or obscure
the overlay window from screen capture, screen recording, proctoring tools,
or window lists.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from netprep.capture import pixel_box_to_screen_box
from netprep.config import AppConfig, load_config
from netprep.scan_pipeline import BoundingBox, OverlayRenderer, ParsedQuestion

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

try:
    from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
    from PySide6.QtWidgets import QApplication, QWidget

    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False


if HAS_PYSIDE6:

    class OverlayWindow(QWidget):
        """Frameless, transparent, click-through, always-on-top overlay window.

        DESIGN RULE: This is a standard visible window with transparent background.
        It does not hide from screen capture or proctoring software.
        """

        def __init__(self, config: AppConfig | None = None) -> None:
            super().__init__(None)
            self.config = config or load_config()

            # Window configuration:
            # - FramelessWindowHint: no title bar
            # - WindowStaysOnTopHint: always on top
            # - WindowDoesNotAcceptFocus: never steals keyboard focus
            # - SubWindow: does not activate app on macOS
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
                | Qt.WindowType.SubWindow
            )

            # Attributes:
            # - WA_TranslucentBackground: transparent canvas
            # - WA_TransparentForMouseEvents: clicks pass directly through to apps below
            # - WA_ShowWithoutActivating: show() does not activate the app window
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

            self._mode: str | None = None  # "answer" or "message"
            self._answer_letter: str = ""
            self._highlight_rect: QRect | None = None
            self._badge_rect: QRect | None = None
            self._message_text: str = ""
            self._message_rect: QRect | None = None
            self._is_fallback_badge: bool = False

            # Auto-dismiss timer
            self._dismiss_timer = QTimer(self)
            self._dismiss_timer.setSingleShot(True)
            self._dismiss_timer.timeout.connect(self.hide_overlay)

            self._sync_geometry_with_screen()

        def _sync_geometry_with_screen(self) -> None:
            """Cover the primary screen area."""
            primary = QGuiApplication.primaryScreen()
            if primary:
                self.setGeometry(primary.geometry())
            else:
                self.setGeometry(0, 0, 1920, 1080)

        def show_answer_marker(
            self,
            answer_letter: str,
            box_screen: BoundingBox | None,
            duration: float | None = None,
        ) -> None:
            """Display the highlight box and answer badge on screen."""
            self._sync_geometry_with_screen()
            self._mode = "answer"
            self._answer_letter = answer_letter.upper()
            self._message_text = ""
            self._message_rect = None

            screen_rect = self.rect()
            badge_size = 32

            if (
                box_screen is not None
                and box_screen.width > 0
                and box_screen.height > 0
                and screen_rect.contains(box_screen.x, box_screen.y)
            ):
                self._is_fallback_badge = False
                self._highlight_rect = QRect(
                    box_screen.x,
                    box_screen.y,
                    box_screen.width,
                    box_screen.height,
                )

                # Position badge immediately to the left of the option box
                badge_x = self._highlight_rect.left() - badge_size - 8
                badge_y = self._highlight_rect.top() + (self._highlight_rect.height() - badge_size) // 2

                # If too close to screen left edge, position inside top-left
                if badge_x < screen_rect.left() + 8:
                    badge_x = self._highlight_rect.left() + 4
                    badge_y = max(screen_rect.top() + 8, self._highlight_rect.top() - badge_size - 4)

                self._badge_rect = QRect(badge_x, badge_y, badge_size, badge_size)
            else:
                # Fallback badge centered near top of screen
                self._is_fallback_badge = True
                self._highlight_rect = None
                fallback_w = 260
                fallback_h = 44
                fallback_x = (screen_rect.width() - fallback_w) // 2
                fallback_y = 60
                self._badge_rect = QRect(fallback_x, fallback_y, fallback_w, fallback_h)

            self.show()
            self.update()

            display_duration = duration if duration is not None else self.config.overlay_duration
            if display_duration > 0:
                self._dismiss_timer.start(int(display_duration * 1000))

        def show_toast_message(self, message: str, duration: float | None = None) -> None:
            """Display a floating message/error toast banner near top of screen."""
            self._sync_geometry_with_screen()
            self._mode = "message"
            self._message_text = message
            self._answer_letter = ""
            self._highlight_rect = None
            self._badge_rect = None

            screen_rect = self.rect()
            toast_w = max(380, min(800, len(message) * 9 + 48))
            toast_h = 44
            toast_x = (screen_rect.width() - toast_w) // 2
            toast_y = 60
            self._message_rect = QRect(toast_x, toast_y, toast_w, toast_h)

            self.show()
            self.update()

            display_duration = duration if duration is not None else self.config.overlay_duration
            if display_duration > 0:
                self._dismiss_timer.start(int(display_duration * 1000))

        def hide_overlay(self) -> None:
            """Dismiss and clear the overlay."""
            self._dismiss_timer.stop()
            self._mode = None
            self._highlight_rect = None
            self._badge_rect = None
            self._message_rect = None
            self.hide()
            self.update()

        def paintEvent(self, event: Any) -> None:
            """Paint highlight boxes, badges, or error banners with high contrast."""
            if not self._mode:
                return

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            if self._mode == "answer":
                self._paint_answer(painter)
            elif self._mode == "message":
                self._paint_message(painter)

            painter.end()

        def _paint_answer(self, painter: QPainter) -> None:
            """Paint option highlight box and badge."""
            hl_color = QColor(self.config.overlay_highlight_color)
            badge_color = QColor(self.config.overlay_badge_color)

            # 1. Option highlight box
            if self._highlight_rect:
                pad_rect = self._highlight_rect.adjusted(-6, -3, 6, 3)

                # Outer dark contrast outline (ensures visibility on bright white backgrounds)
                dark_pen = QPen(QColor(0, 0, 0, 140), 4)
                painter.setPen(dark_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(pad_rect, 6, 6)

                # Main colored stroke and semi-transparent fill
                stroke_pen = QPen(hl_color, 2.5)
                painter.setPen(stroke_pen)
                fill_color = QColor(hl_color.red(), hl_color.green(), hl_color.blue(), 35)
                painter.setBrush(fill_color)
                painter.drawRoundedRect(pad_rect, 6, 6)

            # 2. Answer badge
            if self._badge_rect:
                if self._is_fallback_badge:
                    # Draw fallback pill: [ Suggested Answer: B ]
                    painter.setPen(QPen(QColor(0, 0, 0, 160), 3))
                    painter.setBrush(QColor(15, 23, 42, 230))  # dark slate
                    painter.drawRoundedRect(self._badge_rect, 10, 10)

                    painter.setPen(QPen(badge_color, 2))
                    painter.drawRoundedRect(self._badge_rect, 10, 10)

                    painter.setPen(QColor(255, 255, 255))
                    font = QFont("Helvetica", 14, QFont.Weight.Bold)
                    painter.setFont(font)
                    text = f"Suggested Answer: [{self._answer_letter}]"
                    painter.drawText(self._badge_rect, Qt.AlignmentFlag.AlignCenter, text)
                else:
                    # Draw standard circular/square badge next to option
                    painter.setPen(QPen(QColor(0, 0, 0, 160), 3))
                    painter.setBrush(badge_color)
                    painter.drawRoundedRect(self._badge_rect, 8, 8)

                    painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
                    painter.drawRoundedRect(self._badge_rect, 8, 8)

                    painter.setPen(QColor(255, 255, 255))
                    font = QFont("Helvetica", 16, QFont.Weight.Bold)
                    painter.setFont(font)
                    painter.drawText(self._badge_rect, Qt.AlignmentFlag.AlignCenter, self._answer_letter)

        def _paint_message(self, painter: QPainter) -> None:
            """Paint floating toast message banner."""
            if not self._message_rect:
                return

            # Dark slate pill background with dark border
            painter.setPen(QPen(QColor(0, 0, 0, 180), 3))
            painter.setBrush(QColor(15, 23, 42, 230))
            painter.drawRoundedRect(self._message_rect, 10, 10)

            # Amber/gold accent border
            accent = QColor(245, 158, 11)
            painter.setPen(QPen(accent, 2))
            painter.drawRoundedRect(self._message_rect, 10, 10)

            # Text
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Helvetica", 13, QFont.Weight.DemiBold)
            painter.setFont(font)
            text = f"[netPrep] {self._message_text}"
            painter.drawText(self._message_rect, Qt.AlignmentFlag.AlignCenter, text)

    class _OverlayDispatcher(QObject):
        """Internal Qt signal dispatcher avoiding ABC/QObject multiple inheritance metaclass conflicts."""

        sig_show_answer = Signal(str, object, float, object, bool)
        sig_show_message = Signal(str, float)
        sig_hide = Signal()

    class PySide6OverlayRenderer(OverlayRenderer):
        """Thread-safe OverlayRenderer implementation orchestrating OverlayWindow."""

        def __init__(self, config: AppConfig | None = None) -> None:
            super().__init__()
            self.config = config or load_config()
            self._window: OverlayWindow | None = None

            # Connect dispatcher signals to UI slots
            self._dispatcher = _OverlayDispatcher()
            self._dispatcher.sig_show_answer.connect(self._handle_show_answer)
            self._dispatcher.sig_show_message.connect(self._handle_show_message)
            self._dispatcher.sig_hide.connect(self._handle_hide)

        def _ensure_window(self) -> OverlayWindow:
            """Ensure OverlayWindow is created on UI thread."""
            if self._window is None:
                self._window = OverlayWindow(self.config)
            return self._window

        @property
        def is_visible(self) -> bool:
            """Check if overlay window is currently visible."""
            return self._window is not None and self._window.isVisible()

        def show_answer(
            self,
            answer_letter: str,
            question: ParsedQuestion,
            scale_factor: float = 1.0,
            origin_points: tuple[float, float] = (0.0, 0.0),
            is_pixels: bool = False,
        ) -> None:
            """Show the answer overlay, safe to invoke from any thread."""
            self._dispatcher.sig_show_answer.emit(
                answer_letter, question, scale_factor, origin_points, is_pixels
            )

        def show_message(self, message: str, duration: float | None = None) -> None:
            """Show a temporary floating message/error banner, safe to invoke from any thread."""
            dur = duration if duration is not None else self.config.overlay_duration
            self._dispatcher.sig_show_message.emit(message, dur)

        def hide(self) -> None:
            """Dismiss overlay immediately, safe to invoke from any thread."""
            self._dispatcher.sig_hide.emit()

        def clear(self) -> None:
            """Alias for hide()."""
            self.hide()

        # --- Internal UI thread slots ---

        def _handle_show_answer(
            self,
            answer_letter: str,
            question: ParsedQuestion,
            scale_factor: float,
            origin_points: tuple[float, float],
            is_pixels: bool,
        ) -> None:
            window = self._ensure_window()
            chosen_box = question.option_boxes.get(answer_letter.upper())

            box_screen: BoundingBox | None = None
            if chosen_box:
                if is_pixels:
                    box_screen = pixel_box_to_screen_box(
                        box=chosen_box,
                        scale_factor=scale_factor,
                        origin_points=origin_points,
                    )
                else:
                    box_screen = chosen_box

            window.show_answer_marker(answer_letter, box_screen)

        def _handle_show_message(self, message: str, duration: float) -> None:
            window = self._ensure_window()
            window.show_toast_message(message, duration)

        def _handle_hide(self) -> None:
            if self._window is not None:
                self._window.hide_overlay()

else:

    class PySide6OverlayRenderer(OverlayRenderer):  # type: ignore[no-redef]
        """Fallback stub overlay renderer when PySide6 is unavailable."""

        def __init__(self, config: AppConfig | None = None) -> None:
            self.config = config or load_config()
            self._visible = False
            self.last_answer: str | None = None
            self.last_message: str | None = None

        @property
        def is_visible(self) -> bool:
            return self._visible

        def show_answer(
            self,
            answer_letter: str,
            question: ParsedQuestion,
            scale_factor: float = 1.0,
            origin_points: tuple[float, float] = (0.0, 0.0),
            is_pixels: bool = False,
        ) -> None:
            self._visible = True
            self.last_answer = answer_letter
            logger.info("Console Overlay: Answer [%s]", answer_letter)

        def show_message(self, message: str, duration: float | None = None) -> None:
            self._visible = True
            self.last_message = message
            logger.info("Console Overlay: Message '%s'", message)

        def hide(self) -> None:
            self._visible = False

        def clear(self) -> None:
            self.hide()
