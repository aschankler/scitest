"""
Provides an interface to attach validated configuration properties to classes.

Registered properties track when they are modified from defaults, and may be used with
a provided interface to serialize configured objects.
"""

import re
from abc import ABC, abstractmethod
from typing import (
    Any,
    Generic,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    TypeAlias,
    Union,
)

import schema
import strictyaml

_T = TypeVar("_T")
_Number = Union[int, float]
_NT = TypeVar("_NT", bound=_Number)
_ClsT = TypeVar("_ClsT", bound="HasProperties")


class ValidatedProperty(Generic[_T], ABC):
    """Descriptor type to validate input, store defaults, and outline serialization.

    Attributes:
        expected_type: type for the property value
        schema_validator: validator used to serialize/deserialize the property data
        default: default parameter value
    """

    expected_type = object  # type: Union[Type, Tuple[Type, ...]]
    schema_validator = strictyaml.Any()
    default: _T

    _schema_attr = "_prop_schema"
    _mod_attr = "_prop_modified"

    def __init__(
        self, default: Optional[_T] = None, *, required: bool = False, **_
    ) -> None:
        """Create a parameter descriptor.

        Args:
            default: Default parameter value
            required: If parameter is required, raise an error if the value is
                requested when the parameter is unset
        """
        self.required = required
        # Defer check of default value until bound to a class property
        self.default = default  # type: ignore

    def __or__(self, other: object) -> "ValidatedProperty":
        """Join two properties."""
        if not isinstance(other, ValidatedProperty):
            return NotImplemented
        return OrProperty(self, other)

    def __set_name__(self, owner: Type, name: str) -> None:
        """Register property validator with containing class."""
        # pylint: disable=attribute-defined-outside-init
        self.public_name = name
        self.private_name = "_" + name
        # Update the schema
        if hasattr(owner, self._schema_attr):
            schema = getattr(owner, self._schema_attr)
        else:
            schema = {}
        # Re-allocation so that the (mutable) schema is not shared between sibling classes
        key = name if self.required else strictyaml.Optional(name)
        schema = {key: self.schema_validator, **schema}
        setattr(owner, self._schema_attr, schema)

        # If the parameter is optional, check the default value
        # Note: this check is deferred from the init method so that merged properties
        #   are resolved before the check occurs
        if not self.required:
            self.check_type(self.default)
            self.validate(self.default)

    def _check_modified(self, instance: object) -> bool:
        """Check if the property has been set."""
        try:
            mod_dict = getattr(instance, self._mod_attr)
        except AttributeError:
            # Mod. dict is initialized at runtime only after the first property is
            # modified. If dict is absent, then this property is not modified
            return False
        if not isinstance(mod_dict, Mapping):
            raise RuntimeError("Invalid type for modified map.")
        if self.public_name not in mod_dict:
            return False
        return mod_dict[self.public_name]

    def _set_modified(self, instance: object, state: bool) -> None:
        """Mark the property as modified."""
        mod_dict = getattr(instance, self._mod_attr, {})
        if not isinstance(mod_dict, MutableMapping):
            raise RuntimeError("Invalid type for modified map.")
        mod_dict[self.public_name] = state
        setattr(instance, self._mod_attr, mod_dict)

    def __get__(self, instance: object, owner: Type) -> _T:
        """Get the value for the attribute."""
        if not self._check_modified(instance):
            if self.required:
                raise AttributeError(
                    f"Non-optional parameter {self.public_name} is unset"
                )
            return self.default
        if not hasattr(instance, self.private_name):
            raise RuntimeError(f"Value for attribute {self.public_name} not found")
        return getattr(instance, self.private_name)

    def __set__(self, instance: object, value: _T) -> None:
        """Set the attribute value and mark as non-default."""
        self.check_type(value)
        self.validate(value)
        setattr(instance, self.private_name, value)
        self._set_modified(instance, True)

    def __delete__(self, instance: object) -> None:
        """Restore the attribute to the default value."""
        setattr(instance, self.private_name, None)
        self._set_modified(instance, False)

    def check_type(self, value: object) -> None:
        """Verify that the provided value is of the correct type.

        Raises:
            TypeError: If value is of incorrect type
        """
        if not isinstance(value, self.expected_type):
            raise TypeError(
                f"{self.public_name!r}: Expected {self.expected_type!r} got {value!r}"
            )

    @abstractmethod
    def validate(self, value: _T) -> None:
        """Raise error if value is invalid."""
        raise NotImplementedError


