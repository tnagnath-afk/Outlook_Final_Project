import streamlit as st
import json

st.title(
    "Automotive SWE V-Cycle Assistant"
)

with open(
    "data/output/metrics.json"
) as f:

    metrics = json.load(f)

st.metric(
    "Requirements",
    metrics["requirements"]
)

st.metric(
    "Test Cases",
    metrics["testcases"]
)

st.metric(
    "Coverage %",
    metrics["coverage_percent"]
)

st.metric(
    "Safety Requirements",
    metrics["safety_requirements"]
)

st.divider()

st.header(
    "Validation Report"
)

with open(
    "data/output/validation_report.json"
) as f:

    report = json.load(f)

st.json(report)

st.divider()

st.header(
    "Requirements Review"
)

with open(
    "data/output/requirements.json"
) as f:

    requirements = json.load(f)

for req in requirements[:10]:

    st.subheader(req["req_id"])

    st.write(req["text"])

    st.write(
        "Section:",
        req["source_section"]
    )

    st.button(
        f"Approve {req['req_id']}"
    )