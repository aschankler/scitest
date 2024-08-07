"""Methods to write and load test objects from file.

Naming conventions:
    query: An atomic query run on exe output. Has an arbitrary result.
    query set: A group of queries run on the output of a single exe run.
    input conditions: The input provided to the exe.
    test: Pairing of conditions with one or more query sets.
    test suite: Set of many tests

File structure:
    Queries and query sets: Specifications stored in files `query-<tag>.{yml,json}`.
        Any queries used in query sets must already be registered with the resolver
    Test suites: Named test cases are grouped in files `suite-<suite name>.yml`. Param
        files must be in the same directory as the test suite.
    Benchmarks: Benchmark results are stored in files `ref-<suite name>-<version>.yml`
        with results from one test suite per file.
"""

import json
from pathlib import Path
from typing import (
    Any,
    Collection,
    Container,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    TypeVar,
)

import yaml

from scitest.exceptions import SerializationError, TestCodeError
from scitest.query import load_query_file
from scitest.suite import (
    TestSuite,
    TestSuiteResults,
    load_result_file,
    load_suite_file,
    serialize_result_file,
)

_T = TypeVar("_T")


def _exclusive_merge(_d1: Mapping[str, _T], _d2: Mapping[str, _T]) -> Mapping[str, _T]:
    """Merge two dicts, raising an error if they share a key."""
    # Check for duplicate keys
    if any(k in _d1 for k in _d2):
        raise KeyError("Duplicate keys")
    return {**_d1, **_d2}


def _load_serialized_file(file_path: Path) -> Any:
    """Deserialize a file based on its extension."""
    file_type = file_path.suffix
    with open(file_path, encoding="utf8") as fh:
        file_contents = fh.read()

    if file_type in (".yml", ".yaml"):
        try:
            parsed = yaml.safe_load(file_contents)
        except yaml.YAMLError as exe:
            raise SerializationError(
                f"Could not parse file {file_path.name} as yaml"
            ) from exe
    elif file_type == ".json":
        try:
            parsed = json.loads(file_contents)
        except json.JSONDecodeError as exe:
            raise SerializationError(
                f"Could not parse file {file_path.name} as json"
            ) from exe
    else:
        raise ValueError(f"Unrecognized file type {file_type}")

    return parsed


def _write_serialized_file(file_path: Path, file_data: Any) -> None:
    """Serialize a file based on its extension."""
    file_type = file_path.suffix

    if file_type in (".yml", ".yaml"):
        try:
            serialized = yaml.safe_dump(file_data)
        except yaml.YAMLError as exe:
            raise SerializationError(
                f"Could not serialize {file_path.name} as yaml"
            ) from exe
    elif file_type == ".json":
        try:
            serialized = json.dumps(file_data)
        except TypeError as exe:
            raise SerializationError(
                f"Could not serialize file {file_path.name} as json"
            ) from exe
    else:
        raise ValueError(f"Unrecognized file type {file_type}")

    with open(file_path, "w", encoding="utf8") as f_out:
        f_out.write(serialized)


# ----------------------------------------------------------------------------
# Load query definitions
# ----------------------------------------------------------------------------


def discover_query_files(search_dirs: Iterable[Path]) -> Sequence[Path]:
    """Discover and sort query definition files by name.

    Files must match `query-<tag>.{yml,json}`; results are sorted by tag

    Args:
        search_dirs: Directories to search for matching files

    Returns:
        Files matching the pattern sorted by tag
    """
    # pylint: disable=import-outside-toplevel
    from itertools import chain

    def _get_tag(_path: Path) -> str:
        return _path.stem.split("-", maxsplit=1)[-1]

    sorted_paths = sorted(
        (_get_tag(p), p)
        for p in chain.from_iterable(
            chain(search_dir.glob("query-*.yml"), search_dir.glob("query-*.json"))
            for search_dir in search_dirs
        )
    )

    return [p for _, p in sorted_paths]


