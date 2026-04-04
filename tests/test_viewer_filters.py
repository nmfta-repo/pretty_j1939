import pytest
import can
from unittest.mock import patch, MagicMock
from pretty_j1939.viewer import J1939Viewer, main
from pretty_j1939.describe import J1939Filter


@pytest.fixture
def mock_curses():
    with patch("pretty_j1939.viewer.curses") as mock:
        mock.color_pair.side_effect = lambda x: x * 256
        mock.A_NORMAL = 0
        mock.A_BOLD = 1
        yield mock


def test_process_message_with_filter(mock_curses):
    win = MagicMock()
    win.getmaxyx.return_value = (24, 80)
    bus = MagicMock()
    describer = MagicMock()

    # Create a filter that only allows PGN 0xFEEB
    j1939_filter = MagicMock(spec=J1939Filter)

    with patch.object(J1939Viewer, "run"):
        viewer = J1939Viewer(win, bus, describer, j1939_filter=j1939_filter)

    # 1. Message that matches
    msg_match = can.Message(
        arbitration_id=0x18FEEB00, data=b"\x01" * 8, is_extended_id=True
    )
    desc_match = {"_pgn": 0xFEEB, "RPM": 1000}
    describer.return_value = desc_match
    j1939_filter.matches.return_value = True

    viewer._process_message(msg_match)

    assert 0x18FEEB00 | (1 << 32) in viewer.messages
    j1939_filter.matches.assert_called_with(desc_match)

    # 2. Message that does NOT match
    msg_no_match = can.Message(
        arbitration_id=0x18FEF100, data=b"\x02" * 8, is_extended_id=True
    )
    desc_no_match = {"_pgn": 0xFEF1, "Speed": 50}
    describer.return_value = desc_no_match
    j1939_filter.matches.return_value = False

    viewer._process_message(msg_no_match)

    assert 0x18FEF100 | (1 << 32) not in viewer.messages


def test_viewer_main_filters():
    # Test that main() correctly processes filter arguments and passes them to J1939Filter and can.Bus
    test_args = [
        "viewer",
        "--filter-pgn",
        "65261",
        "--filter-sa",
        "0",
        "--interface",
        "virtual",
        "--channel",
        "vcan0",
    ]

    with patch("sys.argv", test_args), patch(
        "pretty_j1939.viewer.can.Bus"
    ) as mock_bus, patch("pretty_j1939.viewer.curses.wrapper") as mock_wrapper, patch(
        "pretty_j1939.viewer.get_describer"
    ) as mock_get_describer:

        mock_da_describer = MagicMock()
        mock_get_describer.return_value.da_describer = mock_da_describer

        main()

        # Verify can.Bus was called with expected filters
        # J1939Filter should have been created and generate_can_filters called
        args, kwargs = mock_bus.call_args
        assert kwargs["interface"] == "virtual"
        assert kwargs["channel"] == "vcan0"
        assert "can_filters" in kwargs

        # Verify curses.wrapper was called with J1939Viewer and the filter
        wrapper_args = mock_wrapper.call_args[0]
        assert wrapper_args[0] == J1939Viewer
        # wrapper_args[1] is the bus
        # wrapper_args[2] is the describer
        # kwargs in wrapper are passed to J1939Viewer
        wrapper_kwargs = mock_wrapper.call_args[1]
        assert "j1939_filter" in wrapper_kwargs
        assert isinstance(wrapper_kwargs["j1939_filter"], J1939Filter)
        assert wrapper_kwargs["j1939_filter"].pgn_list == [65261]
        assert wrapper_kwargs["j1939_filter"].sa_list == [0]
