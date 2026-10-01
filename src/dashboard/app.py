import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(
    page_title="Automotive SWE V-Cycle Assistant",
    page_icon="🚗",
    layout="wide"
)

# -------------------------
# Paths
# -------------------------

REQ_FILE = "data/output/requirements.json"
TC_FILE = "data/output/testcases.json"
VALIDATION_FILE = "data/output/validation_report.json"
TRACE_FILE = "data/output/traceability_matrix.json"
METRICS_FILE = "data/output/metrics.json"

# -------------------------
# Load Helpers
# -------------------------

def load_json(path):

    if os.path.exists(path):

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    return []


requirements = load_json(
    REQ_FILE
)

testcases = load_json(
    TC_FILE
)

validation = load_json(
    VALIDATION_FILE
)

traceability = load_json(
    TRACE_FILE
)

metrics = load_json(
    METRICS_FILE
)

# -------------------------
# Add Review Status
# -------------------------

for req in requirements:

    if "review_status" not in req:

        req["review_status"] = "Pending"

for tc in testcases:

    if "review_status" not in tc:

        tc["review_status"] = "Pending"

# -------------------------
# Save Helpers
# -------------------------

def save_requirements():

    with open(
        REQ_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            requirements,
            f,
            indent=2,
            ensure_ascii=False
        )


def save_testcases():

    with open(
        TC_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            testcases,
            f,
            indent=2,
            ensure_ascii=False
        )


# -------------------------
# Sidebar
# -------------------------

st.sidebar.title("🚗 PWCM AI Assistant")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Requirements",
        "Test Cases",
        "Traceability",
        "Validation",
        "Database View"
    ]
)

# ====================================================
# DASHBOARD
# ====================================================

if page == "Dashboard":

    st.title(
        "🚗 Automotive SWE V-Cycle Dashboard"
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Requirements",
        metrics.get(
            "requirements",
            len(requirements)
        )
    )

    col2.metric(
        "Test Cases",
        metrics.get(
            "testcases",
            len(testcases)
        )
    )

    col3.metric(
        "Coverage %",
        metrics.get(
            "coverage_percent",
            0
        )
    )

    col4.metric(
        "Safety Reqs",
        metrics.get(
            "safety_requirements",
            0
        )
    )

    st.divider()

    st.subheader(
        "Review Progress"
    )

    approved = sum(
        1
        for r in requirements
        if r["review_status"] == "Approved"
    )

    total = len(requirements)

    progress = (
        approved / total
    ) if total > 0 else 0

    st.progress(progress)

    st.write(
        f"{approved}/{total} Approved"
    )

    st.divider()

    if requirements:

        categories = {}

        for req in requirements:

            cat = req.get(
                "category",
                "Unknown"
            )

            categories[cat] = (
                categories.get(cat, 0) + 1
            )

        df = pd.DataFrame(
            {
                "Category": categories.keys(),
                "Count": categories.values()
            }
        )

        st.subheader(
            "Requirements by Category"
        )

        st.bar_chart(
            df.set_index(
                "Category"
            )
        )

# ====================================================
# REQUIREMENTS
# ====================================================

elif page == "Requirements":

    st.title(
        "📄 Requirements Review"
    )

    search = st.text_input(
        "Search Requirement"
    )

    categories = sorted(
        list(
            set(
                [
                    r.get(
                        "category",
                        "Unknown"
                    )
                    for r in requirements
                ]
            )
        )
    )

    selected = st.selectbox(
        "Category",
        ["All"] + categories
    )

    for i, req in enumerate(requirements):

        if (
            search
            and search.lower()
            not in json.dumps(req).lower()
        ):
            continue

        if (
            selected != "All"
            and req.get("category")
            != selected
        ):
            continue

        status = req.get(
            "review_status",
            "Pending"
        )

        status_icon = {
            "Approved": "🟢",
            "Rejected": "🔴",
            "Needs Clarification": "🟡",
            "Pending": "⚪"
        }

        with st.expander(
            f"{status_icon.get(status)} "
            f"{req['req_id']} "
            f"({status})"
        ):

            st.write(
                req.get(
                    "text",
                    ""
                )
            )

            st.write(
                "**Category:**",
                req.get(
                    "category",
                    ""
                )
            )

            st.write(
                "**Source Section:**",
                req.get(
                    "source_section",
                    ""
                )
            )

            st.write(
                "**Verification Criteria:**",
                req.get(
                    "verification_criteria",
                    ""
                )
            )

            col1, col2, col3 = st.columns(3)

            if col1.button(
                "✅ Approve",
                key=f"a_{i}"
            ):

                req[
                    "review_status"
                ] = "Approved"

                save_requirements()

                st.success(
                    "Approved"
                )

            if col2.button(
                "❌ Reject",
                key=f"r_{i}"
            ):

                req[
                    "review_status"
                ] = "Rejected"

                save_requirements()

                st.error(
                    "Rejected"
                )

            if col3.button(
                "🟡 Clarify",
                key=f"c_{i}"
            ):

                req[
                    "review_status"
                ] = (
                    "Needs Clarification"
                )

                save_requirements()

                st.warning(
                    "Needs Clarification"
                )

# ====================================================
# TEST CASES
# ====================================================

elif page == "Test Cases":

    st.title(
        "🧪 Test Cases Review"
    )

    for i, tc in enumerate(testcases):

        status = tc.get(
            "review_status",
            "Pending"
        )

        with st.expander(
            f"{tc['tc_id']} ({status})"
        ):

            st.write(
                "**Requirement:**",
                tc.get(
                    "req_id",
                    ""
                )
            )

            st.write(
                "**Objective:**",
                tc.get(
                    "objective",
                    ""
                )
            )

            st.write(
                "**Expected Result:**",
                tc.get(
                    "expected_result",
                    ""
                )
            )

            col1, col2 = st.columns(2)

            if col1.button(
                "✅ Approve",
                key=f"ta_{i}"
            ):

                tc[
                    "review_status"
                ] = "Approved"

                save_testcases()

                st.success(
                    "Approved"
                )

            if col2.button(
                "❌ Reject",
                key=f"tr_{i}"
            ):

                tc[
                    "review_status"
                ] = "Rejected"

                save_testcases()

                st.error(
                    "Rejected"
                )

# ====================================================
# TRACEABILITY
# ====================================================

elif page == "Traceability":

    st.title(
        "🔗 Traceability Matrix"
    )

    if traceability:

        df = pd.DataFrame(
            traceability
        )

        st.dataframe(
            df,
            use_container_width=True
        )

# ====================================================
# VALIDATION
# ====================================================

elif page == "Validation":

    st.title(
        "✅ Validation Report"
    )

    st.json(
        validation
    )

# ====================================================
# DATABASE VIEW
# ====================================================

elif page == "Database View":

    st.title(
        "🗄 Stored Artifacts"
    )

    st.subheader(
        "Requirements"
    )

    st.dataframe(
        pd.DataFrame(
            requirements
        ),
        use_container_width=True
    )

    st.subheader(
        "Test Cases"
    )

    st.dataframe(
        pd.DataFrame(
            testcases
        ),
        use_container_width=True
    )