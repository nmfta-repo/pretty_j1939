#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

from __future__ import annotations
import argparse
import curses
import json
import logging
import time
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Generator, TYPE_CHECKING

try:
    import can
    from can.cli import create_bus_from_namespace
except ImportError:
    can = None
    create_bus_from_namespace = None

if TYPE_CHECKING:
    import can

from .describe import get_describer
from .render import HighPerformanceRenderer, NUM_IN_PARENS_RE

logger = logging.getLogger("pretty_j1939.viewer")

# --- Constants ---
PRETTY_COL_OFFSET = 50
WRAP_INDENT = 4
BOUNCE_BUFFER_WIDTH = 15
REFRESH_RATE_MS = 0.001

# --- Utility Functions ---


def hex_to_curses_basic(hex_str: str) -> int:
    """Maps a hex color string to one of the 8 basic curses colors."""
    if hex_str == "default":
        return -1

    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        return curses.COLOR_WHITE

    try:
        r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
    except ValueError:
        return curses.COLOR_WHITE

    colors = [
        (0, 0, 0, curses.COLOR_BLACK),
        (255, 0, 0, curses.COLOR_RED),
        (0, 255, 0, curses.COLOR_GREEN),
        (255, 255, 0, curses.COLOR_YELLOW),
        (0, 0, 255, curses.COLOR_BLUE),
        (255, 0, 255, curses.COLOR_MAGENTA),
        (0, 255, 255, curses.COLOR_CYAN),
        (255, 255, 255, curses.COLOR_WHITE),
    ]

    return min(
        colors, key=lambda c: (r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2
    )[3]


# --- Data Structures ---


@dataclass
class MessageState:
    """Holds the current state and history for a specific CAN ID."""

    msg: can.Message
    count: int = 0
    last_time: float = 0.0
    dt: float = 0.0
    description: OrderedDict = field(default_factory=OrderedDict)
    previous_description: OrderedDict = field(default_factory=OrderedDict)
    previous_data_hex: str = ""
    num_rows: int = 1


class UIState:
    """Manages the UI interaction state (scrolling, selection, logging)."""

    def __init__(self):
        self.scroll: int = 0
        self.paused: bool = False
        self.highlight_changes: bool = False
        self.selection_cursor: Optional[int] = None
        self.marked_ids: Set[int] = set()
        self.active_logging_ids: Set[int] = set()
        self.log_file_handle = None
        self.log_filename: str = ""


# --- Main Viewer Class ---


class J1939Viewer:
    def __init__(
        self, stdscr, bus: can.Bus, describer, theme_name: Optional[str] = None
    ):
        self.stdscr = stdscr
        self.bus = bus
        self.describer = describer
        self.ui = UIState()

        # Theme and Colors
        renderer = HighPerformanceRenderer(theme_dict=theme_name, color_system=None)
        self.theme = renderer.theme_dict
        self._init_curses()

        # Data
        self.messages: Dict[int, MessageState] = {}
        self.id_order: List[int] = []
        self.screen_h, self.screen_w = self.stdscr.getmaxyx()

        self.run()

    def _init_curses(self):
        """Sets up curses modes and color pairs."""
        self.stdscr.nodelay(True)
        curses.curs_set(0)
        curses.use_default_colors()

        def get_theme_color(key, default):
            return hex_to_curses_basic(self.theme.get(key, default))

        # Determine the color for 'disabled_bytes' to avoid collisions with printable data
        disabled_color = get_theme_color("disabled_bytes", "#555753")

        def get_safe_color(key, default):
            c = get_theme_color(key, default)
            # Ensure theme colors don't match disabled_bytes due to curses palette limits.
            # If they do, use -1 (default) to ensure visibility/distinction.
            if key != "disabled_bytes" and c != -1 and c == disabled_color:
                return -1
            return c

        curses.init_pair(1, get_safe_color("keys", "#00ffff"), -1)  # Keys
        curses.init_pair(2, get_safe_color("numbers", "#ffff00"), -1)  # Numbers
        curses.init_pair(3, get_safe_color("strings", "#ffffff"), -1)  # Default/Values

        # Byte specific colors
        curses.init_pair(10, get_safe_color("zero_bytes", "#babdb6"), -1)
        curses.init_pair(11, disabled_color, -1)
        curses.init_pair(12, get_safe_color("ascii_bytes", "#75507b"), -1)
        curses.init_pair(13, get_safe_color("normal_bytes", "default"), -1)

        h_color = get_theme_color("highlight", "#ffffff")
        curses.init_pair(
            5,
            curses.COLOR_BLACK,
            h_color if h_color != curses.COLOR_BLACK else curses.COLOR_CYAN,
        )
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Cursor
        curses.init_pair(7, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Marked for log

    # --- Layout Logic ---

    def _format_value(self, key: str, val: Any) -> str:
        """Applies fixed-width limits to floating point numbers ONLY, preserving units."""
        s = str(val)
        if key in ("Bytes", "Transport Data"):
            return s

        # Detect floating point with optional units: e.g. "12.5 [deg]"
        t = s.strip()
        if t and "." in t:
            # Split into numeric part and everything else (like units)
            # Find first space or bracket to isolate the number
            split_idx = -1
            for i, char in enumerate(t):
                if char in (" ", "["):
                    split_idx = i
                    break

            num_part = t[:split_idx] if split_idx != -1 else t
            rest_part = t[split_idx:] if split_idx != -1 else ""

            # Verify num_part is actually numeric
            if num_part.replace(".", "", 1).isdigit() or (
                num_part.startswith(("-", "+"))
                and num_part[1:].replace(".", "", 1).isdigit()
            ):
                # Pad/truncate ONLY the numeric part to prevent jitter
                formatted_num = (
                    f"{num_part[:BOUNCE_BUFFER_WIDTH]:<{BOUNCE_BUFFER_WIDTH}}"
                )
                return f"{formatted_num}{rest_part}"

        return s

    def _iterate_pretty_fields(
        self, state: MessageState
    ) -> Generator[Tuple[str, str, bool, bool, bool], None, None]:
        """Engine for field layout. Yields (key, value, is_changed, is_bytes, is_first_on_line)."""
        is_first = True
        for k, v in state.description.items():
            if k.startswith("_") or k == "Bytes":
                continue

            val_str = self._format_value(k, v)
            is_changed = (
                self.ui.highlight_changes
                and k in state.previous_description
                and state.previous_description[k] != v
            )

            yield k, val_str, is_changed, (k == "Transport Data"), is_first
            is_first = False

    def _calculate_required_rows(self, state: MessageState) -> int:
        """Calculates how many screen rows a message's 'Pretty' output requires."""
        curr_x, num_rows = PRETTY_COL_OFFSET, 1
        max_x = self.screen_w - 1

        for k, v_str, _, _, is_first in self._iterate_pretty_fields(state):
            kv_len = len(str(k)) + len(v_str) + 2  # "key: value"
            sep_len = 0 if is_first else 2  # ", "

            if not is_first and curr_x + sep_len + kv_len > max_x:
                num_rows += 1
                curr_x = PRETTY_COL_OFFSET + WRAP_INDENT + kv_len
            else:
                curr_x += sep_len + kv_len
        return num_rows

    # --- Rendering ---

    def _draw_header(self):
        """Draws the sticky top header."""
        self.stdscr.erase()
        text = f"{'Count':<8}{'dt':<8}{'ID':<12}{'Bytes':<22}Pretty"
        if self.ui.highlight_changes:
            text += " (h)"
        if self.ui.active_logging_ids:
            text += (
                f" REC ({len(self.ui.active_logging_ids)} IDs): {self.ui.log_filename}"
            )
        elif self.ui.selection_cursor is not None:
            text += f" [SELECT: {len(self.ui.marked_ids)} marked]"

        self.stdscr.addstr(0, 0, text[: self.screen_w], curses.A_BOLD)

    def _draw_message_row(self, key: int, start_row: int):
        """Draws a single ID's data across one or more rows."""
        state = self.messages[key]
        screen_row = start_row - self.ui.scroll

        # Bounds check
        if screen_row + state.num_rows - 1 < 1 or screen_row >= self.screen_h:
            return

        # UI context
        is_hover = (
            self.ui.selection_cursor is not None
            and self.id_order[self.ui.selection_cursor] == key
        )
        is_marked = key in self.ui.marked_ids
        is_logging = key in self.ui.active_logging_ids

        attr_base = (
            curses.color_pair(6)
            if is_hover
            else (curses.color_pair(7) if is_marked else curses.A_NORMAL)
        )
        if is_logging:
            attr_base |= curses.A_BOLD

        # 1. Clear rows and draw selection highlight
        for i in range(state.num_rows):
            r = screen_row + i
            if 1 <= r < self.screen_h:
                self.stdscr.move(r, 0)
                self.stdscr.clrtoeol()
                if is_hover or is_marked:
                    self.stdscr.chgat(r, 0, -1, attr_base)

        # 2. Draw standard columns (Count, dt, ID)
        if 1 <= screen_row < self.screen_h:
            marker = ">" if is_marked else ("*" if is_logging else " ")
            id_hex = (
                f"0x{state.msg.arbitration_id:08X}"
                if state.msg.is_extended_id
                else f"0x{state.msg.arbitration_id:03X}"
            )

            self.stdscr.addstr(screen_row, 0, f"{state.count:<8}", attr_base)
            self.stdscr.addstr(screen_row, 8, f"{round(state.dt, 2):<8.3f}", attr_base)
            self.stdscr.addstr(screen_row, 16, f"{marker}{id_hex:<11}", attr_base)

            # 2.1 Draw Bytes column
            curr_x = 28
            data_hex = state.msg.data.hex().upper()

            # Use same coloring logic as HighPerformanceRenderer
            def get_byte_attr(byte_str, is_diff):
                if is_hover or is_marked:
                    return attr_base
                if is_diff and self.ui.highlight_changes:
                    return curses.color_pair(5)

                if byte_str == "00":
                    return curses.color_pair(10)
                if byte_str == "FF":
                    return curses.color_pair(11)

                try:
                    b_int = int(byte_str, 16)
                    if 32 <= b_int <= 126:
                        return curses.color_pair(12)
                except ValueError as e:
                    logger.debug(f"Byte {byte_str} is not valid hex: {e}")
                return curses.color_pair(13)

            prev_data_hex = ""
            if self.ui.highlight_changes:
                # msg in MessageState is the CURRENT message.
                # To highlight changes we need the data from the message that produced state.previous_description.
                # Actually MessageState holds the current message, and we update it in _process_message.
                # So we need to store the previous data hex.
                prev_data_hex = getattr(state, "previous_data_hex", "")

            for i in range(0, min(len(data_hex), 16), 2):
                byte_str = data_hex[i : i + 2]
                is_diff = False
                if prev_data_hex and i < len(prev_data_hex):
                    is_diff = byte_str != prev_data_hex[i : i + 2]

                attr = get_byte_attr(byte_str, is_diff)
                self.stdscr.addstr(screen_row, curr_x, byte_str, attr)
                curr_x += 2

            if len(data_hex) > 16:
                self.stdscr.addstr(screen_row, curr_x, "..", attr_base)

        # 3. Draw Pretty column with wrapping
        curr_x, curr_y = PRETTY_COL_OFFSET, screen_row
        prev_desc = state.previous_description

        for k, v_str, is_changed, is_bytes, is_first in self._iterate_pretty_fields(
            state
        ):
            kv_len = len(str(k)) + len(v_str) + 2
            sep_len = 0 if is_first else 2

            if not is_first and curr_x + sep_len + kv_len > self.screen_w - 1:
                curr_y += 1
                curr_x = PRETTY_COL_OFFSET + WRAP_INDENT
                sep_len, is_first = 0, True

            if curr_y >= self.screen_h:
                break
            if curr_y < 1:
                curr_x += sep_len + kv_len
                continue

            # Draw separator
            if sep_len:
                self.stdscr.addstr(
                    curr_y,
                    curr_x,
                    ", ",
                    attr_base if (is_hover or is_marked) else curses.color_pair(3),
                )
                curr_x += 2

            # Draw Key
            self.stdscr.addstr(
                curr_y,
                curr_x,
                f"{k}: ",
                attr_base if (is_hover or is_marked) else curses.color_pair(1),
            )
            curr_x += len(k) + 2

            # Draw Value
            if is_bytes and k in prev_desc and len(v_str) == len(str(prev_desc[k])):
                # Special granular byte highlight
                prev_v_str = str(prev_desc[k])
                for i in range(0, len(v_str), 2):
                    pair, p_pair = v_str[i : i + 2], prev_v_str[i : i + 2]
                    attr = (
                        attr_base
                        if (is_hover or is_marked)
                        else (
                            curses.color_pair(5)
                            if (self.ui.highlight_changes and pair != p_pair)
                            else curses.color_pair(3)
                        )
                    )
                    if curr_x + 2 < self.screen_w:
                        self.stdscr.addstr(curr_y, curr_x, pair, attr)
                        curr_x += 2
            else:
                # Determine color for this value
                val_attr = (
                    attr_base
                    if (is_hover or is_marked)
                    else (curses.color_pair(5) if is_changed else curses.color_pair(3))
                )

                # Apply numeric colorization if using default color and parens are present
                if not (is_hover or is_marked or is_changed) and "(" in v_str:
                    last_end = 0
                    for match in NUM_IN_PARENS_RE.finditer(v_str):
                        # Text before number (including '(')
                        pre = v_str[last_end : match.start(2)]
                        room = self.screen_w - 1 - curr_x
                        if room <= 0:
                            break
                        self.stdscr.addstr(curr_y, curr_x, pre[:room], val_attr)
                        curr_x += len(pre[:room])

                        # Number itself
                        num_part = match.group(2)
                        room = self.screen_w - 1 - curr_x
                        if room <= 0:
                            break
                        self.stdscr.addstr(
                            curr_y, curr_x, num_part[:room], curses.color_pair(2)
                        )
                        curr_x += len(num_part[:room])

                        last_end = match.end(2)

                    # Remaining text
                    post = v_str[last_end:]
                    room = self.screen_w - 1 - curr_x
                    if room > 0:
                        self.stdscr.addstr(curr_y, curr_x, post[:room], val_attr)
                        curr_x += len(post[:room])
                else:
                    room = self.screen_w - 1 - curr_x
                    if room > 0:
                        self.stdscr.addstr(curr_y, curr_x, v_str[:room], val_attr)
                        curr_x += len(v_str[:room])

    def _redraw_all(self):
        """Full screen refresh."""
        self._draw_header()
        curr_row = 1
        for key in self.id_order:
            self._draw_message_row(key, curr_row)
            curr_row += self.messages[key].num_rows

    # --- Interaction ---

    def _get_user_input(self, prompt: str) -> Optional[str]:
        """Displays a prompt at the bottom and returns user text input."""
        curses.echo()
        curses.curs_set(1)
        self.stdscr.move(self.screen_h - 1, 0)
        self.stdscr.clrtoeol()
        self.stdscr.addstr(self.screen_h - 1, 0, prompt)
        self.stdscr.refresh()

        result = ""
        while True:
            ch = self.stdscr.getch()
            if ch in (10, 13):
                break
            if ch == 27:
                result = None
                break
            if ch in (8, 127, curses.KEY_BACKSPACE):
                if result:
                    result = result[:-1]
                    self.stdscr.move(self.screen_h - 1, len(prompt))
                    self.stdscr.clrtoeol()
                    self.stdscr.addstr(result)
            elif 32 <= ch <= 126:
                result += chr(ch)
            time.sleep(0.01)

        curses.noecho()
        curses.curs_set(0)
        self.stdscr.move(self.screen_h - 1, 0)
        self.stdscr.clrtoeol()
        return result

    def _show_help(self):
        """Displays the help overlay."""
        lines = [
            "  pretty_j1939 Curses Viewer Help",
            "  -------------------------------",
            "  q / ESC   : Quit viewer",
            "  Space     : Pause / Resume data receipt",
            "  c         : Clear all history and reset",
            "  s         : Sort rows by CAN ID",
            "  h         : Toggle highlighting for changed SPNs",
            "  ?         : Show this help screen",
            "  UP / DOWN : Scroll display rows",
            "",
            "  Logging (Log Changes Mode):",
            "  l         : Enter Selection Mode",
            "  SPACE     : (In Selection Mode) Mark ID for logging",
            "  ENTER     : Confirm selection and start logging",
            "  ESC       : Stop active logging or exit mode",
            "",
            "  [ Press any key to close help ]",
        ]
        h, w = len(lines) + 4, 60
        y, x = (self.screen_h - h) // 2, (self.screen_w - w) // 2
        win = curses.newwin(h, w, y, x)
        win.box()
        for i, line in enumerate(lines):
            win.addstr(i + 2, 2, line[: w - 4])
        win.refresh()
        while self.stdscr.getch() == -1:
            time.sleep(0.01)
        self._redraw_all()

    def _handle_input(self) -> bool:
        """Processes a single keypress. Returns False if the app should quit."""
        key = self.stdscr.getch()
        if key == -1:
            return True

        if key == 27:  # ESC
            if self.ui.active_logging_ids:
                self._stop_logging()
                self._redraw_all()
            elif self.ui.selection_cursor is not None:
                self.ui.selection_cursor = None
                self.ui.marked_ids.clear()
                self._redraw_all()
            else:
                return False
        elif key == ord("q"):
            return False
        elif key == ord("?"):
            self._show_help()
        elif key == ord("c"):
            self.messages.clear()
            self.id_order.clear()
            self.ui.scroll = 0
            self._draw_header()
        elif key == ord("s"):
            self.id_order.sort()
            self._redraw_all()
        elif key == ord("h"):
            self.ui.highlight_changes = not self.ui.highlight_changes
            self._redraw_all()
        elif key == ord(" "):
            if self.ui.selection_cursor is not None:
                kid = self.id_order[self.ui.selection_cursor]
                if kid in self.ui.marked_ids:
                    self.ui.marked_ids.remove(kid)
                else:
                    self.ui.marked_ids.add(kid)
                self._redraw_all()
            else:
                self.ui.paused = not self.ui.paused
        elif key == ord("l") and not self.ui.active_logging_ids:
            self.ui.selection_cursor = (
                0 if (not self.ui.selection_cursor and self.id_order) else None
            )
            self.ui.marked_ids.clear()
            self._redraw_all()
        elif key in (10, 13) and self.ui.selection_cursor is not None:
            if not self.ui.marked_ids:
                self.ui.marked_ids.add(self.id_order[self.ui.selection_cursor])
            fname = self._get_user_input("Log filename: ")
            if fname:
                try:
                    self.ui.log_file_handle = open(fname, "a")
                    self.ui.active_logging_ids, self.ui.log_filename = (
                        self.ui.marked_ids.copy(),
                        fname,
                    )
                    self.ui.selection_cursor = None
                    self.ui.marked_ids.clear()
                except Exception as e:
                    self._get_user_input(f"Error: {e} (Enter)")
            else:
                self.ui.selection_cursor = None
                self.ui.marked_ids.clear()
            self._redraw_all()
        elif key == curses.KEY_UP:
            if self.ui.selection_cursor is not None:
                self.ui.selection_cursor = max(0, self.ui.selection_cursor - 1)
                self._redraw_all()
            elif self.ui.scroll > 0:
                self.ui.scroll -= 1
                self._redraw_all()
        elif key == curses.KEY_DOWN:
            if self.ui.selection_cursor is not None:
                self.ui.selection_cursor = min(
                    len(self.id_order) - 1, self.ui.selection_cursor + 1
                )
                self._redraw_all()
            else:
                total_rows = sum(m.num_rows for m in self.messages.values())
                if self.ui.scroll < max(0, total_rows - (self.screen_h - 2)):
                    self.ui.scroll += 1
                    self._redraw_all()
        return True

    # --- Processing ---

    def _stop_logging(self):
        if self.ui.log_file_handle:
            self.ui.log_file_handle.close()
        self.ui.log_file_handle = None
        self.ui.active_logging_ids.clear()
        self.ui.log_filename = ""

    def _process_message(self, msg: can.Message):
        """Decodes message and updates internal state."""
        key = msg.arbitration_id | (1 << 32 if msg.is_extended_id else 0)

        if key not in self.messages:
            self.messages[key] = MessageState(msg=msg, last_time=msg.timestamp)
            self.id_order.append(key)
        else:
            state = self.messages[key]
            state.dt = msg.timestamp - state.last_time
            if self.ui.highlight_changes:
                state.previous_description = state.description.copy()
                state.previous_data_hex = state.msg.data.hex().upper()
            state.last_time, state.msg = msg.timestamp, msg

        state = self.messages[key]
        state.count += 1

        new_desc = self.describer(msg.data, msg.arbitration_id)

        # Logging check
        if key in self.ui.active_logging_ids and self.ui.log_file_handle:
            if new_desc != state.description:
                entry = {
                    "timestamp": msg.timestamp,
                    "id": (
                        f"0x{msg.arbitration_id:08X}"
                        if msg.is_extended_id
                        else f"0x{msg.arbitration_id:03X}"
                    ),
                    "data": msg.data.hex().upper(),
                    "pretty": {
                        k: v for k, v in new_desc.items() if not k.startswith("_")
                    },
                }
                self.ui.log_file_handle.write(json.dumps(entry) + "\n")
                self.ui.log_file_handle.flush()

        state.description = new_desc
        new_rows = self._calculate_required_rows(state)

        if new_rows != state.num_rows:
            state.num_rows = new_rows
            self._redraw_all()
        else:
            # Targeted update
            row_pos = 1
            for k in self.id_order:
                if k == key:
                    self._draw_message_row(k, row_pos)
                    break
                row_pos += self.messages[k].num_rows

    def run(self):
        """Main application loop."""
        self._draw_header()
        while True:
            if not self.ui.paused:
                msg = self.bus.recv(timeout=REFRESH_RATE_MS)
                if msg:
                    self._process_message(msg)
            else:
                time.sleep(REFRESH_RATE_MS)

            if not self._handle_input():
                break

            if curses.is_term_resized(self.screen_h, self.screen_w):
                self.screen_h, self.screen_w = self.stdscr.getmaxyx()
                if hasattr(curses, "resizeterm"):
                    curses.resizeterm(self.screen_h, self.screen_w)
                self._redraw_all()

        self._stop_logging()
        self.bus.shutdown()


def main():
    if can is None:
        raise ImportError(
            "Error: 'python-can' is not installed. Curses viewer requires 'python-can'."
        )

    from .__main__ import get_parser

    parser = get_parser()
    parser.description = "Pretty J1939 Curses Viewer"
    args, _ = parser.parse_known_args()

    describer = get_describer(
        da_json=args.da_json,
        describe_pgns=args.pgn,
        describe_spns=args.spn,
        describe_link_layer=args.link,
        describe_transport_layer=args.transport,
        real_time=args.real_time,
        include_transport_rawdata=args.candata,
        include_na=args.include_na,
        include_raw_data=args.include_raw_data,
        enable_isotp=args.enable_isotp,
    )

    try:
        curses.wrapper(
            J1939Viewer,
            create_bus_from_namespace(args),
            describer,
            theme_name=args.theme,
        )
    except KeyboardInterrupt:
        logger.info("Viewer terminated by user")


if __name__ == "__main__":
    main()
