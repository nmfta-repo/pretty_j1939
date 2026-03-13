import pytest
import can
import curses
from unittest.mock import patch, MagicMock

from pretty_j1939.cli.viewer import hex_to_curses_basic, MessageState, UIState, J1939Viewer


def test_hex_to_curses_basic():
    # Test valid hex
    assert hex_to_curses_basic("#000000") == 0  # Black
    assert hex_to_curses_basic("#ffffff") == 7  # White
    assert hex_to_curses_basic("#ff0000") == 1  # Red
    assert hex_to_curses_basic("default") == -1

    # Test invalid hex formats fallback to white (7)
    assert hex_to_curses_basic("invalid") == 7
    assert hex_to_curses_basic("#123") == 7


def test_ui_state_init():
    ui = UIState()
    assert ui.scroll == 0
    assert not ui.paused
    assert not ui.highlight_changes
    assert ui.selection_cursor is None
    assert len(ui.marked_ids) == 0
    assert len(ui.active_logging_ids) == 0
    assert ui.log_file_handle is None
    assert ui.log_filename == ""


class MockWindow:
    def __init__(self):
        self.addstr_calls = []
        self.attron_calls = []
        self.attroff_calls = []
        self.chgat_calls = []
        self.current_attr = 0
        self.y = 0
        self.x = 0

    def erase(self):
        pass

    def move(self, y, x):
        self.y = y
        self.x = x

    def clrtoeol(self):
        pass

    def chgat(self, *args):
        self.chgat_calls.append(args)

    def addstr(self, *args):
        self.addstr_calls.append(args)

    def attron(self, attr):
        self.current_attr |= attr
        self.attron_calls.append(attr)

    def attroff(self, attr):
        self.current_attr &= ~attr
        self.attroff_calls.append(attr)

    def getmaxyx(self):
        return (24, 80)

    def refresh(self):
        pass

    def nodelay(self, flag):
        pass


@pytest.fixture
def mock_curses():
    with patch("pretty_j1939.cli.viewer.curses") as mock:
        mock.color_pair.side_effect = lambda x: x * 256
        mock.A_NORMAL = 0
        mock.A_BOLD = 1
        yield mock


def test_draw_message_row_standard(mock_curses):
    win = MockWindow()

    with patch.object(J1939Viewer, "run"):
        viewer = J1939Viewer(win, MagicMock(), MagicMock(), theme_name="monokai")

    msg = can.Message(
        arbitration_id=0x18FEEB00,
        data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
        is_extended_id=True,
    )
    state = MessageState(msg=msg, count=5, dt=0.01)
    state.description = {"PGN": "Engine RPM", "RPM": "1000"}
    viewer.messages[0x18FEEB00] = state
    viewer.id_order = [0x18FEEB00]

    viewer._draw_message_row(0x18FEEB00, 2)

    # Assert addstr called with correct outputs
    found_count = False
    found_rpm = False
    for args in win.addstr_calls:
        if "5" in str(args[2]):
            found_count = True
        if "1000" in str(args[2]):
            found_rpm = True

    assert found_count, "Expected count '5' to be drawn"
    assert found_rpm, "Expected '1000' (RPM value) to be drawn"


def test_draw_message_row_highlights(mock_curses):
    win = MockWindow()

    with patch.object(J1939Viewer, "run"):
        viewer = J1939Viewer(win, MagicMock(), MagicMock(), theme_name="monokai")

    viewer.ui.highlight_changes = True

    msg = can.Message(
        arbitration_id=0x18FEEB00,
        data=b"\x01\x02\x03\x04\x05\x06\x07\x08",
        is_extended_id=True,
    )
    state = MessageState(msg=msg, count=5, dt=0.01)
    state.description = {"PGN": "Engine RPM", "RPM": "1000"}

    state.previous_data_hex = "0102030005060708"  # 4th byte changed from 00 to 04
    state.previous_description = {"PGN": "Engine RPM", "RPM": "900"}  # RPM changed

    viewer.messages[0x18FEEB00] = state
    viewer.id_order = [0x18FEEB00]

    viewer._draw_message_row(0x18FEEB00, 2)

    # color_pair(5) is mock-mapped to 5 * 256 = 1280
    CHANGED_ATTR = 1280

    # Check that "04" was printed with the changed color
    found_changed_byte = False
    for args in win.addstr_calls:
        if len(args) >= 4:
            text, attr = args[2], args[3]
            if text == "04" and attr == CHANGED_ATTR:
                found_changed_byte = True

    assert (
        found_changed_byte
    ), "Expected changed byte '04' to be drawn with color_pair(5)"

    # Check that "RPM" value "1000" or the key-value pair was printed with the changed color
    found_changed_pretty = False
    for args in win.addstr_calls:
        if len(args) >= 4:
            text, attr = args[2], args[3]
            if "RPM" in text and attr == CHANGED_ATTR:
                found_changed_pretty = True
            if "1000" in text and attr == CHANGED_ATTR:
                found_changed_pretty = True

    assert (
        found_changed_pretty
    ), "Expected changed pretty description to use color_pair(5)"
