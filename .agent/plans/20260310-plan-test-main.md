# Implementation Plan: Test Coverage for __main__.py

## 0. Strict Execution Rules & Command Summary
**IMPROVISATION IS NOT ALLOWED.** The plan must be followed exactly as specified. If any step fails or if the exact instructions cannot be followed, you must stop immediately and ask for direction from the user.

### Verified Command Menu
*   **Run Test Suite:** `python3 -m pytest tests/test_cli.py -v`
*   **Run Coverage:** `python3 -m pytest --cov=pretty_j1939.__main__ tests/test_cli.py`

## 1. Objective
Add comprehensive unit test coverage for the `process_messages()` method in `pretty_j1939/__main__.py`. This function handles file and interface inputs, parsing disparate formats (candump, Wireshark, standard hex). It is currently 178 LOC with weak test coverage in error paths.

### 1.1 Future-Proofing / Readiness
By ensuring robust testing of the parsing branches, we can eventually extract these format-specific parsers into their own dedicated input-processing modules.

## 2. Current Architecture & Required Refactoring
`process_messages` iterates over an input stream, determining line formats dynamically, cleaning strings, extracting timestamps, and feeding the ID/bytes to the central describer. 

### Action Items for Code:
1.  **Testing Strategies:** Use `io.StringIO` to mock `sys.stdin` or input files, passing strings mimicking various common formats. Use a mock describer or verify the final printed output via `capsys`.

## 3. Testing Architecture

### 3.1 Build System Setup
No special build setup required; Python `pytest` will be used.

### 3.2 Test Suite Implementation
We will enhance `tests/test_cli.py` (or create a dedicated module) by directly instantiating the `J1939Runner`, injecting fake inputs via `StringIO`, and capturing the printed output.

## 4. Execution Steps, File Modifications, & Checkpoints
Follow these steps strictly. After completing a step, verify the checkpoint before proceeding to the next. Do not skip checkpoints.

### [ ] Step 1: Test Standard Candump Parsing
*   **Files Modified:** `tests/test_cli.py`
*   **Actions:** Write `test_process_messages_candump()`. Initialize `J1939Runner` and feed it a standard timestamped candump line. Assert the output stream receives the correctly parsed message.
*   **Checkpoint 1:** Does the test pass?

### [ ] Step 2: Test Alternate Formats (Wireshark/Hex)
*   **Files Modified:** `tests/test_cli.py`
*   **Actions:** Write `test_process_messages_alternate_formats()`. Feed lines containing `#` delimiters or space-delimited raw hex. Verify successful parsing.
*   **Checkpoint 2:** Does the test pass?

### [ ] Step 3: Test Malformed Input Resilience
*   **Files Modified:** `tests/test_cli.py`
*   **Actions:** Write `test_process_messages_malformed()`. Send invalid strings (bad hex, missing spaces) and verify that the system gracefully logs and continues via the recently added `except (ValueError, IndexError)` paths, without raising unhandled exceptions.
*   **Checkpoint 3:** Do the tests pass, and does coverage for `process_messages` improve significantly?

### [ ] Step 4: Final Run Report
*   **Files Modified:** `.agent/run_reports/20260310-test-main-run_report.md`
*   **Actions:** Compile execution statuses into the run report.