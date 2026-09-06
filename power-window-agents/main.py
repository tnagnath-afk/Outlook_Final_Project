import json
import os

from dotenv import load_dotenv
load_dotenv()   

from src.ingestion.ingest import parse_spec
from src.agents.swe1_agent import generate_requirements
from src.agents.swe6_agent import generate_test_cases   # <-- ADD THIS

SPEC_PATH = "data/specs/PWCM-SPEC-001_PowerWindowController.docx"
REQ_OUTPUT_PATH = "data/output/requirements.json"
TC_OUTPUT_PATH = "data/output/testcases.json"           # <-- ADD THIS

# STEP 1: Parse specification
spec = parse_spec(SPEC_PATH)
print(f"Parsed {len(spec.sections)} section(s) from {SPEC_PATH}")
for warning in spec.ingestion_warnings:
    print(f"[INGEST WARNING] {warning}")

# STEP 2: Generate SWE.1 requirements
requirements = generate_requirements(spec.sections)

# os.makedirs(os.path.dirname(REQ_OUTPUT_PATH), exist_ok=True)
# with open(REQ_OUTPUT_PATH, "w", encoding="utf-8") as f:
#     json.dump(requirements, f, indent=2)

# # print(f"\nGenerated {len(requirements)} requirement(s) -> {REQ_OUTPUT_PATH}\n")
# # for r in requirements:
# #     print(f"{r['req_id']} ({r['source_section']}) - {r['text']}")

# STEP 3: Generate SWE.6 test cases
test_cases = generate_test_cases(requirements)

os.makedirs(os.path.dirname(TC_OUTPUT_PATH), exist_ok=True)
with open(TC_OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(test_cases, f, indent=2)

# print(f"\nGenerated {len(test_cases)} test case(s) -> {TC_OUTPUT_PATH}\n")
# for tc in test_cases:
#     print(f"{tc['tc_id']} (REQ: {tc['req_id']}) - {tc['title']}")
