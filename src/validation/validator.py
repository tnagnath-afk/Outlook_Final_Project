import re
from collections import Counter

def validate_requirement_ids(requirements):

    ids = [r["req_id"] for r in requirements]

    duplicates = [
        item
        for item, count in Counter(ids).items()
        if count > 1
    ]

    return {
        "check": "unique_requirement_ids",
        "passed": len(duplicates) == 0,
        "duplicates": duplicates
    }


def validate_testcase_ids(testcases):

    ids = [t["tc_id"] for t in testcases]

    duplicates = [
        item
        for item, count in Counter(ids).items()
        if count > 1
    ]

    return {
        "check": "unique_testcase_ids",
        "passed": len(duplicates) == 0,
        "duplicates": duplicates
    }


def validate_traceability(requirements, testcases):

    req_ids = set(r["req_id"] for r in requirements)

    covered = set()

    orphan_tests = []

    for tc in testcases:

        req_id = tc["req_id"]

        if req_id in req_ids:
            covered.add(req_id)
        else:
            orphan_tests.append(tc["tc_id"])

    orphan_requirements = list(req_ids - covered)

    coverage = round(
        (len(covered) / len(req_ids)) * 100,
        2
    ) if req_ids else 0

    return {
        "coverage_percent": coverage,
        "orphan_requirements": orphan_requirements,
        "orphan_tests": orphan_tests
    }


def validate_tbd_hallucinations(requirements):

    suspicious = []

    keywords = [
        "10 minutes",
        "20 ms",
        "50 ms",
        "15 A"
    ]

    for r in requirements:

        text = r["text"]

        if r["source_section"] == "SEC-5":
            for kw in keywords:
                if kw.lower() in text.lower():
                    suspicious.append(r["req_id"])

    return {
        "check": "review_required",
        "count": len(suspicious),
        "requirements": suspicious
    }


def run_all_validations(
    requirements,
    testcases
):

    return {
        "requirements": validate_requirement_ids(
            requirements
        ),
        "testcases": validate_testcase_ids(
            testcases
        ),
        "traceability": validate_traceability(
            requirements,
            testcases
        ),
        "hallucination_review": validate_tbd_hallucinations(
            requirements
        )
    }