def load_queries(query_dirs: Iterable[Path]) -> None:
    """Load query definitions from a directory.

    Loads query definitions, registers queries with the resolver, and loads query sets.

    Args:
        query_dirs: Directories to search for query and query set definitions

    Raises:
        SerializationError: If files are not properly formed
    """
    for query_file in discover_query_files(query_dirs):
        file_data = _load_serialized_file(query_file)
        load_query_file(file_data)


# ----------------------------------------------------------------------------
# Test suite file interface
# ----------------------------------------------------------------------------


def discover_test_files(
    search_dir: Path, allowed_suites: Optional[Container[str]] = None
) -> dict[str, Path]:
    """Discover test suite definition files in a directory.

    Suite definitions must be named `suite-*.{yml,json}`

    Args:
        search_dir: Directory to search for tests
        allowed_suites: Names of test suites to load

    Returns:
        Map from test suite name to the path to the test definition file
    """
    # pylint: disable=import-outside-toplevel
    from itertools import chain

    def _get_suite_name(_path: Path) -> str:
        _, name = _path.stem.split("-", maxsplit=1)
        return name

    test_suites = {
        _get_suite_name(suite_path): suite_path
        for suite_path in chain(
            search_dir.glob("suite-*.yml"), search_dir.glob("suite-*.json")
        )
    }
    if allowed_suites is None:
        # No restrictions on tests to load
        return test_suites
    else:
        return {n: p for n, p in test_suites.items() if n in allowed_suites}


def _load_test_dir(
    search_dir: Path,
    suite_request: Optional[Collection[str]] = None,
    recursive: bool = True,
) -> dict[str, TestSuite]:
    # pylint: disable=import-outside-toplevel
    from contextlib import chdir

    # Load tests
    test_suites = {}

    with chdir(search_dir):
        test_files = discover_test_files(Path.cwd(), allowed_suites=suite_request)
        for suite_name, suite_path in test_files.items():
            parsed = _load_serialized_file(suite_path)
            test_suites[suite_name] = load_suite_file(parsed)

    # Load tests from subdirectories
    if recursive:
        for sub_dir in (p for p in search_dir.glob("*") if p.is_dir()):
            subdir_tests = _load_test_dir(sub_dir, suite_request=suite_request)
            test_suites = _exclusive_merge(test_suites, subdir_tests)

    return test_suites


def load_test_files(
    search_dirs: Iterable[Path],
    requested_suites: Optional[Collection[str]] = None,
) -> dict[str, TestSuite]:
    """Load test suite definitions from save files.

    Args:
        search_dirs: Paths to search for test definitions
        requested_suites: Names of test suites to load

    Returns:
        Mapping of test suite names to groups of instantiated test cases

    Raises:
        SerializationError: if malformed test definition is encountered
    """
    test_suites = {}
    for test_dir in search_dirs:
        dir_tests = _load_test_dir(test_dir, suite_request=requested_suites)
        test_suites = _exclusive_merge(test_suites, dir_tests)

    # Check that all requested suites were found
    if requested_suites is not None:
        if set(requested_suites) != set(test_suites.keys()):
            missing = set(requested_suites) - set(test_suites.keys())
            raise TestCodeError("Requested were not found: " + ", ".join(missing))

    return test_suites


# ----------------------------------------------------------------------------
# Result data file interface
# ----------------------------------------------------------------------------


