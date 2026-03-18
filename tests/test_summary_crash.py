#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
import pytest
from pretty_j1939.render import HighPerformanceRenderer


def test_render_summary_with_none_names():
    """Verify that render_summary doesn't crash when names are None."""
    theme = HighPerformanceRenderer.load_theme(None)
    renderer = HighPerformanceRenderer(theme)

    # The original crash occurs because sorted() tries to compare None with str when SA is the same
    summary_data = {
        (0, 255, "Engine", "All"): {"sent": {61444}, "req": set()},
        (0, 255, None, "All"): {"sent": {61444}, "req": set()},
    }

    # This should not raise TypeError
    rendered = renderer.render_summary(summary_data)
    assert "Summary" in rendered
    assert "Engine" in rendered
    assert "N0" in rendered


def test_render_summary_mixed_key_lengths():
    """Verify that render_summary handles mixed key lengths (2 and 4)."""
    theme = HighPerformanceRenderer.load_theme(None)
    renderer = HighPerformanceRenderer(theme)

    summary_data = {
        (0, 255, "Engine", "All"): {"sent": {61444}, "req": set()},
        (1, 255): {"sent": {61443}, "req": set()},
    }

    rendered = renderer.render_summary(summary_data)
    assert "Summary" in rendered
    assert "N0_Engine" in rendered
    assert "N1" in rendered


def test_render_summary_all_none_names():
    """Verify that render_summary handles keys where all names are None."""
    theme = HighPerformanceRenderer.load_theme(None)
    renderer = HighPerformanceRenderer(theme)

    summary_data = {
        (0, 1, None, None): {"sent": {61444}, "req": set()},
        (1, 0, None, None): {"sent": {61443}, "req": set()},
    }

    rendered = renderer.render_summary(summary_data)
    assert "N0" in rendered
    assert "N1" in rendered


def test_render_summary_address_255_special_handling():
    """Verify that address 255 (All) is handled correctly even with weird keys."""
    theme = HighPerformanceRenderer.load_theme(None)
    renderer = HighPerformanceRenderer(theme)

    summary_data = {
        (0, 255, "Engine", None): {"sent": {61444}, "req": set()},
        (255, 0, "Wait, All usually doesn't send", "Engine"): {
            "sent": {59904},
            "req": set(),
        },
    }

    rendered = renderer.render_summary(summary_data)
    assert "All" in rendered
    assert "N0" in rendered


def test_render_summary_empty():
    """Verify that empty summary data returns an empty string or basic JSON."""
    theme = HighPerformanceRenderer.load_theme(None)
    renderer = HighPerformanceRenderer(theme)

    assert renderer.render_summary({}) == ""


def test_cli_oserror_handling():
    """Verify that main() catches OSError (like FileNotFoundError)."""
    from pretty_j1939.__main__ import main
    import sys
    from io import StringIO
    from unittest.mock import patch

    original_argv = sys.argv
    sys.argv = ["pretty_j1939", "--da-json", "nonexistent.json", "some.log"]

    stderr = StringIO()
    # We also mock sys.stdout to avoid polluting test output if it were to print anything
    with patch("sys.stderr", stderr), patch("sys.stdout", StringIO()):
        with pytest.raises(SystemExit) as excinfo:
            main()

    sys.argv = original_argv
    assert excinfo.value.code == 1
    assert "FileNotFoundError" in stderr.getvalue()
