def generate_traceability_matrix(
    requirements,
    testcases
):

    matrix = []

    for req in requirements:

        linked_tests = [
            tc["tc_id"]
            for tc in testcases
            if tc["req_id"] == req["req_id"]
        ]

        matrix.append(
            {
                "requirement": req["req_id"],
                "tests": linked_tests,
                "covered": len(linked_tests) > 0
            }
        )

    return matrix