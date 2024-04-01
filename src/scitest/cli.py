"""CLI interface for the test code."""

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from pathlib import Path

from scitest import __version__
from scitest.config import TestConfig
from scitest.tester import (
    run_bench_mode,
    run_clean_mode,
    run_compare_mode,
    run_test_mode,
)

PARSER_FIELDS = (
    "test_dirs",
    "ref_dirs",
    "query_dirs",
    "exe_path",
    "test_out",
    "bench_out",
    "ref_ver",
    "cmp_ver",
    "out_ver",
    "test_suites",
)


def _make_argument_parser() -> ArgumentParser:
    """Build CLI interface."""
    parser = ArgumentParser()
    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {__version__}"
    )

    parser.add_argument("--verbose", "-v", action="count", default=0)

    # Choose run mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--test", const="test", action="store_const", dest="mode")
    mode_group.add_argument(
        "--benchmark", "--bench", const="bench", action="store_const", dest="mode"
    )
    mode_group.add_argument(
        "--compare", const="compare", action="store_const", dest="mode"
    )
    mode_group.add_argument("--clean", const="clean", action="store_const", dest="mode")
    parser.add_argument(
        "--check-config", action="store_true", help="Validate configuration and exit"
    )

    # Where to search for configuration
    parser.add_argument(
        "--config",
        "--conf",
        type=Path,
        dest="config",
        metavar="PATH",
        help="Path to configuration file.",
    )
    parser.add_argument(
        "--exe",
        type=Path,
        dest="exe_path",
        metavar="PATH",
        help="Path to executable to test.",
    )
    parser.add_argument(
        "--add-queries",
        action="append",
        type=Path,
        dest="query_dirs",
        metavar="DIR",
        help="Add directory for query set definitions.",
    )
    parser.add_argument(
        "--add-test-dir",
        action="append",
        type=Path,
        dest="test_dirs",
        metavar="DIR",
        help="Add directory to search for test definitions.",
    )
    parser.add_argument(
        "--add-ref-dir",
        "--ref",
        action="append",
        type=Path,
        dest="ref_dirs",
        metavar="DIR",
        help="Add directory to search for reference data.",
    )

    # Which tests to run
    parser.add_argument(
        "--add-test",
        action="append",
        dest="test_suites",
        metavar="TEST",
        help="Name of test suite to run.",
    )

    # Directories for output
    parser.add_argument(
        "--test-out-dir",
        type=Path,
        dest="test_out",
        metavar="DIR",
        help="Directory to write test output.",
    )
    parser.add_argument(
        "--bench-out-dir",
        type=Path,
        dest="bench_out",
        metavar="DIR",
        help="Directory to write benchmarks.",
    )

    # Configure version stamps
    parser.add_argument(
        "--ref-version",
        dest="ref_ver",
        metavar="VERSION",
        help="Name of benchmark data to compare against.",
    )
    parser.add_argument(
        "--comp-version",
        dest="cmp_ver",
        metavar="VERSION",
        help="Second benchmark to use in compare mode.",
    )
    parser.add_argument(
        "--out-version",
        dest="out_ver",
        metavar="VERSION",
        help="Version for output test/benchmark data.",
    )

    return parser


def parse_args(args: Sequence[str]) -> Namespace:
    """Definition of the testing CLI."""
    parser = _make_argument_parser()

    # Set default options
    parsed = parser.parse_args(args)
    if parsed.mode is None:
        parsed.mode = "test"

    return parsed


def main(argv: Sequence[str]) -> None:
    # Parse arguments
    args = parse_args(argv)

    # Generate configuration
    conf = TestConfig.from_namespace(args, PARSER_FIELDS, root_path=Path.cwd())
    if args.config is not None:
        conf_file = args.config
    elif Path.cwd().joinpath("config.yml").exists():
        conf_file = Path.cwd().joinpath("config.yml")
    else:
        conf_file = None

    if conf_file is not None:
        file_conf = TestConfig.from_file(conf_file)
        file_conf.update(conf)
        conf = file_conf

    is_verbose = args.verbose > 0
    if is_verbose or args.check_config:
        print(str(conf))
    if args.check_config:
        return

    # TODO: -vv option (print out data on each query)
    # TODO: print out relevant version choice at the start of the run

    if args.mode == "test":
        conf.check_fields(
            ("exe_path", "test_out", "test_dirs", "ref_dirs", "query_dirs")
        )
        run_test_mode(conf, verbose=is_verbose)
    elif args.mode == "bench":
        conf.check_fields(("exe_path", "bench_out", "test_dirs", "query_dirs"))
        run_bench_mode(conf, verbose=is_verbose)
    elif args.mode == "compare":
        conf.check_fields(("ref_dirs", "ref_ver", "cmp_ver"))
        run_compare_mode(conf, verbose=is_verbose)
    elif args.mode == "clean":
        conf.check_fields(("test_out",))
        run_clean_mode(conf)
    else:
        raise RuntimeError(f"Unknown mode {args.mode}")
