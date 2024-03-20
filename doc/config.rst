*************
Configuration
*************

Module behavior is determined by configurations that may be set in a
configuration file and can be updated through the CLI. The config file is
in the YAML format. Note that if a field is specified multiple times, only
the last occurrence is recorded.
Values set to the null value ("null" in YAML) are left unset

exe_path
    Path to the program under test


Test search directories
-----------------------

Several directories are searched for files that describe the testing protocol. Each field
may contain a list of directories to search. Results from all directories are used, but
the directories may not contain conflicting definitions.
Relative paths are interpreted to be relative to the directory containing the
configuration file.

query_dirs
    List of directories that are searched for query definitions
    (``query-*.yml``)

test_dirs
    Paths to be searched for test suite definitions (``suite-*.yml``)

ref_dirs
    Paths searched for reference benchmarks


Output directories
------------------

Records of test runs are recorded in the specified directories. Results are overwritten
if a record with the same version already exists.
Relative paths are interpreted to be relative to the directory containing the
configuration file.

test_out
    Test results are written to this directory

bench_out
    Directory where benchmark results are written


Test selection
--------------

test_suites
    If provided, only these test suites are used

ref_ver
    Version used as a reference

cmp_ver
    Compare this version against the reference

out_ver
    Version used when writing result output