class BoolProperty(ValidatedProperty[bool]):
    """Store a boolean configuration property."""

    expected_type = bool
    schema_validator = strictyaml.Bool()

    def validate(self, value: bool) -> None:
        """Accept booleans with no checks."""


class NullProperty(ValidatedProperty[None]):
    """Property storing a null value; useful for combining with other properties."""

    expected_type = type(None)
    schema_validator = strictyaml.NullNone()

    def validate(self, value: None) -> None:
        """Accept null values."""


class NumericProperty(ValidatedProperty[_NT]):
    """Store a property that is a number of arbitrary type."""

    expected_type = (int, float)  # type: Union[Type, Tuple[Type, ...]]
    schema_validator = strictyaml.Int() | strictyaml.Float()

    def __init__(
        self,
        default: Optional[_NT] = None,
        *,
        required: bool = False,
        min_value: Optional[_Number] = None,
        max_value: Optional[_Number] = None,
    ) -> None:
        """Initialize bounds for the numeric property value.

        Arg:
            default: Default value if the property is not set
            required: the property must be set; default value will not be used
            min_value: Minimum allowable value for the property
            max_value: Maximum allowable value for the property
        """
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(default, required=required)

    def validate(self, value: _NT) -> None:
        """Ensure that numeric value is within the acceptable range.

        Raises:
            ValueError: If the value is out of range
        """
        if self.min_value is not None and value < self.min_value:
            raise ValueError(
                f"{self.public_name!r}: Expected {value!r} to be at least {self.min_value!r}"
            )
        if self.max_value is not None and value < self.max_value:
            raise ValueError(
                f"{self.public_name!r}: Expected {value!r} to be at most {self.max_value!r}"
            )


class IntProperty(NumericProperty[int]):
    """Store an integer configuration property."""

    expected_type = int
    schema_validator = strictyaml.Int()


class FloatProperty(NumericProperty[float]):
    """Store a numeric configuration property that is a float."""

    expected_type = float
    schema_validator = strictyaml.Float()


class OptionalNumericProperty(ValidatedProperty[Optional[_NT]]):
    """Store a numeric configuration property where a null value has semantic meaning."""

    expected_type = (type(None), float, int)
    schema_validator = strictyaml.Int() | strictyaml.Float() | strictyaml.NullNone()

    def __init__(
        self,
        default: Optional[_NT] = None,
        *,
        required: bool = False,
        min_value: Optional[_Number] = None,
        max_value: Optional[_Number] = None,
    ) -> None:
        """Initialize bounds for the numeric property value.

        Arg:
            default: Default value if the property is not set
            required: the property must be set; default value will not be used
            min_value: Minimum allowable value for the property
            max_value: Maximum allowable value for the property
        """
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(default, required=required)

    def validate(self, value: Optional[_NT]) -> None:
        """Ensure that numeric value is within the acceptable range.

        Raises:
            ValueError: If the value is out of range
        """
        if value is None:
            # None is always acceptable
            return
        if self.min_value is not None and value < self.min_value:
            raise ValueError(
                f"{self.public_name!r}: Expected {value!r} to be at least {self.min_value!r}"
            )
        if self.max_value is not None and value < self.max_value:
            raise ValueError(
                f"{self.public_name!r}: Expected {value!r} to be at most {self.max_value!r}"
            )


class StringProperty(ValidatedProperty[str]):
    """Store a string configuration property."""

    expected_type = str
    schema_validator = strictyaml.Str()

    def __init__(
        self,
        default: str = "",
        *,
        required: bool = False,
        validate_regex: Optional[str] = None,
    ) -> None:
        """Initialize string property.

        Args:
            default: Default value if the property is not set
            required: the property must be set; default value will not be used
            validate_regex: property value must match this regex
        """
        self.validate_regex = validate_regex
        super().__init__(default, required=required)

    def validate(self, value: str) -> None:
        """Ensure that value matches regex."""
        if self.validate_regex is None:
            return
        if not re.match(self.validate_regex, value):
            raise ValueError(
                f"{self.public_name!r}: Value {value!r} does not match provided regex"
            )


