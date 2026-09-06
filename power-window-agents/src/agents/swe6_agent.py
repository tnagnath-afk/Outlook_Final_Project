import uuid
import json
import os
import re
from google import genai


# -----------------------------
# 1. Gemini client
# -----------------------------
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not set")

client = genai.Client(api_key=api_key)


# -----------------------------
# 2. JSON extraction helper
# -----------------------------
def extract_json(text: str):
    text = text.strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()

    starts = [text.find("["), text.find("{")]
    starts = [s for s in starts if s != -1]
    if starts:
        text = text[min(starts):]

    return json.loads(text)


# -----------------------------
# 3. SWE.6 Test Case Generator (Batch Mode)
# -----------------------------
def generate_test_cases(requirements):
    """
    Batch-generates SWE.6 test cases for all SWE.1 requirements.
    Input: requirements = list of SWE.1 requirement dicts.
    Output: list of SWE.6 test case dicts.
    """

    requirements_json = json.dumps(requirements, indent=2)

    prompt = f"""
You are the SWE.6 Test Case Agent for an automotive Power Window Controller ECU.

You are given a JSON array of SWE.1 requirements.
Each requirement includes:
req_id, category, text, rationale, source_section, trace_source_excerpt,
safety_relevant, asil_suggestion, verification_criteria, grounding_refs, forward_trace.

Your tasks:
1. For EACH requirement, generate one or more SWE.6-compliant test cases.
2. Use concise single-string test steps.
3. Include measurable pass/fail criteria.
4. Specify the test environment (HIL, SIL, MIL, Unit, Integration).
5. Provide backward traceability to the SWE.1 requirement via req_id.
6. Provide forward traceability placeholder for future test reports.

INPUT REQUIREMENTS (JSON):
{requirements_json}

STRICT OUTPUT RULES:
- Output ONLY a JSON array.
- No markdown fences.
- No explanations.
- Each test case MUST include:

tc_id
req_id
title
objective
test_environment
preconditions
test_steps
expected_results
traceability
grounding_refs
forward_trace
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    raw_text = response.text
    parsed = extract_json(raw_text)

    # Normalize structure
    test_cases = []
    for tc in parsed:
        test_case = {
            "tc_id": tc.get("tc_id", f"TC-{uuid.uuid4().hex[:6]}"),
            "req_id": tc["req_id"],
            "title": tc["title"],
            "objective": tc["objective"],
            "test_environment": tc["test_environment"],
            "preconditions": tc["preconditions"],
            "test_steps": tc["test_steps"],
            "expected_results": tc["expected_results"],
            "traceability": tc["traceability"],
            "grounding_refs": tc.get("grounding_refs", []),
            "forward_trace": tc.get("forward_trace", [])
        }
        test_cases.append(test_case)

    return test_cases
