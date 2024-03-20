"""CLI interface for the test code."""

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from pathlib import Path

from scitest.config import TestConfig
from scitest.tester import (
    run_bench_mode,
    run_clean_mode,
    run_compare_mode,
    run_test_mode,
)


def parse_args(args: Sequence[str]) -> Namespace:
    """Definition of the testing CLI."""
    parser = ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true")

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

    # Where to search for configuration
    test_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--config",
        "--conf",
        type=Path,
        default=test_dir.joinpath("config.yml"),
        dest="config",
        metavar="PATH",
        help="Path to config file.",
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
        dest="query_files",
        metavar="PATH",
        help="Query set definitions.",
    )
    parser.add_argument(
        "--add-test-dir",
        action="append",
        type=Path,
        dest="test_dirs",
        metavar="DIR",
        help="Directory to search for test definitions.",
    )
    parser.add_argument(
        "--add-ref-dir",
        "--ref",
        action="append",
        type=Path,
        dest="ref_dirs",
        metavar="DIR",
        help="Directory to search for reference data.",
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
        "--test-out",
        type=Path,
        dest="test_out",
        metavar="DIR",
        help="Directory to write test output.",
    )
    parser.add_argument(
        "--bench-out",
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

    # Set default options
    args = parser.parse_args(args)
    if args.mode is None:
        args.mode = "test"

    return args


def main(args: Sequence[str]) -> None:
    # Parse arguments
    args = parse_args(args)

    # Generate configuration
    conf = TestConfig.from_namespace(args)
    if args.config is not None:
        file_conf = TestConfig.from_file(args.config)
        file_conf.update(conf)
        conf = file_conf

    # TODO: better print of configuration (maybe an option to print and exit)
    print(repr(conf))

    # TODO: -vv option (print out data on each query)
    # TODO: print out relevant version choice at the start of the run

    if args.mode == "test":
        conf.check_fields(
            ("exe_path", "test_out", "test_dirs", "ref_dirs", "query_dirs")
        )
        run_test_mode(conf, verbose=args.verbose)
    elif args.mode == "bench":
        conf.check_fields(("exe_path", "bench_out", "test_dirs", "query_dirs"))
        run_bench_mode(conf, verbose=args.verbose)
    elif args.mode == "compare":
        conf.check_fields(("ref_dirs", "ref_ver", "cmp_ver"))
        run_compare_mode(conf, verbose=args.verbose)
    elif args.mode == "clean":
        conf.check_fields(("test_out",))
        run_clean_mode(conf)
    else:
        raise RuntimeError("Unknown mode {}".format(args.mode))
