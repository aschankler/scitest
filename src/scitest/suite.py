"""Classes for individual tests and test suites.

A test is a pairing of program input conditions and queries for the results.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Optional, Self, TypeVar

import attrs
import schema

from scitest.exceptions import SerializationError
from scitest.fixture import ExeTestFixture
from scitest.query import QuerySet, QuerySetResults, resolve_query_set
from scitest.serialize import SchemaType, Serializable, SerializedType

_T = TypeVar("_T")
_ClsT = TypeVar("_ClsT", bound="TestCase")


@attrs.frozen(order=False)
class TestCase(Serializable):
    """A pairing of program input and queries for the output.

    Attributes:
        name: Name for the test case
        prefix: Prefix for naming program output
        input_files: Map from file name to file contents for required input files
        cli_args: Command line arguments to supply to exe
        query_sets: Queries to run on program output
    """

    name: str = attrs.field()
    query_sets: tuple[QuerySet] = attrs.field(converter=tuple)
    input_files: Mapping[str, str] = attrs.field(factory=dict, kw_only=True)
    cli_args: tuple[str] = attrs.field(converter=tuple, factory=tuple, kw_only=True)
    base_dir: Optional[Path] = attrs.field(default=None, kw_only=True)
    prefix: str = attrs.field(kw_only=True)

    @prefix.default
    def _prefix_default(self) -> str:
        return self.name

    def run_query_set(
        self, fixture: ExeTestFixture, query_set: QuerySet
    ) -> QuerySetResults:
        """Run a query set using an initialized fixture."""
        results = []
        for query in query_set:
            res = fixture.run_query(query)
            results.append(res)
        return QuerySetResults(self.name, query_set, results)

    def get_input_file(self, in_path: str) -> str:
        """Read contents of an input file referenced in a test."""
        base_dir = Path.cwd() if self.base_dir is None else self.base_dir
        full_path = base_dir / in_path
        if not full_path.is_relative_to(base_dir):
            raise ValueError("In file must be relative to base directory")
        with open(full_path, encoding="utf8") as src_file:
            return src_file.read()

    def run_test(self, fixture: ExeTestFixture) -> list[QuerySetResults]:
        """Run the test using the provided test fixture."""
        in_files = {
            dest_path: self.get_input_file(src_path)
            for dest_path, src_path in self.input_files.items()
        }
        results = []
        try:
            # Initialize the fixture
            fixture.setup(
                self.name, in_files, prefix=self.prefix, exe_args=self.cli_args
            )
            fixture.run_exe()

            # Use the fixture for each query
            for query_set in self.query_sets:
                results.append(self.run_query_set(fixture, query_set))

        finally:
            fixture.cleanup()
        return results

    @classmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return schema for test definition."""
        if not strict:
            return schema.Schema(dict)
        return schema.Schema(
            {
                "test-name": str,
                schema.Optional("prefix"): str,
                "args": schema.Or(str, [str]),
                schema.Optional("base-dir"): str,
                "input": schema.Or([str], {str: str}),
                "queries": [str],
            }
        )

    def serialize(self) -> SerializedType:
        """Save the test definition to file.

        Note that the file is assumed to be saved in the cwd, so the base directory that
        is searched for linked files is saved relative to the cwd.
        """
        state = {
            "test-name": self.name,
            "prefix": self.prefix,
            "args": self.cli_args,
            "input": self.input_files,
            "queries": [_qset.query_set_name for _qset in self.query_sets],
        }
        if self.base_dir is None or self.base_dir == Path.cwd():
            return state
        try:
            state["base-dir"] = str(self.base_dir.relative_to(Path.cwd()))
        except ValueError as err:
            raise SerializationError from err
        return state

    @classmethod
    def from_serialized(cls: type[_ClsT], state: SerializedType) -> _ClsT:
        """Load a test object from serialized representation.

        Note that the cwd is used, as the base directory is assumed to be relative to
        the cwd.
        """
        try:
            parsed = cls.get_object_schema().validate(state)
        except schema.SchemaError as exe:
            raise SerializationError("Malformed test definition") from exe

        cli_args = parsed["args"]
        if isinstance(cli_args, str):
            cli_args = cli_args.split()

        query_sets = tuple(resolve_query_set(name) for name in parsed["queries"])

        if "base-dir" in parsed:
            base_dir = Path.cwd().joinpath(parsed["base-dir"])
        else:
            base_dir = Path.cwd()
        if not base_dir.is_relative_to(Path.cwd()):
            raise SerializationError("Tests may only search sub-directories.")
        base_dir = base_dir.resolve()

        if isinstance(parsed["input"], Sequence):
            input_files = {f_name: f_name for f_name in parsed["input"]}
        else:
            input_files = parsed["input"]

        return cls(
            name=parsed["test-name"],
            query_sets=query_sets,
            input_files=input_files,
            cli_args=cli_args,
            base_dir=base_dir,
            prefix=parsed["prefix"] if "prefix" in parsed else parsed["test-name"],
        )


