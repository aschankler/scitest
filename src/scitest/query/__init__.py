"""Module for performing groups of queries on files."""

from scitest.query.base import (
    OutputQueryBase,
    load_query,
    register_queries,
    register_query_type,
    resolve_query,
)
from scitest.query.common import RegexQuery, TableQuery
from scitest.query.load import load_query_file
from scitest.query.query_set import (
    QuerySet,
    QuerySetResults,
    register_query_sets,
    resolve_query_set,
)
from scitest.query.results import QueryResult
