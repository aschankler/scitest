"""Datastructures for collections of queries and query results."""

from collections.abc import Collection, Iterable, Iterator, Mapping
from typing import Self

import schema

from scitest.exceptions import SerializationError, TestCodeError, TestFailure
from scitest.query.base import OutputQueryBase, resolve_query
from scitest.query.results import QueryResult
from scitest.serialize import SchemaType, Serializable, SerializedType


class QuerySet(Collection[OutputQueryBase], Serializable):
    """Named collection of query objects."""

    def __init__(
        self, query_set_name: str, queries: Collection[OutputQueryBase]
    ) -> None:
        """Initialize query set.

        Args:
            query_set_name: name of query set
            queries: collection of query instances
        """
        self.query_set_name = query_set_name
        self.queries = queries

    def __str__(self) -> str:
        return self.query_set_name

    def __repr__(self) -> str:
        """Represent query collection."""
        query_name_str = ", ".join(name for name in self.query_names)
        return f"QuerySet({self.query_set_name}, {{{query_name_str}}})"

    @property
    def query_names(self) -> Collection[str]:
        """Names of queries in the query set."""
        return [q.query_name for q in self.queries]

    def __contains__(self, elem: object) -> bool:
        """Check if a query is in the set using query object equality testing."""
        if not isinstance(elem, OutputQueryBase):
            return NotImplemented
        return elem in self.queries

    def __iter__(self) -> Iterator[OutputQueryBase]:
        """Iterate over queries in the set."""
        return iter(self.queries)

    def __len__(self) -> int:
        """Return the number of queries in the set."""
        return len(self.queries)

    def __eq__(self, other: object) -> bool:
        """Check equality of both query set name and contained queries."""
        if not isinstance(other, QuerySet):
            return NotImplemented
        if self.query_set_name != other.query_set_name:
            return False
        if len(self) != len(other):
            return False
        return all(el in other for el in self)

    @classmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return schema for QuerySet.

        Serialization schema::

            query-set:
                query-set-name: unique_name
                queries:
                    - registered_name1
                    - registered_name2
                    ...
        """

        def _duplicate_free(_seq: list) -> bool:
            return len(_seq) == len(set(_seq))

        return schema.Schema(
            {
                "query-set-name": str,
                "queries": schema.And([str], _duplicate_free) if strict else [str],
            }
        )

    def serialize(self) -> SerializedType:
        """Encode the query set according to the schema."""
        return {"query-set-name": self.query_set_name, "queries": self.query_names}

    @classmethod
    def from_serialized(cls, state: SerializedType) -> Self:
        """Construct a query set and resolve referenced queries."""
        try:
            state = cls.get_object_schema().validate(state)
        except schema.SchemaError as exe:
            raise SerializationError("Malformed query set") from exe

        queries = []
        for query_name in state["queries"]:
            try:
                queries.append(resolve_query(query_name))
            except KeyError as exe:
                raise SerializationError(f"Unknown query {query_name!r}") from exe

        return cls(state["query-set-name"], queries)


# Global record of known query set definitions
_query_set_map: dict[str, QuerySet] = {}


def register_query_sets(query_sets: Iterable[QuerySet]) -> None:
    """Register known query sets with the resolver.

    Args:
        query_sets: Query sets to register

    Raises:
        ValueError: If a duplicate name is registered
    """
    for q_set in query_sets:
        name = q_set.query_set_name
        if name in _query_set_map:
            raise ValueError(f"Duplicate query set {name!r} registered.")
        _query_set_map[name] = q_set


def resolve_query_set(query_set_name: str) -> QuerySet:
    """Resolve a query set by name.

    Args:
        query_set_name: Name to resolve

    Returns:
        QuerySet object if the query set is registered

    Raises:
        KeyError: If the query set is not found
    """
    if query_set_name not in _query_set_map:
        raise KeyError(f"Query set {query_set_name!r} not known.")
    return _query_set_map[query_set_name]


class QuerySetResults(Mapping[str, QueryResult], Serializable):
    """Stores a set of query results.

    Args:
        query_set: Query set that produced the results
        results: Query results from each tests
    """

    def __init__(
        self,
        query_set: QuerySet,
        results: Iterable[QueryResult],
    ) -> None:
        self.query_set = query_set
        self.results = {str(res.query): res for res in results}
        if not (
            all(k in query_set for k in self.results.keys())
            and len(self.results) == len(query_set)
        ):
            raise TestCodeError("Query set and results do not match.")

    def __str__(self) -> str:
        return self.query_set.query_set_name

    def __repr__(self) -> str:
        return (
            f"QuerySetResults({str(self)}, <{str(self.query_set)}>, "
            f"<{len(self.results)} results>)"
        )

    def __iter__(self) -> Iterator[str]:
        return iter(self.results)

    def __getitem__(self, item: str) -> QueryResult:
        return self.results[item]

    def __len__(self) -> int:
        return len(self.results)

    def count_errors(self) -> int:
        """Count the number of failed queries."""
        return sum(res.error for res in self.results.values())

    def count_failures(self, other: "QuerySetResults") -> int:
        """Count the comparison failures between two results.

        Args:
            other: Results set to compare against

        Returns:
            Number of comparison failures
        """
        if self.query_set != other.query_set:
            raise TestCodeError("Results sets have incompatible queries.")

        failures = 0
        for query_name in self:
            if self[query_name] != other[query_name]:
                failures += 1
        return failures

    def compare_results(
        self, other: "QuerySetResults", raise_failures: bool = False
    ) -> bool:
        """Compare two sets of results.

        Args:
            other: Results set to compare against
            raise_failures (optional): The first failed comparison raises an exception

        Returns:
            True if all results match, False if not

        Raises:
            TestError: If the result sets are incompatible
            TestFailure: If one of the comparisons fails and `raise_failures` is true
        """
        if self.query_set != other.query_set:
            raise TestCodeError("Results sets have incompatible queries.")

        has_failures = False

        for query_name in self:
            if self[query_name] != other[query_name]:
                has_failures = True
                if raise_failures:
                    raise TestFailure(self[query_name], other[query_name])

        return not has_failures

    @classmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return a schema for the QuerySetResults.

        Serialization schema::

            query-set-results:
              query-set: query_set_name
              results:
                - query-name: ...
                  result: ...
                - query_result
                - query_result
                - ...
        """
        if not strict:
            return schema.Schema(dict, name=cls.__name__)
        return schema.Schema(
            {
                "query-set": str,
                "results": [QueryResult.get_object_schema(strict=False)],
            },
            name=cls.__name__,
        )

    def serialize(self) -> SerializedType:
        """Serialize set of results according to object schema."""
        return {
            "query-set": str(self.query_set),
            "results": [res.serialize() for res in self.results.values()],
        }

    @classmethod
    def from_serialized(cls, state: SerializedType) -> Self:
        """Construct a results set from serialized input."""
        try:
            state = cls.get_object_schema().validate(state)
        except schema.SchemaError as exe:
            raise SerializationError("Malformed result set") from exe
        results = [QueryResult.from_serialized(res) for res in state["results"]]
        try:
            query_set = resolve_query_set(state["query-set"])
        except KeyError as exe:
            raise SerializationError(f"Unknown query set {state['query-set']}") from exe
        return cls(query_set, results)
