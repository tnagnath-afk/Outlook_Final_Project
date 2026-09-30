import uuid
import json
import os
import re
import chromadb
from google import genai


# -----------------------------
# 1. Gemini client
# -----------------------------
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not set")

client = genai.Client(api_key=api_key)


# -----------------------------
# 2. Chroma client
# -----------------------------
chroma_client = chromadb.PersistentClient(path="data/kb")
standards_collection = chroma_client.get_collection("standards")


# -----------------------------
# 3. JSON extraction helper
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
# 4. Retrieval with chunk IDs
# -----------------------------
def get_standard_context(query: str):
    res = standards_collection.query(query_texts=[query], n_results=5)
    docs = res["documents"][0]
    ids = res["ids"][0]
    return "\n\n".join(docs), ids


# -----------------------------
# 5. SWE.1 generator (FINAL VERSION)
# -----------------------------
def generate_requirements(spec_sections):
    all_requirements = []

    for section in spec_sections:

        grounding_text, grounding_ids = get_standard_context(
            f"{section.heading}\n{section.text[:500]}"
        )

        prompt = f"""
You are the SWE.1 Requirements Agent for an automotive Power Window Controller ECU.

Use SYSTEM-CENTRIC requirement grammar:
"The Power Window Controller SHALL <measurable action> WHEN <condition> WITHIN <constraint>."

Specification Section:
ID: {section.section_id}
Heading: {section.heading}
Text:
{section.text}

Grounding:
{grounding_text}

Your tasks:
1. Generate atomic, verifiable SWE.1 requirements.
2. Use strict system-centric grammar.
3. Ensure each requirement is testable and unambiguous.
4. Provide backward traceability (exact phrase from spec).
5. Provide forward traceability placeholder (array).
6. Provide ASIL scoring: ASIL X (Sx, Ex, Cx).
7. Provide concise single-string verification criteria.
8. Categorize each requirement:
   Functional, Safety, Performance, Interface, Diagnostic, FaultHandling.

STRICT OUTPUT RULES:
- Output ONLY a JSON array.
- No markdown fences.
- No explanations.
- Each requirement MUST include:

req_id
category
text
rationale
source_section
trace_source_excerpt
safety_relevant
asil_suggestion
verification_criteria
grounding_refs
forward_trace
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        raw_text = response.text
        parsed = extract_json(raw_text)

        for r in parsed:
            req = {
                "req_id": r.get("req_id", f"SWR-{uuid.uuid4().hex[:6]}"),
                "category": r.get("category", "Functional"),
                "text": r["text"],
                "rationale": r.get("rationale", ""),
                "source_section": r.get("source_section", section.section_id),
                "trace_source_excerpt": r.get("trace_source_excerpt", ""),
                "safety_relevant": r.get("safety_relevant", False),
                "asil_suggestion": r.get("asil_suggestion"),
                "verification_criteria": r.get("verification_criteria", ""),
                "status": "draft",
                "grounding_refs": grounding_ids,
                "forward_trace": r.get("forward_trace", []),
            }
            all_requirements.append(req)

    return all_requirements
