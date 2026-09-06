import uuid
import json
import os
import re
import chromadb
from google import genai


# -----------------------------
# 1. Gemini client with hard fail
# -----------------------------
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY not set — ensure .env exists and load_dotenv() is called in main.py"
    )

client = genai.Client(api_key=api_key)


# -----------------------------
# 2. Chroma client (single instance)
# -----------------------------
chroma_client = chromadb.PersistentClient(path="data/kb")
standards_collection = chroma_client.get_collection("standards")


# -----------------------------
# 3. JSON extraction helper
# -----------------------------
def extract_json(text: str):
    """
    Gemini sometimes returns JSON with markdown fences or leading prose.
    This extracts clean JSON reliably.
    """
    text = text.strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()

    start = min(
        (text.find("["), text.find("{")),
        key=lambda x: x if x != -1 else float("inf")
    )
    if start != float("inf"):
        text = text[start:]

    return json.loads(text)


# -----------------------------
# 4. Retrieval with chunk IDs
# -----------------------------
def get_standard_context(query: str):
    """
    Returns (grounding_text, grounding_ids)
    """
    res = standards_collection.query(query_texts=[query], n_results=5)
    docs = res["documents"][0]
    ids = res["ids"][0]
    return "\n\n".join(docs), ids


# -----------------------------
# 5. SWE.1 generator using Gemini
# -----------------------------
def generate_requirements(spec_sections):
    all_requirements = []

    for section in spec_sections:

        grounding_text, grounding_ids = get_standard_context(
            f"{section.heading}\n{section.text[:500]}"
        )

        prompt = f"""
You are the SWE.1 Requirements Agent.

Specification Section:
ID: {section.section_id}
Heading: {section.heading}
Text:
{section.text}

Grounding (retrieved from ISO 26262 + ASPICE):
{grounding_text}

Task:
Generate atomic, verifiable SWE.1 software requirements.

STRICT OUTPUT RULES:
- Return ONLY a JSON array.
- NO markdown fences.
- NO prose before or after the JSON.
- Each requirement object MUST contain:
    - req_id
    - text
    - rationale
    - safety_relevant
    - asil_suggestion
    - verification_criteria
"""

        response = client.models.generate_content(
            model="gemini-3.6-flash",   # fast + cheap + stable
            contents=prompt
        )

        raw_text = response.text
        parsed = extract_json(raw_text)

        for r in parsed:
            req = {
                "req_id": r.get("req_id", f"SWR-{uuid.uuid4().hex[:6]}"),
                "text": r["text"],
                "rationale": r.get("rationale", ""),
                "source_section": section.section_id,
                "safety_relevant": r.get("safety_relevant", False),
                "asil_suggestion": r.get("asil_suggestion"),
                "verification_criteria": r.get("verification_criteria", ""),
                "status": "draft",
                "grounding_refs": grounding_ids,
            }
            all_requirements.append(req)

    return all_requirements
