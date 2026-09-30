def calculate_metrics(
    requirements,
    testcases,
    validation
):

    total_requirements = len(requirements)

    total_testcases = len(testcases)

    coverage = validation[
        "traceability"
    ]["coverage_percent"]

    safety = sum(
        1
        for r in requirements
        if r["safety_relevant"]
    )

    return {
        "requirements": total_requirements,
        "testcases": total_testcases,
        "coverage_percent": coverage,
        "safety_requirements": safety
    }