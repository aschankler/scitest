***********
Data format
***********

Types of files
==============

Query and query set specifications are stored in files named ``query-<tag>.{yml,json}``.
The tags are not used internally, except that discovered query files are sorted by the
tag and loaded in that order.
This allows entries in one file to use types in a previously loaded file.
Test suite definitions are stored in files named ``suite-<suite name>.{yml,json}``.

Finally, test suite results are stored in files named ``{test,ref}-<suite name>-<version>.{yml,json}``.
Test output (i.e. query results from output of the program under test) are prefixed with
``test`` while benchmark data used to validate the test output is prefixed with ``ref``.
The test suite name may not contain the '-' character.
The version is parsed according to their first character.
Currently, those starting with 'v' are expected to be valid semantic versions while
those prefixed with 'd' are treated as ``YYY-MM-DD`` formatted dates.

All files are deserialized to python base types according to the file extension.


Schema definitions
==================

Each file type has own root schema.
Constituent objects (Queries, results, etc.) have their own schema which are listed where relevant.

Query files
-----------

Query files contain definitions of query and query set objects.
They are defined in two sections

.. code-block::
    :name: query-file-schema

    queries:
      - <query def>
      - <query def>
      ...
    query-sets:
      - <query set def>
      - <query set def>
      ...

Query sets are specified according to:

.. code-block::
    :name: query-set-schema

    query-set-name: <query set name>
    queries:
      - <query name>
      - <query name>
      ...

The query names used in the query set must either be present in the file or already
loaded in the program context.
Queries are defined as:

.. code-block::
    :name: query-schema

    query-name: <query name>
    query-type: <QueryType>
    quantity: <serialized quantity>
    properties:
      [search_regex: ".*"]
      [file_ext: dat]
      ...

The query name must be unique in the context that it is loaded in.
Different queries will have different property options to control its behavior.
See the documentation for a query type for the options and requirements.
As queries can be quite similar to one another, an alternative referential form is provided

.. code-block::
    :name: query-extends-schema

    query-name: <query name>
    extends: <existing query>
    with:
      fields:
        to:
          update

In this form, the existing query is used as a template, and the "with" block is traversed
to override or add particular values.
Only queries in the same file can be extended.

Quantities are serialized according to their own schema:

.. code-block::
    :name: quantity-schema

    quantity-type: <QuantityType>
    parameters:
      [width: 6]
      [precision: 8]

Both query and quantity types must have previously been registered into the program
context (either by the library or through the registration API).
Like queries, the fields available to be set in "parameters" vary depending on the type;
see the specific documentation for more information.
As an abbreviated schema, specifying only the quantity type (rather than a mapping) where
a quantity is expected will use the default values for all parameters.


Test files
----------

Test definitions are stored in files of the form

.. code-block::
    :name: test-file-schema

    suite-name: <suite name>
    tests:
    - <test>
    - <test>
    ...

Each test must have a name that is unique within the suite.
Tests themselves are defined as

.. code-block::
    :name: test-schema

    test-name: <test name>
    [prefix: <prefix>]
    args: <program args>
    [base-dir: <base dir>]
    input:
      <dest file>: <src file>
      ...
    queries:
    - <query set name>
    ...

The program args is either a sequence of string args, or a single string (which is split
on whitespace).
Input files is either a sequence of files which are copied into the test directory, or
a map from destination file (in the test directory) to source files (relative to the base
directory).
The base directory is in turn a path relative to the test file.

Query set names must be registered

Result files
------------

Results are stored in a file record of the form:

.. code-block::
    :name: result-file-schema

    suite-name: <test suite name>
    version: <version>
    suite-results:
      <test name>:
        - <result set>
        - <result set>
        - ...
      <test name>: ...
      ...

Though suite name and version information are expected to be in the filename, this form
allows several result sets to be joined in a stream without loss of data.
The query result sets are formatted as

.. code-block::
    :name: result-set-schema

    query-set: <query set name>
    results:
      - <query result>
      - ...

The query results are serialized according to the following schema:

.. code-block::
    :name: query-result-schema

    query-name: <query name>
    result: <serialized result>
    [error: true]

Note that the query name must have been loaded into the program context (likely from file)
previously during the test routine; unrecognized queries are not supported.
The results themselves are serialized according to the quantity definition provided
with the query.
