"""Basic datastructures for single queries on the output of the program under test."""

import enum
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Generic, Iterable, Type, TypeVar

import attrs
import schema

from scitest.exceptions import QueryError, SerializationError
from scitest.query.properties import SchemaType, Serializable, SerializedType
from scitest.query.quantity import QuantityTypeBase, load_quantity

_T = TypeVar("_T")
_ClsT = TypeVar("_ClsT", bound="OutputQueryBase")


QUERY_SCHEMA_KEY = "__query_schema"
QUERY_SERIALIZER_KEY = "__query_serializer"
QUERY_DESERIALIZE_KEY = "__query_deserialize"
QUERY_EXCLUDE_KEY = "__query_exclude"
QUERY_REQUIRED_KEY = "__query_required"


class _UnsetType(enum.Enum):
    """Sentinel for unset required fields."""

    UNSET = enum.auto()

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return "UNSET"

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _UnsetType.UNSET


@attrs.define(order=False, repr=False)
class OutputQueryBase(Serializable, Generic[_T], ABC):
    """Base interface for query on program output.

    .. highlight:: yaml
    Serialization schema::

        query:
            query-name: unique_query_name
            query-type: RegisteredClassName
            quantity:
                <quantity schema ...>
            properties:
                file_ext: dat
                ...

    Attributes:
        query_name: Unique name for the query
        quantity: Interface to represent and compare results produced by the query
        file_ext: If specified, run query on the file "{prefix}.{file_ext}"
    """

    query_name: str = attrs.field(
        validator=attrs.validators.instance_of(str), metadata={QUERY_EXCLUDE_KEY: True}
    )
    quantity: QuantityTypeBase = attrs.field(metadata={QUERY_EXCLUDE_KEY: True})
    file_ext: str = attrs.field(
        default="", kw_only=True, validator=attrs.validators.instance_of(str)
    )

    def __attrs_post_init__(self) -> None:
        for field in attrs.fields(type(self)):
            if (
                QUERY_REQUIRED_KEY in field.metadata
                and field.metadata[QUERY_REQUIRED_KEY]
                and getattr(self, field.name) is UNSET
            ):
                raise ValueError(f"Required field {field.name} unset")

    def __str__(self) -> str:
        return self.query_name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(<{self.query_name}>)"

    def get_query_file(self, prefix: str, scratch_dir: Path) -> Path:
        """Return path to the file that the query should be run on."""
        if not self.file_ext:
            raise QueryError(self.query_name, "Query file extension not provided")
        query_file = scratch_dir.joinpath(prefix + "." + self.file_ext)
        return query_file

    @abstractmethod
    def parse_file(self, lines: Iterable[str]) -> _T:
        """Extract the query result from the program output."""
        raise NotImplementedError

    def run_query(self, prefix: str, scratch_dir: Path) -> _T:
        """Run the query."""
        query_file = self.get_query_file(prefix, scratch_dir)
        if not query_file.is_file():
            raise QueryError(
                self.query_name, f"Query file {query_file.name} does not exist"
            )
        with open(query_file, encoding="utf8") as f_query:
            return self.parse_file(f_query)

    @classmethod
    def get_property_schema(cls, *, strict: bool = False) -> SchemaType:
        """Generate schema for the fields of this type."""

        def _wrap_validator(attr: attrs.Attribute) -> Callable[[Any], bool]:
            # pylint: disable=import-outside-toplevel
            from functools import wraps

            @wraps(attr.validator)
            def _wrapped(value: Any) -> bool:
                try:
                    # Todo: this is a probable bug. Methods need to be explicitly passed
                    #   their instance attribute, but using a plain function as a validator
                    #   would break this
                    attr.validator(attr.validator, attr, value)
                except Exception:
                    return False
                return True

            return _wrapped

        def _value_schema(attr: attrs.Attribute) -> Any:
            if QUERY_SCHEMA_KEY in attr.metadata:
                return attr.metadata[QUERY_SCHEMA_KEY]
            if attr.validator is not None:
                return _wrap_validator(attr)
            return object

        properties = {
            (
                schema.Optional(attr.name)
                if attr.default is not attrs.NOTHING
                else attr.name
            ): _value_schema(attr)
            for attr in attrs.fields(cls)
            if not (
                QUERY_EXCLUDE_KEY in attr.metadata and attr.metadata[QUERY_EXCLUDE_KEY]
            )
        }
        if not strict:
            properties[schema.Optional(str)] = object
        return schema.Schema(properties)

    @classmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return a schema for the serialized query object.

        Serialization schema::

            query:
                query-name: unique_query_name
                query-type: RegisteredClassName
                quantity:
                    <quantity schema ...>
                properties:
                    file_ext: dat
                    ...

        The schema does not specify the form for the quantity object or the properties.
        """
        return schema.Schema(
            {
                "query-name": str,
                "query-type": str,
                "quantity": QuantityTypeBase.get_object_schema(strict=False),
                "properties": cls.get_property_schema() if strict else dict,
            },
            name="Query",
        )

    def serialize(self) -> SerializedType:
        """Encode query according to the object schema."""
        _FilterFunction = Callable[[attrs.Attribute, Any], bool]

        def _not_toplevel(field: attrs.Attribute, value: Any) -> bool:
            """Exclude fields marked to be included at the top schema level."""
            if (
                QUERY_EXCLUDE_KEY in field.metadata
                and field.metadata[QUERY_EXCLUDE_KEY]
            ):
                return False
            return True

        def _is_modified(field: attrs.Attribute, value: Any) -> bool:
            """Check whether a properties value differs from the default."""
            if field.default is not attrs.NOTHING and field.default == value:
                return False
            return True

        def _and_filter(*filters: _FilterFunction) -> _FilterFunction:
            def _composite(field: attrs.Attribute, value: Any) -> bool:
                return all(f(field, value) for f in filters)

            return _composite

        def _serializer(inst: type, field: attrs.Attribute, value: Any) -> Any:
            if inst is None:
                # This occurs when serializer is called on collection or mapping elements
                # rather than a class. Assume that such objects are well-behaved or can
                # be caught at earlier levels of serialization
                return value
            if QUERY_SERIALIZER_KEY in field.metadata:
                return field.metadata[QUERY_SERIALIZER_KEY](value)
            return value

        state = attrs.asdict(
            self,
            filter=_and_filter(_not_toplevel, _is_modified),
            value_serializer=_serializer,
        )
        return {
            "query-name": self.query_name,
            "query-type": self.__class__.__name__,
            "quantity": self.quantity.serialize(),
            "properties": state,
        }

    @classmethod
    def from_serialized(cls: Type[_ClsT], state: SerializedType) -> _ClsT:
        """Construct a new query object out of a serialized representation."""
        # Validate the representation against the object schema
        try:
            parsed = cls.get_object_schema().validate(state)
            params = cls.get_property_schema(strict=True).validate(parsed["properties"])
        except schema.SchemaError as exe:
            raise SerializationError from exe

        # Check object type
        if parsed["query-type"] != cls.__name__:
            raise SerializationError(
                f"Serialized state for {parsed['query-type']} passed to"
                f" {cls.__name__} constructor"
            )
        name = str(parsed["query-name"])
        quantity = load_quantity(parsed["quantity"])

        # Check if any fields need further processing
        for field in attrs.fields(cls):
            if field.name in params and QUERY_DESERIALIZE_KEY in field.metadata:
                _decoder = field.metadata[QUERY_DESERIALIZE_KEY]
                params[field.name] = _decoder(params[field.name])

        return cls(name, quantity, **params)


# Global store of registered query types
_query_type_map: dict[str, type[OutputQueryBase]] = {}


def register_query_type(cls: type[OutputQueryBase]) -> type[OutputQueryBase]:
    """Register a query class globally for use in deserialization."""
    if cls.__name__ not in _query_type_map:
        _query_type_map[cls.__name__] = cls
    return cls


def load_query(state: SerializedType) -> OutputQueryBase:
    """Load a query from serialized state.

    The query must have been registered.
    """
    query_schema = OutputQueryBase.get_object_schema(strict=False)
    try:
        state = query_schema.validate(state)
    except schema.SchemaError as exe:
        raise SerializationError("Malformed query definition") from exe
    try:
        query_cls = _query_type_map[state["query-type"]]
    except KeyError as exe:
        raise SerializationError(f"Unknown query type {state['query-type']}") from exe
    return query_cls.from_serialized(state)


# Store of registered query objects
_query_map: dict[str, OutputQueryBase] = {}


def register_queries(queries: Iterable[OutputQueryBase]) -> None:
    """Register queries with the query resolver.

    Args:
        queries: Query objects to register

    Raises:
        RuntimeError: If a duplicate query name is registered
    """
    for query in queries:
        q_name = query.query_name
        if q_name in _query_map:
            raise RuntimeError(f"Duplicate query {q_name!r} registered.")
        _query_map[q_name] = query


def resolve_query(query_name: str) -> OutputQueryBase:
    """Resolve a query by name.

    Args:
        query_name: Name to resolve

    Returns:
        Query object if the query is registered

    Raises:
        KeyError: If the query is not found
    """
    if query_name not in _query_map:
        raise KeyError(f"Query {query_name!r} not known.")
    return _query_map[query_name]