@attrs.frozen(order=False)
class TestSuite(Serializable):
    """Collection of test objects grouped into a test suite.

    Attributes:
        name: Test suite name
        tests: Map of test name to test object
    """

    name: str
    tests: Mapping[str, TestCase]

    @classmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return schema for test suite."""
        return schema.Schema(
            {"suite-name": str, "tests": [TestCase.get_object_schema(strict=False)]},
            name=cls.__name__,
        )

    def serialize(self) -> SerializedType:
        """Serialize test suite to python types."""
        return {
            "suite-name": self.name,
            "tests": [test.serialize() for test in self.tests.values()],
        }

    @classmethod
    def from_serialized(cls, state: SerializedType) -> Self:
        """Load test suite definitions from serialized form.

        Note that test definitions can make use of the CWD to resolve relative paths.
        """
        try:
            parsed = cls.get_object_schema().validate(state)
        except schema.SchemaError as exe:
            raise SerializationError("Malformed test file") from exe
        tests = [TestCase.from_serialized(_test_rep) for _test_rep in parsed["tests"]]
        return cls(parsed["suite-name"], {test.name: test for test in tests})


@attrs.frozen(order=False)
class TestSuiteResults(Serializable):
    """Results for a test suite.

    Attributes:
        suite_name: Name of the test suite producing the results
        version: Code version used to generate result
        results: Map from test name to test results
    """

    suite_name: str
    version: str
    results: Mapping[str, Sequence[QuerySetResults]]

    @classmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return schema for test suite results."""
        if not strict:
            return schema.Schema(dict, name=cls.__name__)
        return schema.Schema(
            {
                "suite-name": str,
                "version": str,
                "suite-results": {
                    str: [QuerySetResults.get_object_schema(strict=False)]
                },
            },
            name=cls.__name__,
        )

    def serialize(self) -> SerializedType:
        """Serialize test suite results to python types."""
        results = {
            test_name: [_res.serialize() for _res in test_res]
            for test_name, test_res in self.results.items()
        }
        return {
            "suite-name": self.suite_name,
            "version": self.version,
            "suite-results": results,
        }

    @classmethod
    def from_serialized(cls, state: SerializedType) -> Self:
        """Load test suite results from a serialized format.

        File schema::

            suite-name: <test suite name>
            version: <version>
            suite-results:
              <test name>:
                - <result set>
                - <result set>
                - ...
              <test name>: ...
              ...
        """
        try:
            parsed = cls.get_object_schema().validate(state)
        except schema.SchemaError as exe:
            raise SerializationError("Malformed result file") from exe

        def _deserialize_test_results(_results: list) -> list[QuerySetResults]:
            return [
                QuerySetResults.from_serialized(_qset_res) for _qset_res in _results
            ]

        return cls(
            parsed["suite-name"],
            parsed["version"],
            {
                str(test_name): _deserialize_test_results(results)
                for test_name, results in parsed["suite-results"].items()
            },
        )