def discover_result_files(
    search_dirs: Iterable[Path], *, with_test_output: bool = False
) -> list[tuple[str, str, Path]]:
    """Discover files containing test results.

    Discover files named as `{test,ref}-<suite name>-<version>.{yml,json}`

    Args:
        search_dirs: Directories to search for result files
        with_test_output: Return test output files in addition to reference data files

    Returns:
        A list of the suite name, version, and path for properly named result files
    """
    # pylint: disable=import-outside-toplevel
    from itertools import chain

    def _find_paths(tag: str) -> Iterable[Path]:
        return chain.from_iterable(
            chain(search_dir.glob(f"{tag}-*-*.yml"), search_dir.glob(f"{tag}-*-*.json"))
            for search_dir in search_dirs
        )

    result_paths = _find_paths("ref")
    if with_test_output:
        result_paths = chain(result_paths, _find_paths("test"))

    def _get_result_name(_res_path: Path) -> tuple[str, str, Path]:
        _, _tag = _res_path.stem.split("-", maxsplit=1)
        name, ver = _tag.rsplit("-", maxsplit=1)
        return name, ver, _res_path

    return [_get_result_name(p) for p in result_paths]


def discover_reference_versions(search_dirs: Iterable[Path]) -> set[str]:
    """List the versions available in the reference directories."""
    return {ver for _, ver, _ in discover_result_files(search_dirs)}


def select_result_data(
    search_dirs: Iterable[Path],
    version: str,
    *,
    suites: Optional[Collection[str]] = None,
    with_test_output: bool = False,
) -> dict[str, Path]:
    """Find files containing reference data. Name format: `ref-<suite>.<version>.yml`.

    Args:
        search_dirs: Directories to search for test output
        version: Find reference data for this version
        suites: Return results only for these test suites
        with_test_output: Search test output files in addition to benchmark files

    Returns:
        Paths to reference data indexed by suite name

    Raises:
        TestCodeError: If requested suites were not found
    """
    result_files = discover_result_files(search_dirs, with_test_output=with_test_output)
    labeled_paths = {suite: path for suite, ver, path in result_files if ver == version}

    # Filter output by test suite
    if suites is not None:
        labeled_paths = {k: p for k, p in labeled_paths.items() if k in suites}
        if set(labeled_paths.keys()) != set(suites):
            raise TestCodeError("Suites were not found for version ")

    return labeled_paths


def load_result_data(
    search_dirs: Iterable[Path],
    version: str,
    suites: Optional[Collection[str]] = None,
    *,
    with_test_output: bool = False,
) -> dict[str, TestSuiteResults]:
    """Load test suite results from a single version.

    Args:
        search_dirs: Directories to search for results
        version: Load data from this version
        suites: Only load data from these test suites
        with_test_output: Load saved by test output, rather than just benchmark output

    Returns:
        Map from suite names to results for each version

    Raises:
        TestCodeError: If requested data could not be loaded
    """
    to_load = select_result_data(
        search_dirs, version, suites=suites, with_test_output=with_test_output
    )

    if len(to_load) == 0:
        raise TestCodeError("No ref. data found for " + version)

    def _load_one_reference(ref_path: Path) -> TestSuiteResults:
        """Load results for a single test suite."""
        _, path_name, path_ver = ref_path.stem.split("-", maxsplit=2)
        parsed = _load_serialized_file(ref_path)
        suite_results = load_result_file(parsed)
        assert path_name == suite_results.suite_name
        assert path_ver == suite_results.version
        return suite_results

    return {suite: _load_one_reference(path) for suite, path in to_load.items()}


def write_reference_data(
    ref_data: Sequence[TestSuiteResults],
    out_dir: Path,
    *,
    test_output: bool = False,
    file_type: str = "yml",
) -> None:
    """Write test results to file.

    Args:
        ref_data: Result objects to write
        out_dir: Directory to write data to
        test_output: Written data is test output, not benchmark output
        file_type: Serialization format for output file
    """
    if not out_dir.exists():
        out_dir.mkdir(parents=True)
    elif not out_dir.is_dir():
        raise RuntimeError("File blocking output")

    for result in ref_data:
        out_type = "ref" if not test_output else "test"
        out_path = (
            out_dir / f"{out_type}-{result.suite_name}-{result.version}.{file_type}"
        )
        out_data = serialize_result_file(result)
        _write_serialized_file(out_path, out_data)
