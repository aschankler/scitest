"""Datastructure to store query output."""

import enum
from typing import Generic, Optional, Self, TypeVar

import schema

from scitest.exceptions import SerializationError, TestCodeError
from scitest.query.base import OutputQueryBase, resolve_query
from scitest.serialize import SchemaType, Serializable, SerializedType

_T = TypeVar("_T")


class _TestError(enum.Enum):
    """Placeholder for the result of errored tests."""

    ERROR = enum.auto()

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        """Always evaluate to false; an error is never equivalent to another."""
        return False

    def __str__(self) -> str:
        return "ERROR"

    def __repr__(self) -> str:
        return "ERROR"


# Placeholder for the result of errored tests
ERROR = _TestError.ERROR


class QueryResult(Serializable, Generic[_T]):
    """Stores the result of a query and a pointer to the query definition.

    Representation and equality tests are implemented with calls to
    class methods of the query class.

    Attributes:
        query: Class of query that was executed
        result: Value produced by the query
        error: indicates whether the query encountered an error
    """

    def __init__(
        self, query: OutputQueryBase[_T], result: _T, error: bool = False
    ) -> None:
        self.query = query
        self.result = result
        self.quantity = query.quantity
        self.error = error
        # Discard value in the case of an error
        if self.error:
            self.result = ERROR

    def __str__(self) -> str:
        return self.str_short()

    def str_short(self, *, max_width: Optional[int] = None) -> str:
        """Print the result in a limited width."""
        if self.error:
            return str(self.result)
        return self.quantity.str_short(self.result, max_width=max_width)

    def str_long(self) -> str:
        """Print the full result. Can be multiline."""
        if self.error:
            return str(self.result)
        return self.quantity.str_long(self.result)

    def __repr__(self) -> str:
        if self.error:
            return f"{self.__class__.__name__}(query={self.query!r}, result=ERROR, error=True)"
        res = self.quantity.repr_quantity(self.result)
        return f"{self.__class__.__name__}(query={self.query!r}, result={res})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QueryResult):
            return NotImplemented
        try:
            return self.compare(other)
        except TestCodeError:
            return False

    def compare(self, other: "QueryResult") -> bool:
        """Test if two query results are equal.

        Raises:
            TestCodeError: If the results are from incompatible queries
        """
        if self.query != other.query:
            raise TestCodeError(
                f"Invalid comparison: {self.query!r} and {other.query!r}"
            )
        if self.error or other.error:
            return False
        return self.quantity.compare(self.result, other.result)

    def compare_msg(self, other: "QueryResult") -> str:
        """Verbose result comparison.

        Raises:
            TestCodeError: If the results are from incompatible queries
        """
        if self.query != other.query:
            raise TestCodeError(
                f"Invalid comparison: {self.query!r} and {other.query!r}"
            )
        if self.error or other.error:
            return "At least one query resulted in an error"
        return self.quantity.compare_msg(self.result, other.result)

    @classmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return a schema for the serialized result object.

        Serialization schema::

            query-result:
              query-name: registered_name
              result: value
              [error: true]
        """
        return schema.Schema(
            {
                "query-name": str,
                "result": object,
                schema.Optional("error"): bool,
            }
        )

    def serialize(self) -> SerializedType:
        """Serialize the query result according to the schema."""
        state = {"query-name": str(self.query)}
        if self.error:
            state["result"] = repr(self.result)
            state["error"] = True
        else:
            state["result"] = self.quantity.repr_quantity(self.result)

        return state

    @classmethod
    def from_serialized(cls, state: SerializedType) -> Self:
        """Load result object from serialized state."""
        try:
            state = cls.get_object_schema().validate(state)
        except schema.SchemaError as exe:
            raise SerializationError from exe
        query = resolve_query(str(state["query-name"]))
        if "error" in state and state["error"]:
            # Note: we discard any value stored in "result" here
            return cls(query, ERROR, error=True)
        result = query.quantity.deserialize_quantity(state["result"])
        return cls(query, result)
