# Implementation Plan Template

## Instructions for Use
1. **Copy this template:** Make a copy of this file into `.agent/plans/YYYYMMDD-<short-description>.md`. Remove this Instructions for use subsection and change the TL heading title
2. **Fill it out iteratively:** Work with the user to fill out sections 1-3. Do not rush to execution. Ask clarifying questions until the objective, current architecture, and required actions are fully understood.
    1. DO: ask the user clarifying questions
    2. DO: ensure the details written to teh plan are sufficient for another agent to execute with little context
    3. DO NOT: assume something is best or assume what the user wants
3. **Verify Commands:** Before finalizing the plan, test and verify *every* shell command, build script, and test invocation in the target environment to ensure they work as intended. Collect them in Section 0.
4. **Detail the Steps:** Break down the work in Section 4 into discrete, verifiable steps. A step is only complete when its "Checkpoint" can be empirically proven to have passed.
5. **Execute Autonomously:** Once the plan is agreed upon and commands are verified, wait for the user to request that the agent should follow the plan. After that time, during execution of the plan , If a step fails and cannot be resolved, the agent must stop and ask the user for direction.

---

## 0. Strict Execution Rules & Command Summary
**IMPROVISATION IS NOT ALLOWED.** The plan must be followed exactly as specified. If any step fails or if the exact instructions cannot be followed, you must stop immediately and ask for direction from the user.

### Verified Command Menu
*(Agent: complete this list with any and all commands used in section 4. Pre-verify these commands in the environment before adding them here. Ensure flags, paths, and dependencies are correct for the target system.)*
*   **Compile Code:** `[Insert verified compilation command, e.g., gcc with necessary -I and -D flags]`
*   **Run Test Suite:** `[Insert verified test command, e.g., python3 -m pytest path/to/test.py -v]`
*   **Firmware/Project Build:** `[Insert verified build script command, e.g., scripts/build/docker_BUILD_Clean_Release.sh > build.log 2>&1]`

## 1. Objective
*(Agent: Clearly define the end goal of this plan. What feature is being added? What bug is being fixed? What is the expected final state of the system?)*

### 1.1 Future-Proofing / Readiness (Optional)
*(Agent: Note any upcoming architectural changes this plan must accommodate, such as supporting parallel implementations or specific design patterns.)*

## 2. Current Architecture & Required Refactoring
*(Agent: Analyze and describe the current state of the codebase relevant to the objective. Identify pain points, tight coupling, or missing abstractions.)*

### Action Items for Code:
1.  **Centralization/Refactoring:** *(Detail what logic needs to move where.)*
2.  **Modularization:** *(Define how functions/classes should be structured to decouple them from hardware/global state.)*
3.  **Mocking/Testing Strategies:** *(Define how hardware or environment dependencies will be mocked, e.g., using compiler flags like `-D__MAIN_H` to prevent hardware includes during host compilation.)*

## 3. Testing Architecture
*(Agent: Define how the changes will be validated. If creating a hybrid test, detail the bindings and runner.)*

### 3.1 Build System Setup
*(Detail how the test artifacts will be built, including specific scripts or Makefiles to be created.)*

### 3.2 Test Suite Implementation
*(Detail the structure of the test suite, such as parameterization loops, expected inputs, and assertion logic. Ensure the test suite is automated where possible, e.g., triggering compilation automatically before running tests.)*

## 4. Execution Steps, File Modifications, & Checkpoints
Follow these steps strictly. After completing a step, verify the checkpoint before proceeding to the next. Do not skip checkpoints.

### [ ] Step 1: Scaffold Infrastructure
*   **Files Modified:** `[List files]`
*   **Actions:** *(e.g., Create build scripts, stub out test files, verify environment dependencies.)*
*   **Checkpoint 1:** *(e.g., Do the scripts execute without error? Do necessary imports work?)*

### [ ] Step 2: Implement Core Modules
*   **Files Modified:** `[List files]`
*   **Actions:** *(e.g., Implement the core C/Python/JS logic. Apply necessary mocking strategies (like compiler guard flags) to ensure it compiles in isolation. Iteratively build the firmware/project and resolve errors.)*
*   **Checkpoint 2:** *(e.g., Does the isolated module compile successfully? Does the main project build cleanly?)*

### [ ] Step 3: Implement Initial Tests
*   **Files Modified:** `[List files]`
*   **Actions:** *(e.g., Write the initial test cases for the core modules. Ensure type bindings and data passing are correct.)*
*   **Checkpoint 3:** *(e.g., Do the initial tests pass 100%?)*

### [ ] Step 4: Expand Implementation (Iterative Loop)
*(If applicable, define a loop for implementing multiple similar components.)*
For each remaining component:
1.  **Implementation:** *(Add logic)*
2.  **Build Verification:** *(Run build and resolve errors)*
3.  **Test Implementation:** *(Add corresponding tests)*
4.  **Test Verification:** *(Ensure tests pass)*
*   **Files Modified:** `[List files]`
*   **Checkpoint 4:** *(e.g., After the loop completes, does the full test suite achieve a 100% pass rate?)*

### [ ] Step 5: Refactor Existing Logic
*   **Files Modified:** `[List files]`
*   **Actions:** *(e.g., Replace old scattered logic with the newly implemented modular functions. Ensure naming conventions are protocol/implementation agnostic if necessary. Iteratively build and resolve errors.)*
*   **Checkpoint 5:** *(e.g., Are all old references removed? Does the project compile without warnings/errors?)*

### [ ] Step 6: Final Full Build
*   **Files Modified:** None (Verification only)
*   **Actions:** Run the exact build command from Section 0.
*   **Checkpoint 6:** Does the project compile successfully with no regressions? Verify by outputting the end of the build log.

### [ ] Step 7: Final Run Report
*   **Files Modified:** `.agent/run_reports/YYYYMMDD-<description>-run_report.md` (new)
*   **Actions:** Create a directory for run reports (`mkdir -p .agent/run_reports`). Compile all decisions made, execution statuses of each step, and outcomes of every checkpoint verification into a structured run report. Ensure the report includes an "Epilogue" detailing any post-plan refinements or environment context.
