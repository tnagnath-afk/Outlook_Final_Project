import os
import chromadb
from dotenv import load_dotenv

load_dotenv()

# Always resolves relative to CHROMA_DB_DIR / the same default main.py uses —
# run this from the project root so "data/kb" means the same place both times.
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", "data/kb")
client = chromadb.PersistentClient(path=CHROMA_DB_DIR)

try:
    client.delete_collection("standards")
except:
    pass

collection = client.create_collection(
    name="standards",
    metadata={"hnsw:space": "cosine"}
)

docs = [
    "ISO 26262 requires software requirements to be verifiable, traceable, and safety-classified.",
    "ASPICE SWE.1 requires atomic, unambiguous, testable software requirements.",
    "Requirements must include rationale, constraints, and backward traceability to source sections.",
    "Safety requirements must identify hazards, ASIL relevance, and verification criteria.",
]

collection.add(
    documents=docs,
    ids=[f"STD-{i}" for i in range(len(docs))]
)

print("ChromaDB 'standards' collection created successfully.")
