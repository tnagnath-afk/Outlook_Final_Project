from pydantic import BaseModel
from typing import List, Optional

class SpecSection(BaseModel):
    section_id: str
    heading: str
    text: str
    page: Optional[int] = None

class SpecDocument(BaseModel):
    doc_id: str
    source_filename: str
    source_format: str
    title: str
    sections: List[SpecSection]
    ingestion_warnings: List[str] = []

class Requirement(BaseModel):
    req_id: str
    text: str
    rationale: Optional[str] = ""
    source_section: str
    safety_relevant: bool = False
    asil_suggestion: Optional[str] = None
    verification_criteria: Optional[str] = ""
    status: str = "draft"
    is_ambiguous: bool = False
    ambiguity_note: Optional[str] = None
    is_open_point: bool = False
    grounding_refs: List[str] = []

class TestCase(BaseModel):
    test_id: str
    requirement_id: str
    title: str
    technique: str
    preconditions: Optional[str]
    steps: List[str]
    expected_result: str
    status: str = "draft"
    grounding_refs: List[str] = []
