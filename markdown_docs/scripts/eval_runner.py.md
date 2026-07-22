# scripts/eval/eval_runner.py

The orchestration engine for the Evaluation Harness.

## Overview
`EvalRunner` is responsible for coordinating the evaluation process. It handles the loading of test datasets, the execution of the generation pipeline (either via static captures or live regeneration), and the persistence of results to SQLite.

## Key Features

### Dynamic Regeneration (`--regenerate`)
The runner can now bypass static capture files and generate fresh test code using the live system:
- **`_regenerate_code()`**: Iterates through the golden dataset and calls `TestOrchestrator.run_pipeline()` for each story.
- **RAG Integration**: When `RAG_ENABLED=1` is set in the environment, the regeneration process utilizes the RAG retriever to resolve placeholders, allowing for direct quantitative measurement of RAG's impact.

### Static Validation
When regeneration is disabled, the runner loads pre-generated Python files from the `captures/` directory, providing a fast, offline way to validate the `golden_validator` logic.

### Full Validation Mode (`--full`)
In `full` mode, the runner not only validates locators (static) but also executes the generated tests using `pytest` to measure the actual test pass rate and detect false positives.

## Module Logic Flow
1. **Initialization**: Sets up dataset, capture, and database paths.
2. **Code Acquisition**:
   - If `regenerate=True` $\rightarrow$ Call `_regenerate_code()` $\rightarrow$ Live pipeline run.
   - If `regenerate=False` $\rightarrow$ Call `_load_code_map()` $\rightarrow$ Load from `captures/`.
3. **Validation**:
   - `run_static_validation()`: compares extracted locators against golden keys.
   - `run_generated_tests()`: runs `pytest` on the output.
4. **Persistence**: Writes detailed metrics (accuracy, duration, mode) to the `eval_runs` table in SQLite.

## Integration
- **`TestOrchestrator`**: The primary engine used during regeneration.
- **`golden_validator`**: Used to parse and match the results of both static and regenerated code.
- **`HarnessReport`**: The final aggregated metric object returned by `run()`.
