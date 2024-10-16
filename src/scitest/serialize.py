"""Provides an interface to attach validated configuration properties to classes.

The interface separates serialization from validation. The schema type validates
the serialized representation using the `SchemaType.validate` method.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, Self, TypeAlias

import schema

SchemaType: TypeAlias = schema.Schema
SerializedType: TypeAlias = int | float | None | str | Sequence | Mapping[str, Any]


class Serializable(ABC):
    """Interface definition for a serializable object."""

    @classmethod
    @abstractmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return a schema for the full serialized object.

        This schema does not validate object state.
        """
        raise NotImplementedError

    @abstractmethod
    def serialize(self) -> SerializedType:
        """Encode the object instance in a standard format."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_serialized(cls, state: SerializedType) -> Self:
        """Construct a new object out of a serialized representation.

        Args:
            state: serialized object state in pure python types

        Returns:
            Constructed object instance restored from serialized state

        Raises:
            ValueError: if a valid schema is used to create an object with invalid
                arguments to the constructor
            SerializationError: if the serialized representation cannot be used to
                construct an object
        """
        raise NotImplementedError
