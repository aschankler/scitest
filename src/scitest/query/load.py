"""Interface to load query and query set definitions from file.

Files are expected to follow the schema

queries:
  - <query def>
  - <query def>
  ...
query-sets:
  - <query set def>
  ...
"""

from typing import Any, Mapping, Sequence, TypeAlias

import schema

from scitest.exceptions import SerializationError
from scitest.query.base import OutputQueryBase, load_query, register_queries
from scitest.query.query_set import QuerySet, register_query_sets
from scitest.serialize import SerializedType

# Todo: improve type checking in query dereferencing
_QueryDefT: TypeAlias = dict[str, SerializedType]


def _dereference_query_map(
    init_map: Mapping[str, _QueryDefT]
) -> Mapping[str, _QueryDefT]:
    """Expand queries defined as an extension to another query.

    Effectively adds an alternate query format::

        query-name: unique_name
        extends: base_query_name
        with:
          key1: value
          key2:
            key3: value

    where the original query serialization defined in "base_query_name" is updated with
    entries from the `with` block. Query definitions are updated iteratively, where only
    queries in the un-extended form may be targets of an "extends" directive.
    """
    # pylint: disable=import-outside-toplevel
    from copy import deepcopy

    # Define schemas for queries
    concrete_schema = OutputQueryBase.get_object_schema(strict=False)
    extended_schema = schema.Schema({"query-name": str, "extends": str, "with": dict})

    unprocessed_queries = dict(init_map)  # Queries that still need to be dereferenced
    final_queries: dict[str, _QueryDefT] = {}  # Concrete query definitions

    # Search initial map and extract concrete definitions
    # Iterate over a static list of keys to enable deletion of keys during iteration
    for query_name in list(unprocessed_queries):
        query_def = unprocessed_queries[query_name]
        if concrete_schema.is_valid(query_def):
            # Concrete definition; move to output map
            final_queries[query_name] = query_def
            del unprocessed_queries[query_name]

    # noinspection PyTypeChecker
    def _update_mapping(obj: _QueryDefT, to_update: Mapping[str, Any]) -> None:
        for k, v in to_update.items():
            if isinstance(v, Mapping) and isinstance(obj[k], Mapping):
                _update_mapping(obj[k], v)  # type: ignore
            else:
                obj[k] = v

    def dereference_query(_query_def: _QueryDefT) -> _QueryDefT:
        base_query = deepcopy(final_queries[_query_def["extends"]])  # type: ignore
        # Fix the name
        base_query["query-name"] = _query_def["query-name"]
        _update_mapping(base_query, _query_def["with"])  # type: ignore
        return base_query

    # Try to update referential query definitions
    while unprocessed_queries:
        query_updated = False

        for query_name in list(unprocessed_queries):
            query_def = unprocessed_queries[query_name]
            # Match against the referential query definition
            if not extended_schema.is_valid(query_def):
                raise SerializationError(f"Invalid query definition for {query_name}")

            if query_def["extends"] in final_queries:
                # Dereference query definition
                final_queries[query_name] = dereference_query(query_def)
                query_updated = True
                del unprocessed_queries[query_name]

        if not query_updated:
            raise SerializationError(
                "Some query definitions could not be dereferenced."
                f" Remaining queries: {unprocessed_queries.keys()}"
            )

    return final_queries


def parse_queries(query_block: Sequence[SerializedType]) -> dict[str, OutputQueryBase]:
    """Parse query definitions from file.

    Args:
        query_block: List of serialized queries

    Returns:
        Mapping from query names to query objects

    Raises:
        SerializationError: if any queries could not be successfully loaded
    """
    query_block_schema = schema.Schema([{"query-name": str, str: object}])
    try:
        parsed = query_block_schema.validate(query_block)
    except schema.SchemaError as exe:
        raise SerializationError("Malformed query definition") from exe

    # Construct map from query name to query state
    query_map = {}
    for query_state in parsed:
        query_name = str(query_state["query-name"])
        query_map[query_name] = query_state

    query_map = _dereference_query_map(query_map)
    queries = {
        query_name: load_query(query_state)
        for query_name, query_state in query_map.items()
    }

    return queries


def parse_query_sets(qset_block: Sequence[SerializedType]) -> dict[str, QuerySet]:
    """Parse query set definitions from file.

    Args:
        qset_block: List of serialized query sets

    Returns:
        A map from query set names to fully instantiated query set objects

    Raises:
        SerializationError: if any query sets cannot be loaded
    """
    qset_block_schema = schema.Schema([QuerySet.get_object_schema(strict=False)])
    try:
        parsed = qset_block_schema.validate(qset_block)
    except schema.SchemaError as exe:
        raise SerializationError("Malformed query set definition") from exe

    query_set_map = {}
    for query_set_state in parsed:
        query_set = QuerySet.from_serialized(query_set_state)
        if query_set.query_set_name in query_set_map:
            raise SerializationError(
                f"Query set names should be unique. Duplicate name {query_set.query_set_name!r}"
            )
        query_set_map[query_set.query_set_name] = query_set

    return query_set_map


def load_query_file(
    file_contents: Any,
) -> tuple[dict[str, OutputQueryBase], dict[str, QuerySet]]:
    """Load query and query set definitions from file.

    Deserializes all definitions in a query file. Queries and query sets are registered
    in the execution context. This is necessary in order to load query sets referencing
    queries in the same file.

    Args:
        file_contents: Serialized query definitions read from the file

    Returns:
        Map of query names to decoded query objects and a map of query set names to
        query set objects

    Raises:
        SerializationError: On improperly formatted query files
    """

    def _convert_null(_val: Any) -> list:
        if _val is None:
            return []
        raise schema.SchemaError

    _null_list = schema.Or(list, schema.Use(_convert_null))
    query_file_schema = schema.Schema({"queries": _null_list, "query-sets": _null_list})

    try:
        parsed = query_file_schema.validate(file_contents)
    except schema.SchemaError as exe:
        raise SerializationError("Malformed query file") from exe

    query_map = parse_queries(parsed["queries"])
    register_queries(query_map.values())

    query_set_map = parse_query_sets(parsed["query-sets"])
    register_query_sets(query_set_map.values())

    return query_map, query_set_map
