# Implementation Plan: Test Coverage for viewer.py

## 0. Strict Execution Rules & Command Summary
**IMPROVISATION IS NOT ALLOWED.** The plan must be followed exactly as specified. If any step fails or if the exact instructions cannot be followed, you must stop immediately and ask for direction from the user.

### Verified Command Menu
*   **Run Test Suite:** `python3 -m pytest tests/test_viewer.py -v`
*   **Run Coverage:** `python3 -m pytest --cov=pretty_j1939.viewer tests/test_viewer.py`

## 1. Objective
Add comprehensive unit test coverage for the `_draw_message_row()` method in `pretty_j1939/viewer.py`. The rendering logic (lines 254-444) has zero test coverage and is highly complex, making it a "monster function." Adding tests is the prerequisite for safe refactoring.

### 1.1 Future-Proofing / Readiness
The testing must decouple the UI logic from an actual terminal environment, allowing headless CI runners to validate rendering commands.

## 2. Current Architecture & Required Refactoring
`_draw_message_row` receives a `MessageState` and invokes multiple `self.stdscr.addstr()` and `self.stdscr.attron/attroff` calls to render hex, ASCII, and decoded text onto the screen.

### Action Items for Code:
1.  **Testing Strategies:** Mock the `curses` window object (`stdscr`). We will capture calls to `addstr()` and `attron()` to verify that the correct text and color pairs are emitted for given CAN frames, without needing a real terminal display.

## 3. Testing Architecture

### 3.1 Build System Setup
No special build setup required; Python `pytest` will be used.

### 3.2 Test Suite Implementation
We will add test cases to `tests/test_viewer.py`. We will create a `MockWindow` class to track cursor positions and printed strings, simulating how curses works, and inject it into the `J1939Viewer` UI instance.

## 4. Execution Steps, File Modifications, & Checkpoints
Follow these steps strictly. After completing a step, verify the checkpoint before proceeding to the next. Do not skip checkpoints.

### [ ] Step 1: Scaffold Curses Mock
*   **Files Modified:** `tests/test_viewer.py`
*   **Actions:** Create a `MockWindow` class that tracks `addstr()`, `attron()`, `attroff()`, and dimensions (e.g., `getmaxyx()`).
*   **Checkpoint 1:** Does the test suite run cleanly with the new mock class defined?

### [ ] Step 2: Test Standard Message Rendering
*   **Files Modified:** `tests/test_viewer.py`
*   **Actions:** Write `test_draw_message_row_standard()`. Initialize `J1939Viewer` with the mock window, feed a standard parsed `MessageState`, call `_draw_message_row()`, and assert `addstr` was called with the expected parsed PGN and data.
*   **Checkpoint 2:** Does the test pass?

### [ ] Step 3: Test Highlight Changes Logic
*   **Files Modified:** `tests/test_viewer.py`
*   **Actions:** Write `test_draw_message_row_highlights()`. Configure the `UIState` to `highlight_changes=True`, provide a previous message state, and assert that specific byte differences use the changed color attribute.
*   **Checkpoint 3:** Does the test pass?

### [ ] Step 4: Test ANSI Stripping & Edge Cases
*   **Files Modified:** `tests/test_viewer.py`
*   **Actions:** Write tests feeding descriptions containing ANSI escape codes, ensuring the rendered text is stripped properly before being passed to `addstr`.
*   **Checkpoint 4:** Do the tests pass, and does coverage for `_draw_message_row` improve significantly?

### [ ] Step 5: Final Run Report
*   **Files Modified:** `.agent/run_reports/20260310-test-viewer-run_report.md`
*   **Actions:** Compile execution statuses into the run report.