#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import pytest
from pretty_j1939.core.render import HighPerformanceRenderer

def test_render_no_color():
    renderer = HighPerformanceRenderer(color_system=None)
    description = {"PGN": "EEC1(61444)", "Engine Speed": "2308.0 [rpm]"}
    output = renderer.render(description)
    assert output == '{"PGN":"EEC1(61444)","Engine Speed":"2308.0 [rpm]"}'

def test_render_no_color_indent():
    renderer = HighPerformanceRenderer(color_system=None)
    description = {"PGN": "EEC1(61444)", "Engine Speed": "2308.0 [rpm]"}
    output = renderer.render(description, indent=True)
    expected = '''{
    "PGN": "EEC1(61444)",
    "Engine Speed": "2308.0 [rpm]"
}'''
    assert output == expected

def test_render_with_color():
    renderer = HighPerformanceRenderer(color_system="truecolor")
    description = {"PGN": "EEC1(61444)", "Engine Speed": "2308.0 [rpm]"}
    output = renderer.render(description)
    # Basic check for ANSI codes
    assert "\x1b[" in output
    assert '"PGN"' in output
    assert "EEC1" in output
    assert "61444" in output

def test_render_with_can_line():
    renderer = HighPerformanceRenderer(color_system=None)
    description = {"PGN": "EEC1(61444)"}
    can_line = "(123.456) can0 18F00400#"
    output = renderer.render(description, can_line=can_line)
    assert output == '(123.456) can0 18F00400#{"PGN":"EEC1(61444)"}'

def test_render_bytes():
    renderer = HighPerformanceRenderer(color_system="truecolor")
    description = {"Bytes": "0x48656C6C6F"}
    output = renderer.render(description)
    assert "\x1b[" in output
    assert "48656C6C6F" in output

def test_render_highlight():
    renderer = HighPerformanceRenderer(color_system="truecolor")
    description = {"PGN": "EEC1(61444)"}
    output = renderer.render(description, highlight=True)
    assert renderer.ansi_esc.get("highlight", "") in output
