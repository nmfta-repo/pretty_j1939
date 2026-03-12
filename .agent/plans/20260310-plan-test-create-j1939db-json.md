# Implementation Plan: Test Coverage for create_j1939db_json.py

## 0. Strict Execution Rules & Command Summary
**IMPROVISATION IS NOT ALLOWED.** The plan must be followed exactly as specified. If any step fails or if the exact instructions cannot be followed, you must stop immediately and ask for direction from the user.

### Verified Command Menu
*   **Run Test Suite:** `python3 -m pytest tests/test_create_j1939db_json.py -v`
*   **Run Coverage:** `python3 -m pytest --cov=pretty_j1939.create_j1939db_json tests/test_create_j1939db_json.py`

## 1. Objective
Add comprehensive unit test coverage for the `process_spns_and_pgns_tab()` method in `pretty_j1939/create_j1939db_json.py`. Currently, this method is a "monster function" (279 LOC) and has very low test coverage. Adding tests will make it safe to refactor.

### 1.1 Future-Proofing / Readiness
The tests must be isolated using mocked `xlrd` sheet objects to avoid relying on large, slow, or proprietary Excel databases, allowing for quick, deterministic validation.

## 2. Current Architecture & Required Refactoring
The `process_spns_and_pgns_tab()` method is a massive loop processing rows from an Excel sheet. It parses standard SPNs, variable-length SPNs, enum bit-decodings, and handles missing/malformed cells. 

### Action Items for Code:
1.  **Testing Strategies:** Use `unittest.mock` to create synthetic `xlrd.sheet` objects or simple lists/dicts that duck-type as rows. Provide specific rows representing typical cases (standard numeric SPN), edge cases (variable length, missing units), and enum cases (discrete bit states).

## 3. Testing Architecture

### 3.1 Build System Setup
No special build setup required; Python `pytest` will be used.

### 3.2 Test Suite Implementation
We will append tests to the existing `tests/test_create_j1939db_json.py` (or create a new test file specifically for the complex tab). The tests will instantiate `J1939daConverter`, inject a mocked sheet, and verify the resulting `j1939db` dictionary state.

## 4. Execution Steps, File Modifications, & Checkpoints
Follow these steps strictly. After completing a step, verify the checkpoint before proceeding to the next. Do not skip checkpoints.

### [ ] Step 1: Scaffold Mock Data Infrastructure
*   **Files Modified:** `tests/test_create_j1939db_json.py`
*   **Actions:** Create a helper function or fixture that returns a mocked `xlrd` sheet object populated with a custom set of rows for the "SPNs & PGNs" tab.
*   **Checkpoint 1:** Does `pytest tests/test_create_j1939db_json.py` run without syntax or import errors?

### [ ] Step 2: Implement Standard SPN Test
*   **Files Modified:** `tests/test_create_j1939db_json.py`
*   **Actions:** Write `test_process_spns_standard()` that feeds a standard SPN row to `process_spns_and_pgns_tab()` and asserts the correct PGN/SPN dictionary entries are created.
*   **Checkpoint 2:** Does the new test pass? 

### [ ] Step 3: Implement Enum/Bit-decoding SPN Test
*   **Files Modified:** `tests/test_create_j1939db_json.py`
*   **Actions:** Write `test_process_spns_enum()` that provides rows with discrete states (e.g. `00`="Off", `01`="On") and asserts that `J1939BitDecodings` is populated correctly.
*   **Checkpoint 3:** Does the test pass?

### [ ] Step 4: Implement Variable Length & Edge Case Tests
*   **Files Modified:** `tests/test_create_j1939db_json.py`
*   **Actions:** Write tests for variable length SPNs, missing values, and empty rows to ensure exception handlers don't crash.
*   **Checkpoint 4:** Do the tests pass, and does the coverage report show an increase for `process_spns_and_pgns_tab`?

### [ ] Step 5: Final Run Report
*   **Files Modified:** `.agent/run_reports/20260310-test-create-j1939db-json-run_report.md`
*   **Actions:** Compile execution statuses and outcomes of checkpoints into the run report.
