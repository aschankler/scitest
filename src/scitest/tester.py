"""Main entry points to run the test code."""

import sys
from pathlib import Path
from typing import Optional, Sequence, TextIO

from scitest.config import TestConfig
from scitest.fixture import ExeTestFixture
from scitest.io import (
    discover_reference_versions,
    load_queries,
    load_result_data,
    load_test_files,
    write_reference_data,
)
from scitest.print_util import OutputTable, wrap_line
from scitest.query import QueryResult, QuerySetResults
from scitest.suite import TestSuite, TestSuiteResults


def display_query_comparison(test, ref, out_stream=sys.stdout):
    # type: (QueryResult, QueryResult, TextIO) -> None
    """Print the results of a query comparison.

    Args:
        test: The query result under test
        ref: The reference query result
        out_stream: stream where the comparison should be written.

    Example:
        Query_name
        Test result: 1.00
        Reference result: 0.500
        Comparison failed; Absolute error is 0.500
    """
    result_str = "Comparison {}; ".format("succeeded" if test == ref else "failed")
    lines = [
        str(test.query),
        "Test result: " + test.str_long(),
        "Ref. result: " + ref.str_long(),
        result_str + ref.compare_msg(test),
    ]
    for line in lines:
        out_stream.write(wrap_line(line))


def display_test_comparison(test, ref, tst_label="Test", out_stream=sys.stdout):
    # type: (QuerySetResults, QuerySetResults, str, TextIO) -> None
    """Print detailed comparison for each query in a test."""
    _RESULT_WIDTH = 12
    if test.query_set != ref.query_set:
        raise ValueError("Incompatible results sets.")

    fields = (
        ("Query", 16),
        ("Pass?", 6),
        (tst_label, _RESULT_WIDTH),
        ("Ref.", _RESULT_WIDTH),
        ("Result", 28),
    )
    table_writer = OutputTable(fields, out_stream=out_stream)
    table_writer.write_header()
    test_fails = 0

    for query_name in test:
        test_result = test[query_name]
        ref_result = ref[query_name]
        is_pass = ref_result == test_result
        if not is_pass:
            test_fails += 1

        line = (
            query_name,
            "PASS" if is_pass else "FAIL",
            test_result.str_short(max_width=_RESULT_WIDTH),
            ref_result.str_short(max_width=_RESULT_WIDTH),
            ref_result.compare_msg(test_result),
        )
        table_writer.write_row(line)

    table_writer.write_footer()
    if test_fails == 0:
        out_stream.write("All queries passed!\n")
    else:
        out_stream.write("{} of {} queries failed\n".format(test_fails, len(ref)))


# Todo: name fields are redundant
def display_suite_comparison(
    suite_name,
    ref_results,
    tst_results,
    tst_label="TEST",
    verbose=False,
    out_stream=sys.stdout,
):
    # type: (str, TestSuiteResults, TestSuiteResults, str, bool, TextIO) -> None

    def _search_results(
        q_set_name: str, possible_results: Sequence[QuerySetResults]
    ) -> QuerySetResults:
        """Search for results set matching the name."""
        for q_set_res in possible_results:
            if q_set_name == str(q_set_res.query_set):
                return q_set_res
        raise RuntimeError(f"Could not find {q_set_name}")

    # Write suite header
    header_str = "Running test suite: {}".format(suite_name)
    out_stream.write(header_str + "\n")
    out_stream.write("-" * len(header_str) + "\n\n")

    # Set up the table writer
    if not verbose:
        fields = (("Test", 18), ("Pass?", 6), ("Queries", 24))
        table_writer = OutputTable(fields, out_stream=out_stream)
        table_writer.write_header()

    if tst_results.results.keys() != ref_results.results.keys():
        raise RuntimeError("Test and ref results ran different tests")

    # Check results of each test
    failed_tests = 0
    for test_name in ref_results.results:
        if (
            len(ref_results.results[test_name]) < 1
            or len(tst_results.results[test_name]) < 1
        ):
            raise RuntimeError(f"No queries were run in {test_name}")

        # Do comparison
        n_queries = 0
        n_failures = 0  # Number of failed queries in this test
        for ref_query_res in ref_results.results[test_name]:
            tst_query_res = _search_results(
                str(ref_query_res.query_set), tst_results.results[test_name]
            )
            n_queries += len(ref_query_res)
            n_failures += ref_query_res.count_failures(tst_query_res)

            if verbose:
                out_stream.write(
                    f"Test: {test_name}, Query set: {ref_query_res.query_set!s}\n"
                )
                display_test_comparison(
                    tst_query_res,
                    ref_query_res,
                    tst_label=tst_label,
                    out_stream=out_stream,
                )

        n_success = n_queries - n_failures
        if n_failures > 0:
            failed_tests += 1

        # Print output
        if not verbose:
            table_line = (
                test_name,
                "PASS" if n_failures == 0 else "FAIL",
                f"{n_success} of {n_queries} queries passed",
            )
            table_writer.write_row(table_line)
        else:
            out_stream.write(
                f"Test {test_name}: {n_success}/{n_queries} queries passed\n\n"
            )

    if not verbose:
        table_writer.write_footer()

    # Write final suite summary
    if failed_tests > 0:
        out_stream.write(f"{failed_tests}/{len(ref_results.results)} tests failed\n\n")
    else:
        out_stream.write("All tests passed!\n\n")


def display_test_result(
    test_name: str,
    test_results: Sequence[QuerySetResults],
    out_stream: TextIO = sys.stdout,
) -> None:
    """Display verbose output for the results of one test."""
    for q_set_res in test_results:
        out_stream.write(f"Test: {test_name}, Query set: {q_set_res.query_set!s}\n")

        fields = (("Query", 16), ("Result", 32))
        table_writer = OutputTable(fields, out_stream=out_stream)
        table_writer.write_header()

        for query_name in q_set_res:
            query_result = q_set_res[query_name]
            line = (query_name, str(query_result))
            table_writer.write_row(line)

        table_writer.write_footer()
        out_stream.write("\n")


