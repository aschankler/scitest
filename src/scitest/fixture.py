"""A test fixture runs the program under test and manages queries on the results."""

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import attrs

from scitest.exceptions import QueryError, TestCodeError
from scitest.query import OutputQueryBase, QueryResult


class _PushDir:
    """Context manager to move execution into a new directory.

    Todo: part of std library as of 3.11
    """

    def __init__(self, target):
        # type: (Path) -> None
        self.target_dir = target

    def __enter__(self):
        # type: () -> None
        import os

        self.old_dir = Path.cwd()
        os.chdir(self.target_dir)

    def __exit__(self, exc_type, exc_value, traceback):
        # type: (Any, Any, Any) -> None
        import os

        os.chdir(self.old_dir)


def _concrete_path(path_in: str | Path) -> Path:
    """Converter to ensure all paths are concrete."""
    return Path(path_in).resolve()


@attrs.define(eq=False)
class ExeTestFixture:
    """Test fixture handles setting up and running the program under test.

    Args:
        exe_path: Path to the executable under test
        scratch_dir_base: Directory to run the program in
    """

    exe_path: Path = attrs.field(converter=_concrete_path)
    scratch_dir_base: Path = attrs.field(converter=_concrete_path)

    # Data for the test currently being run
    test_name: str = attrs.field(default="", init=False)
    prefix: str = attrs.field(default="", init=False)
    _exe_args: list[str] = attrs.field(factory=list, init=False)

    # Track state
    setup_run: bool = attrs.field(default=False, init=False)
    exe_run: bool = attrs.field(default=False, init=False)

    def __attrs_post_init__(self) -> None:
        if not self.exe_path.is_file():
            raise TestCodeError(f"Executable {self.exe_path} does not exist")

    @property
    def scratch_dir(self) -> Path:
        """Directory where current test is run."""
        # Note: not well-defined if `not setup_run`
        return self.scratch_dir_base / self.test_name

    @property
    def exe_args(self) -> list[str]:
        """Produce cli arguments to supply to the program under test."""
        return self._exe_args

    @exe_args.setter
    def exe_args(self, args: Sequence[str]) -> None:
        self._exe_args = list(args)

    def generate_program_input(
        self, input_files: Mapping[str, str], *input_args: Any, **input_kw: Any
    ) -> None:
        """Generate input files for the program under test."""
        # Default implementation ignores other config args
        del input_args
        del input_kw

        for in_name, in_data in input_files.items():
            in_path = self.scratch_dir / in_name
            if not in_path.is_relative_to(self.scratch_dir):
                raise TestCodeError(
                    f"Input file {in_name} must be a child of the scratch directory."
                )
            with open(in_path, "w", encoding="utf8") as f_input:
                f_input.write(in_data)

    def setup(
        self,
        test_name: str,
        input_files: Mapping[str, str],
        *,
        prefix: Optional[str] = None,
        exe_args: Optional[Sequence[str]] = None,
        input_args: Optional[Sequence] = None,
        input_kw: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Prepare the scratch directory to run the exe.

        Args:
            test_name: Name for test case to set up
            input_files: mapping from file name to file contents for input files
            prefix: Prefix for the program input/output
            exe_args: Command-line arguments for the exe
            input_args: Passed to `generate_program_input`
            input_kw: Passed to `generate_program_input`
        """
        self.test_name = test_name
        self.prefix = prefix if prefix is not None else test_name

        if exe_args is not None:
            self.exe_args = exe_args

        # Create scratch directory
        self.scratch_dir.mkdir(exist_ok=True)

        # Generate input files
        if input_args is None:
            input_args = []
        if input_kw is None:
            input_kw = {}
        self.generate_program_input(input_files, *input_args, **input_kw)

        # Update state
        self.setup_run = True
        self.exe_run = False

    def run_exe(self):
        # type: () -> None
        """Invoke the program under test. Capture output streams to file."""
        import subprocess

        # Don't run program if input is not set up
        if not self.setup_run:
            raise TestCodeError("Test fixture is not set up.")

        # Run the program
        _args = [str(self.exe_path), *self.exe_args]
        with _PushDir(self.scratch_dir):
            _pout = subprocess.run(
                _args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

        if _pout.returncode != 0:
            raise TestCodeError(
                f"Nonzero exit status ({_pout.returncode}) in test '{self.test_name}'"
            )

        # Write streams to files
        _out_fil = self.scratch_dir.joinpath(self.prefix + ".stdout")
        _err_fil = self.scratch_dir.joinpath(self.prefix + ".stderr")

        with open(_out_fil, "wb") as f:
            f.write(_pout.stdout)

        with open(_err_fil, "wb") as f:
            f.write(_pout.stderr)

        # Update state
        self.exe_run = True

    def cleanup(self) -> None:
        """Remove scratch space after exe run."""
        import shutil

        shutil.rmtree(self.scratch_dir)
        self.test_name = ""
        self.prefix = ""
        self.setup_run = False
        self.exe_run = False

    def run_query(self, query: OutputQueryBase) -> QueryResult:
        """Run a query on the exe output."""
        if not self.exe_run:
            raise RuntimeError("Program was not run; no output to query.")
        try:
            result = query.run_query(self.prefix, self.scratch_dir)
        except QueryError:
            return QueryResult(query, None, error=True)
        return QueryResult(query, result)
