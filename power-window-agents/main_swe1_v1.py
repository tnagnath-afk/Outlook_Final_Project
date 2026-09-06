import json
import os

from dotenv import load_dotenv
load_dotenv()   

from src.ingestion.ingest import parse_spec
from src.agents.swe1_agent import generate_requirements

SPEC_PATH = "data/specs/PWCM-SPEC-001_PowerWindowController.docx"
OUTPUT_PATH = "data/output/requirements.json"

spec = parse_spec(SPEC_PATH)
print(f"Parsed {len(spec.sections)} section(s) from {SPEC_PATH}")
for warning in spec.ingestion_warnings:
    print(f"[INGEST WARNING] {warning}")

requirements = generate_requirements(spec.sections)

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(requirements, f, indent=2)

print(f"\nGenerated {len(requirements)} requirement(s) -> {OUTPUT_PATH}\n")
for r in requirements:
    flag = ""
    if r["is_ambiguous"]:
        flag += " [AMBIGUOUS]"
    if r["is_open_point"]:
        flag += " [OPEN POINT]"
    print(f"{r['req_id']} ({r['source_section']}){flag} - {r['text']}")