def display_suite_result(
    suite_name, suite_results, verbose=False, out_stream=sys.stdout
):
    # type: (str, TestSuiteResults, bool, TextIO) -> None

    # Write suite header
    header_str = "Running test suite: {}".format(suite_name)
    out_stream.write(header_str + "\n")
    out_stream.write("-" * len(header_str) + "\n\n")

    # Set up the table writer
    if not verbose:
        fields = (("Test", 18), ("Queries", 24))
        table_writer = OutputTable(fields, out_stream=out_stream)
        table_writer.write_header()

    for test_name, test_results in suite_results.results.items():
        if not test_results:
            raise RuntimeError(f"No queries run for {test_name}")

        if verbose:
            display_test_result(test_name, test_results, out_stream=out_stream)
        else:
            num_queries = sum(len(res) for res in test_results)
            table_line = (test_name, f"Ran {num_queries} queries")
            table_writer.write_row(table_line)

    if not verbose:
        table_writer.write_footer()

    out_stream.write(f"Ran {len(suite_results.results)} tests\n\n")


def _run_test_suite(
    suite: TestSuite,
    version: str,
    exe_path: Path,
    *,
    scratch_base: Optional[Path] = None,
) -> TestSuiteResults:
    import shutil
    import tempfile

    # Create temporary scratch dir
    delete_scratch = scratch_base is None
    scratch_dir = Path(tempfile.mkdtemp(prefix=suite.name, dir=scratch_base))

    # Set up common test fixture
    fixture = ExeTestFixture(exe_path, scratch_dir, delete_scratch=delete_scratch)

    # Run the test suite
    suite_results = {}
    for test_name, test in suite.tests.items():
        suite_results[test_name] = test.run_test(fixture)

    # Delete scratch directory if not needed
    if delete_scratch:
        shutil.rmtree(scratch_dir)

    return TestSuiteResults(suite.name, version, suite_results)


def run_bench_mode(conf: TestConfig, verbose: bool = False) -> None:
    from scitest.version import DateVersion

    if conf.exe_path is None:
        raise ValueError

    out_ver = conf.out_ver
    if out_ver is None:
        out_ver = DateVersion.today().stamp

    # Load query sets
    load_queries(conf.query_dirs)

    # Load test suites
    suites = load_test_files(conf.test_dirs, requested_suites=conf.test_suites)

    # Run test suites and print results
    all_results = []
    for suite_name, suite_tests in suites.items():
        suite_results = _run_test_suite(
            suite_tests, out_ver, conf.exe_path, scratch_base=conf.scratch_dir
        )
        display_suite_result(suite_name, suite_results, verbose=verbose)
        all_results.append(suite_results)

    # Print output
    write_reference_data(all_results, conf.bench_out)


def run_test_mode(conf: TestConfig, verbose: bool = False) -> None:
    from scitest.version import DateVersion, get_latest_version

    # Load query sets
    load_queries(conf.query_dirs)

    # Load test suites
    suites = load_test_files(conf.test_dirs, requested_suites=conf.test_suites)

    # Choose ref. version
    ref_ver = conf.ref_ver
    out_ver = conf.out_ver
    if ref_ver is None:
        possible_versions = discover_reference_versions(conf.ref_dirs)
        ref_ver = get_latest_version(possible_versions)
        print("Reference version: {!s}".format(ref_ver))
    if out_ver is None:
        # Use a date version
        out_ver = DateVersion.today().stamp

    # Load benchmarks
    ref_data = load_result_data(conf.ref_dirs, ref_ver, suites=suites)

    # Check that all suites are present in ref. data
    if ref_data.keys() != suites.keys():
        raise RuntimeError("All tests are not present in reference data.")

    all_results = []
    for suite_name, suite_tests in suites.items():
        ref_results = ref_data[suite_name]
        # Run test suite
        suite_results = _run_test_suite(
            suite_tests, out_ver, conf.exe_path, scratch_base=conf.scratch_dir
        )
        all_results.append(suite_results)
        # Write comparison
        display_suite_comparison(
            suite_name, ref_results, suite_results, verbose=verbose
        )

    # Write test results
    write_reference_data(all_results, conf.test_out, test_output=True)


def run_compare_mode(conf: TestConfig, verbose: bool = False) -> None:
    from scitest.io import load_result_data

    # Todo: also both ref and cmp version must be named like ref data. this is surprising
    # TODO: compare mode is likely broken because default queries are never loaded into the resolver
    # Load results for both benchmarks
    ref_data = load_result_data(conf.ref_dirs, conf.ref_ver, suites=conf.test_suites)
    cmp_data = load_result_data(conf.ref_dirs, conf.cmp_ver, suites=conf.test_suites)

    # Check presence of test suites if not specified by user
    if conf.test_suites is None:
        if ref_data.keys() != cmp_data.keys():
            # Do not error, just restrict both to the intersection
            suites = set(ref_data) & set(cmp_data)
            ref_data = {k: ref_data[k] for k in suites}
            cmp_data = {k: cmp_data[k] for k in suites}

    # Print comparisons
    for suite in ref_data:
        display_suite_comparison(
            suite, ref_data[suite], cmp_data[suite], tst_label="COMP", verbose=verbose
        )


def run_clean_mode(conf: TestConfig) -> None:
    tst_dir = conf.test_out
    if tst_dir is None:
        raise RuntimeError("Config not found")
    test_output = tst_dir.glob("tst-*.*.yml")
    for p in test_output:
        p.unlink()