class StringChoicesProperty(ValidatedProperty[str]):
    """Store a property that may take on a limited set of valid choices."""

    expected_type = str
    schema_validator = strictyaml.Str()

    def __init__(
        self,
        default: Optional[str] = None,
        *,
        required: bool = False,
        choices: Iterable[str] = (),
    ) -> None:
        """Initialize the property choices.

        Args:
            default: Default value if the property is not set
            required: the property must be set; default value will not be used
            choices: sequence of valid choices for the property
        """
        # Copy the input
        self.choices = tuple(choices)
        super().__init__(default, required=required)

    def validate(self, value: str) -> None:
        """Ensure that the provided value is one of the allowed choices.

        Raises:
            ValueError: if the value is not one of the provided choices
        """
        if value not in self.choices:
            raise ValueError(
                f"{self.public_name!r}: {value!r} is not a valid choice for this property"
            )


class OrProperty(ValidatedProperty):
    """Merge properties so that either type is acceptable.

    Order is important. The validation methods and schema parsers are evaluated
    from left to right.
    """

    def __init__(self, prop_1: ValidatedProperty, prop_2: ValidatedProperty) -> None:
        """Store properties to merge."""
        # Gather component property objects
        self.sub_properties = []  # type: List[ValidatedProperty]
        if isinstance(prop_1, OrProperty):
            self.sub_properties.extend(prop_1.sub_properties)
        elif isinstance(prop_1, ValidatedProperty):
            self.sub_properties.append(prop_1)
        else:
            raise ValueError(f"{prop_1} is not a property")

        if isinstance(prop_2, OrProperty):
            self.sub_properties.extend(prop_2.sub_properties)
        elif isinstance(prop_2, ValidatedProperty):
            self.sub_properties.append(prop_2)
        else:
            raise ValueError(f"{prop_2} is not a property")

        # Set required status and default value
        default = self.sub_properties[0].default
        required = any(prop.required for prop in self.sub_properties)
        super().__init__(default, required=required)

    @property
    def expected_type(self) -> Tuple[Type, ...]:
        """Join allowable types from constituent properties."""
        valid_types = []  # type: List[Type]
        for prop in self.sub_properties:
            if isinstance(prop.expected_type, tuple):
                valid_types.extend(prop.expected_type)
            else:
                valid_types.append(prop.expected_type)
        return tuple(valid_types)

    @property
    def schema_validator(self) -> strictyaml.Validator:
        """Join schema validators from constituent properties."""
        # pylint: disable=import-outside-toplevel
        from functools import reduce
        from operator import or_

        return reduce(or_, (prop.schema_validator for prop in self.sub_properties))

    def validate(self, value: _T) -> None:
        """Apply the first validator for a property of suitable type."""
        for prop in self.sub_properties:
            if isinstance(value, prop.expected_type):
                prop.validate(value)
                break
        else:
            raise TypeError(
                f"{self.public_name!r}: no property found matching type for {value!r}"
            )


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
    def from_serialized(cls: type[_ClsT], state: SerializedType) -> _ClsT:
        """Construct a new object out of a serialized representation."""
        raise NotImplementedError


class HasProperties:
    """Mixin for a class with configurable properties.

    This class tracks which properties are modified from defaults and defines equality
    and property serialization.
    """

    _prop_schema: Mapping[str, strictyaml.Validator]
    _prop_modified: Mapping[str, bool]

    @property
    def modified_properties(self) -> Sequence[str]:
        """Return parameters that have been modified from their default values."""
        if not hasattr(self, "_prop_modified"):
            return []
        return [k for k, v in self._prop_modified.items() if v]

    def __eq__(self, other: object) -> bool:
        """Assert equality by testing all non-default properties."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        if set(self.modified_properties) != set(other.modified_properties):
            return False
        return all(
            getattr(self, param) == getattr(other, param)
            for param in self.modified_properties
        )

    @classmethod
    def get_property_schema(cls) -> strictyaml.Validator:
        """Return a schema used to validate the serialized object state."""
        return strictyaml.EmptyDict() | strictyaml.Map(cls._prop_schema)

    def serialize_properties(self) -> strictyaml.YAML:
        """Serialize the internal state of the object only.

        At the simplest, the internal state is the registered properties. Only modified
        properties are included in the serialized output.
        """
        return strictyaml.as_document(
            {param: getattr(self, param) for param in self.modified_properties},
            schema=self.get_property_schema(),
        )
