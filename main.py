import json
import os
from dotenv import load_dotenv

load_dotenv()

# ----------------------------------
# Core Pipeline
# ----------------------------------

from src.ingestion.ingest import parse_spec

from src.agents.swe1_agent import generate_requirements
from src.agents.swe6_agent import generate_test_cases

# ----------------------------------
# Validation
# ----------------------------------

from src.validation.validator import (
    run_all_validations
)

# ----------------------------------
# Persistence
# ----------------------------------

from src.persistence.sqlite_store import (
    init_db,
    save_requirements,
    save_testcases
)

# ----------------------------------
# Traceability
# ----------------------------------

from src.traceability.matrix import (
    generate_traceability_matrix
)

# ----------------------------------
# Metrics
# ----------------------------------

from src.metrics.metrics import (
    calculate_metrics
)

# ----------------------------------
# Paths
# ----------------------------------

SPEC_PATH = (
    "data/specs/"
    "PWCM-SPEC-001_PowerWindowController.docx"
)

OUTPUT_DIR = "data/output"

REQ_OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "requirements.json"
)

TC_OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "testcases.json"
)

VALIDATION_OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "validation_report.json"
)

TRACEABILITY_OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "traceability_matrix.json"
)

METRICS_OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "metrics.json"
)

# ----------------------------------
# Ensure folders exist
# ----------------------------------

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)

os.makedirs(
    "data/db",
    exist_ok=True
)

# ----------------------------------
# STEP 0
# Initialize SQLite
# ----------------------------------

print("\nInitializing SQLite database...")

init_db()

# ----------------------------------
# STEP 1
# Parse OEM Specification
# ----------------------------------

print("\nParsing Specification...")

spec = parse_spec(SPEC_PATH)

print(
    f"Parsed {len(spec.sections)} section(s)"
)

for warning in spec.ingestion_warnings:
    print(
        f"[INGEST WARNING] {warning}"
    )

# ----------------------------------
# STEP 2
# Generate SWE.1 Requirements
# ----------------------------------

print(
    "\nGenerating SWE.1 Requirements..."
)

requirements = generate_requirements(
    spec.sections
)

print(
    f"Generated {len(requirements)} requirements"
)

with open(
    REQ_OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        requirements,
        f,
        indent=2,
        ensure_ascii=False
    )

# ----------------------------------
# STEP 3
# Generate SWE.6 Test Cases
# ----------------------------------

print(
    "\nGenerating SWE.6 Test Cases..."
)

test_cases = generate_test_cases(
    requirements
)

print(
    f"Generated {len(test_cases)} test cases"
)

with open(
    TC_OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        test_cases,
        f,
        indent=2,
        ensure_ascii=False
    )

# ----------------------------------
# STEP 4
# Store in SQLite
# ----------------------------------

print(
    "\nSaving to SQLite..."
)

save_requirements(
    requirements
)

save_testcases(
    test_cases
)

# ----------------------------------
# STEP 5
# Validation
# ----------------------------------

print(
    "\nRunning Validators..."
)

validation_report = run_all_validations(
    requirements,
    test_cases
)

with open(
    VALIDATION_OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        validation_report,
        f,
        indent=2,
        ensure_ascii=False
    )

print(
    "Validation Complete"
)

# ----------------------------------
# STEP 6
# Traceability Matrix
# ----------------------------------

print(
    "\nBuilding Traceability Matrix..."
)

traceability_matrix = (
    generate_traceability_matrix(
        requirements,
        test_cases
    )
)

with open(
    TRACEABILITY_OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        traceability_matrix,
        f,
        indent=2,
        ensure_ascii=False
    )

print(
    f"Traceability Entries: "
    f"{len(traceability_matrix)}"
)

# ----------------------------------
# STEP 7
# Metrics / Dashboard Data
# ----------------------------------

print(
    "\nCalculating Metrics..."
)

metrics = calculate_metrics(
    requirements,
    test_cases,
    validation_report
)

with open(
    METRICS_OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        metrics,
        f,
        indent=2,
        ensure_ascii=False
    )

# ----------------------------------
# Console Summary
# ----------------------------------

print("\n==============================")
print("PIPELINE SUMMARY")
print("==============================")

print(
    f"Requirements : "
    f"{metrics['requirements']}"
)

print(
    f"Test Cases   : "
    f"{metrics['testcases']}"
)

print(
    f"Coverage %   : "
    f"{metrics['coverage_percent']}"
)

print(
    f"Safety Reqs  : "
    f"{metrics['safety_requirements']}"
)

print(
    "\nOutputs:"
)

print(
    f"  {REQ_OUTPUT_PATH}"
)

print(
    f"  {TC_OUTPUT_PATH}"
)

print(
    f"  {VALIDATION_OUTPUT_PATH}"
)

print(
    f"  {TRACEABILITY_OUTPUT_PATH}"
)

print(
    f"  {METRICS_OUTPUT_PATH}"
)

print(
    "\nPipeline Execution Complete"
)