# Implementation Plan: Test Coverage for describe.py

## 0. Strict Execution Rules & Command Summary
**IMPROVISATION IS NOT ALLOWED.** The plan must be followed exactly as specified. If any step fails or if the exact instructions cannot be followed, you must stop immediately and ask for direction from the user.

### Verified Command Menu
*   **Run Test Suite:** `python3 -m pytest tests/test_describe.py -v`
*   **Run Coverage:** `python3 -m pytest --cov=pretty_j1939.describe tests/test_describe.py`

## 1. Objective
Add comprehensive unit test coverage for the `describe_message_data()` method in `pretty_j1939/describe.py`. This method is the core translation engine, coming in at 309 LOC. It contains complex bit-extraction, dictionary lookups, and overlapping boundary logic.

### 1.1 Future-Proofing / Readiness
High coverage here will allow us to break this function into smaller, specialized decoders (e.g., bit-state extractor, string extractor, numeric extractor) safely.

## 2. Current Architecture & Required Refactoring
The function uses a complex inner function and deep nested logic to iterate through available SPNs, slice out specific bit ranges, handle endienness, and resolve indicators (NA, Error). 

### Action Items for Code:
1.  **Testing Strategies:** Provide a controlled, minimal `da_json` database to a `DADescriber` instance, and then pass specific raw `bitstring.Bits` to trigger boundary conditions, error indicators, and N/A fallbacks.

## 3. Testing Architecture

### 3.1 Build System Setup
No special build setup required; Python `pytest` will be used.

### 3.2 Test Suite Implementation
We will enhance `tests/test_describe.py`. Tests will verify the exact text outputs for various contrived bit sequences corresponding to our mock database.

## 4. Execution Steps, File Modifications, & Checkpoints
Follow these steps strictly. After completing a step, verify the checkpoint before proceeding to the next. Do not skip checkpoints.

### [ ] Step 1: Scaffold Minimal DA JSON Mock
*   **Files Modified:** `tests/test_describe.py`
*   **Actions:** Create a minimal dictionary representing `J1939db` with a single PGN containing SPNs specifically crafted to test unaligned bits, missing data, and standard decoding.
*   **Checkpoint 1:** Does the minimal describer initialize without errors?

### [ ] Step 2: Test Unaligned Bit Extraction
*   **Files Modified:** `tests/test_describe.py`
*   **Actions:** Write `test_describe_message_data_unaligned()`. Feed a bitstring where the SPN boundaries fall across byte lines (e.g., length 3 bits at offset 5). Verify correct decoded value.
*   **Checkpoint 2:** Does the test pass?

### [ ] Step 3: Test SPN N/A and Error States
*   **Files Modified:** `tests/test_describe.py`
*   **Actions:** Write `test_describe_message_data_indicators()`. Provide a bit payload corresponding to `FE` (Error) and `FF` (N/A) indicator ranges based on SPN bit lengths. Verify the description outputs "Error" and "N/A".
*   **Checkpoint 3:** Do the tests pass?

### [ ] Step 4: Test SPN Resolution & Formatting
*   **Files Modified:** `tests/test_describe.py`
*   **Actions:** Provide values requiring resolution multipliers and offsets. Verify the formatting outputs correct float rounding and appends the unit label correctly.
*   **Checkpoint 4:** Do the tests pass, and does coverage for `describe_message_data` improve significantly?

### [ ] Step 5: Final Run Report
*   **Files Modified:** `.agent/run_reports/20260310-test-describe-run_report.md`
*   **Actions:** Compile execution statuses into the run report.