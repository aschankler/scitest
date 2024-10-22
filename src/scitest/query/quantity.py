"""Methods to represent and compare the results extracted by output queries.

Quantity objects encapsulate these methods. A quantity object may be serialized through
the following schema::

quantity:
  quantity-type: RegisteredType
  parameters:
    width: 6
    precision: 8

This would then be deserialized as `RegisteredType(width=6, precision=8)`

An abbreviated format is also allowed::

quantity: RegisteredType

which is deserialized as `RegisteredType()`
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from operator import methodcaller
from typing import Any, Callable, Generic, Optional, Self, TypeVar

import attrs
import attrs.validators as attrsv
import schema

from scitest.exceptions import SerializationError
from scitest.serialize import SchemaType, Serializable, SerializedType

_KT = TypeVar("_KT")
_T = TypeVar("_T")
_WT = TypeVar("_WT")


# Keys to supply additional metadata to the attrs fields
QUANTITY_SCHEMA_KEY: str = "__quantity_schema"
QUANTITY_SERIALIZER_KEY: str = "__quantity_serializer"
QUANTITY_DESERIALIZE_KEY: str = "__quantity_deserialize"


@attrs.define(order=False)
class QuantityTypeBase(Serializable, Generic[_T], ABC):
    """Base interface used to interact with results extracted by queries.

    Attributes:
        width: Maximum width for the short string representation
    """

    width: int = attrs.field(
        default=16,
        kw_only=True,
        validator=[attrsv.ge(1), attrsv.instance_of(int)],
    )

    # ----------------------------------------------------------------
    # Methods relating to the quantities extracted by queries
    # ----------------------------------------------------------------

    @abstractmethod
    def str_short(self, value: _T, max_width: Optional[int] = None) -> str:
        """Print a short representation of a query result for use in a table."""
        raise NotImplementedError

    @abstractmethod
    def str_long(self, value: _T) -> str:
        """Print a detailed representation of a query result."""
        raise NotImplementedError

    def repr_quantity(self, value: _T) -> SerializedType:
        """Represent a query result for serialization."""
        return value

    def deserialize_quantity(self, state: SerializedType) -> _T:
        """Reconstruct value based on serialized data."""
        return state

    @abstractmethod
    def compare(self, ref: _T, test: _T) -> bool:
        """Test if two query results are equal."""
        raise NotImplementedError

    @abstractmethod
    def compare_msg(self, ref: _T, test: _T) -> str:
        """Explain comparison of query results."""
        raise NotImplementedError

    # ----------------------------------------------------------------
    # Methods relating to the underlying quantity class
    # ----------------------------------------------------------------

    @classmethod
    def get_property_schema(cls, *, strict: bool = False) -> SchemaType:
        """Return schema for the properties for this specific type."""

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
            if QUANTITY_SCHEMA_KEY in attr.metadata:
                return attr.metadata[QUANTITY_SCHEMA_KEY]
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
        }
        if not strict:
            properties[schema.Optional(str)] = object
        return schema.Schema(properties)

    @classmethod
    def get_full_quantity_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return the unabbreviated schema for the quantity class."""
        return schema.Schema(
            {
                "quantity-type": str,
                "parameters": cls.get_property_schema() if strict else dict,
            }
        )

    @classmethod
    def get_object_schema(cls, *, strict: bool = True) -> SchemaType:
        """Return a schema for the quantity class.

        Both full and abbreviated forms are acceptable.
        """
        return schema.Schema(
            schema.Or(cls.get_full_quantity_schema(strict=strict), schema.Schema(str)),
            name="Quantity",
        )

    def serialize(self) -> SerializedType:
        """Encode quantity object according to the schema."""

        def _is_modified(attr: attrs.Attribute, value: Any) -> bool:
            """Check whether a properties value differs from the default."""
            if attr.default is not attrs.NOTHING and attr.default == value:
                return False
            return True

        def _serializer(inst: type, field: attrs.Attribute, value: Any) -> Any:
            if inst is None:
                # This occurs when serializer is called on collection or mapping elements
                # rather than a class. Assume that such objects are well-behaved or can
                # be caught at earlier levels of serialization
                return value
            if QUANTITY_SERIALIZER_KEY in field.metadata:
                return field.metadata[QUANTITY_SERIALIZER_KEY](value)
            return value

        state = attrs.asdict(self, filter=_is_modified, value_serializer=_serializer)
        if state:
            # Use standard quantity schema
            return {"quantity-type": self.__class__.__name__, "parameters": state}
        # Use abbreviated schema
        return self.__class__.__name__

    @classmethod
    def type_from_serialized(cls, serialized: SerializedType) -> str:
        """Extract the quantity type from a serialized representation."""
        # Use abbreviated format
        if schema.Schema(str).is_valid(serialized):
            return str(serialized)
        try:
            # Use the full format
            parsed = cls.get_object_schema().validate(serialized)
        except schema.SchemaError as exe:
            raise SerializationError from exe
        return parsed["quantity-type"]

    @classmethod
    def from_serialized(cls, state: SerializedType) -> Self:
        """Construct a new object out of a serialized representation."""
        # Try using abbreviated schema
        if schema.Schema(str).is_valid(state):
            cls_name = state
            params = {}
        else:
            # Use the full schema
            try:
                parsed = cls.get_object_schema().validate(state)
                params = cls.get_property_schema(strict=True).validate(
                    parsed["parameters"]
                )
            except schema.SchemaError as exe:
                raise SerializationError from exe
            cls_name = parsed["quantity-type"]
        # Check type identity
        if cls_name != cls.__name__:
            raise SerializationError(
                f"Serialized state for {cls_name} passed to {cls.__name__} constructor"
            )
        # Check if any fields need further processing
        for field in attrs.fields(cls):
            if field.alias in params and QUANTITY_DESERIALIZE_KEY in field.metadata:
                _decoder = field.metadata[QUANTITY_DESERIALIZE_KEY]
                params[field.alias] = _decoder(params[field.alias])
        # Construct the object
        return cls(**params)


# Global store of allowed quantity types. Used to resolve classes during deserialization
_quantity_type_map: dict[str, type[QuantityTypeBase]] = {}


def register_quantity_type(cls: type[QuantityTypeBase]) -> type[QuantityTypeBase]:
    """Register a quantity class in a global type map.

    Registering the class allows serialization and deserialization methods to work
    correctly. This function may be used as a decorator.

    Args:
        cls: quantity class to register

    Raises:
        ValueError: if a quantity type of the same name is already registered.
    """
    if cls.__name__ in _quantity_type_map:
        raise ValueError(f"Duplicate quantity type {cls.__name__}")
    _quantity_type_map[cls.__name__] = cls
    return cls


def load_quantity(state: SerializedType) -> QuantityTypeBase:
    """Load a quantity from a serialized state.

    The quantity type must have been previously registered.

    Raises:
        SerializationError: if a valid quantity cannot be constructed
    """
    type_name = QuantityTypeBase.type_from_serialized(state)
    try:
        qty_cls = _quantity_type_map[type_name]
    except KeyError as exe:
        raise SerializationError(
            f"Could not load quantity. Unknown type {type_name}"
        ) from exe
    try:
        return qty_cls.from_serialized(state)
    except ValueError as exe:
        raise SerializationError from exe


@attrs.define(order=False)
class QuantityWrapper(QuantityTypeBase[_WT], Generic[_WT, _T], ABC):
    """Base class for wrappers to add functionality to existing quantities.

    Attributes:
        wrapped_quantity: Constructed quantity object to wrap
        width: Maximum width used for short printing of numbers
    """

    wrapped_quantity: QuantityTypeBase[_T] = attrs.field(
        metadata={
            QUANTITY_SERIALIZER_KEY: methodcaller("serialize"),
            QUANTITY_DESERIALIZE_KEY: load_quantity,
        },
    )


@register_quantity_type
class OptionalQuantity(QuantityWrapper[Optional[_T], _T], Generic[_T]):
    """Wrapper for quantities that may contain a null value."""

    def str_short(self, value: Optional[_T], max_width: Optional[int] = None) -> str:
        """Print null values as dashes."""
        if max_width is None:
            max_width = self.width
        if value is None:
            return "-" * min(max_width, 4)
        return self.wrapped_quantity.str_short(value, max_width)

    def str_long(self, value: Optional[_T]) -> str:
        """Represent value as a string."""
        if value is None:
            return "null"
        return self.wrapped_quantity.str_long(value)

    def repr_quantity(self, value: Optional[_T]) -> SerializedType:
        """Encode null values before passing to wrapped repr."""
        if value is None:
            # None should be a serializable type
            return None
        return self.wrapped_quantity.repr_quantity(value)

    def deserialize_quantity(self, state: SerializedType) -> Optional[_T]:
        """Try to construct a null value before passing to the wrapped constructor."""
        if state is None:
            return None
        return self.wrapped_quantity.deserialize_quantity(state)

    def compare(self, ref: Optional[_T], test: Optional[_T]) -> bool:
        """Check for null values before passing to wrapped compare."""
        if ref is None or test is None:
            return ref is None and test is None
        return self.wrapped_quantity.compare(ref, test)

    def compare_msg(self, ref: Optional[_T], test: Optional[_T]) -> str:
        """Note comparisons containing null values."""
        if ref is None or test is None:
            if ref is None and test is None:
                return "Values match"
            if ref is None:
                return f"Expected null value, got {test!r}"
            if test is None:
                return f"Expected {ref!r}, got null value"
        return self.wrapped_quantity.compare_msg(ref, test)


@register_quantity_type
@attrs.define(order=False)
class BoolQuantity(QuantityTypeBase[bool]):
    """Formatting and comparison for boolean quantities."""

    def str_short(self, value: bool, max_width: Optional[int] = None) -> str:
        """Return single letter codes if space constraints require."""
        if max_width is None:
            max_width = self.width
        if max_width < 5:
            return "T" if value else "F"
        return str(value)

    def str_long(self, value: bool) -> str:
        """Apply standard string representation."""
        return str(value)

    def compare(self, ref: bool, test: bool) -> bool:
        """Compare truth values directly."""
        return ref == test

    def compare_msg(self, ref: bool, test: bool) -> str:
        """Print expected values if inconsistent."""
        if self.compare(ref, test):
            return "Values are consistent"
        return f"Expected {ref!r} got {test!r}"


@register_quantity_type
@attrs.define(order=False)
class IntegerQuantity(QuantityTypeBase[int]):
    """Formatting and comparison for integer quantities.

    Attributes:
        abs_tol: Absolute tolerance for comparisons
        rel_tol: Relative tolerance for comparisons
        width: Maximum width used for short printing of numbers
    """

    abs_tol: Optional[int] = attrs.field(
        default=None,
        kw_only=True,
        validator=attrsv.optional([attrsv.instance_of(int), attrsv.ge(0)]),
    )
    rel_tol: Optional[float] = attrs.field(
        default=None,
        kw_only=True,
        validator=attrsv.optional([attrsv.instance_of(float), attrsv.ge(0)]),
    )

    def str_short(self, value: int, max_width: Optional[int] = None) -> str:
        """Print integer within a maximum length."""
        if max_width is None:
            max_width = self.width
        fmt = f"{value:d}"
        if len(fmt) < max_width:
            return fmt
        return "#" * max_width

    def str_long(self, value: int) -> str:
        """Print as a normal integer."""
        return f"{value:d}"

    def compare(self, ref: int, test: int) -> bool:
        """Compare integers, optionally using approximate equality."""
        # Check exact equality
        if test == ref:
            return True
        if self.rel_tol is None and self.abs_tol is None:
            return False
        # Check approx. equality
        diff = abs(ref - test)
        if self.abs_tol is not None and diff > self.abs_tol:
            return False
        if self.rel_tol is not None and diff > self.rel_tol * ref:
            return False
        return True

    def compare_msg(self, ref: int, test: int) -> str:
        """Print the absolute error."""
        if self.compare(ref, test):
            return "Values are consistent"
        return f"Abs. error = {ref - test:d}"


@register_quantity_type
@attrs.define(order=False)
class FloatQuantity(QuantityTypeBase[float]):
    """Inexact formatting and comparison for floating point quantities.

    Attributes:
        abs_tol: Absolute tolerance for comparisons
        rel_tol: Relative tolerance for comparisons
        precision: Desired precision used for printing
        width: Maximum width used for short printing of numbers
        signed: Print an empty leading character for positive values
        allow_exp: Allow short printing to use scientific notation
        zero_pad: Short printing is padded with zeros to exact width
    """

    abs_tol: float = attrs.field(
        default=1e-4, validator=[attrsv.instance_of(float), attrsv.ge(0)]
    )
    rel_tol: float = attrs.field(
        default=0.0, validator=[attrsv.instance_of(float), attrsv.ge(0.0)]
    )
    precision: int = attrs.field(
        default=6,
        kw_only=True,
        validator=(attrsv.instance_of(int), attrsv.ge(0)),
    )
    signed: bool = attrs.field(
        default=False, kw_only=True, validator=attrsv.instance_of(bool)
    )
    allow_exp: bool = attrs.field(
        default=True, kw_only=True, validator=attrsv.instance_of(bool)
    )
    zero_pad: bool = attrs.field(
        default=False, kw_only=True, validator=attrsv.instance_of(bool)
    )

    @staticmethod
    def as_fixed_precision(value: float, precision: int) -> str:
        """Format ``value`` as a float with ``precision`` digits after the decimal."""
        if precision < 0:
            raise ValueError("Negative precision")
        return f"{value:#.{precision}f}"

    @staticmethod
    def as_fixed_width(
        value: float,
        width: int,
        precision: Optional[int] = None,
        *,
        signed: bool = False,
        allow_exp: bool = True,
        zero_pad: bool = True,
    ) -> str:
        """Format float to fill exactly `width` characters.

        Args:
            value: Number to format
            width: Exact length of the formatted string
            precision: Minimum number of digits after the decimal point. The formatted value
                will always have at least `precision + 1` significant digits.
            signed: Always reserve an extra leading character, even if a negative sign
                is not needed
            allow_exp: Disable printing in exponential form
            zero_pad: pad with leading zeros to exactly fill width

        Returns:
            Formatted value with width `width`

        Raises:
            ValueError: If the value cannot be accurately represented in fewer than
                `width` characters
        """
        # pylint: disable=import-outside-toplevel
        from decimal import Decimal

        def _float_decimal_exp(number: float) -> int:
            """Compute the decimal part of the float in base 10.

            Returns:
                Exponent *e* such that::
                    number = m * (10 ** e)

            Refs:
                https://stackoverflow.com/a/45359185
            """
            (_, digits, _exp) = Decimal(number).as_tuple()
            return len(digits) + _exp - 1

        def _float_decimal_man(number: float) -> Decimal:
            """Compute the mantissa of the float in base 10.

            Returns:
                Mantissa *m* such that::
                    number = m * (10 ** e)
            """
            return Decimal(number).scaleb(-_float_decimal_exp(number)).normalize()

        if precision is not None and precision < 0:
            raise ValueError("Negative precision")
        if width < 1:
            raise ValueError("Width too small")
        mantissa = float(_float_decimal_man(value))
        exponent = _float_decimal_exp(value)

        # Width for the trailing 'eNN' string
        exp_suffix_width = 2 + _float_decimal_exp(exponent)
        if exponent < 0:
            exp_suffix_width += 1

        # Minimum width for a float number to give the correct "scale"
        # E.g. 12 -> 2, 1 -> 1, 0.001 -> 5
        if exponent >= 0:
            min_float_width = 1 + exponent
        else:
            min_float_width = 2 + abs(exponent)

        def _format_float(_value: float, _width: int, _units_width: int) -> str:
            sign_char = " " if signed else "-"
            if signed or _value < 0:
                _units_width += 1
            if _width == _units_width:
                # No space for decimals
                if precision is not None and precision != 0:
                    raise ValueError("Width too small for desired precision")
                return f"{_value:{sign_char}.0f}"
            max_precision = _width - _units_width - 1
            tgt_precision = precision if precision is not None else max_precision
            if max_precision < tgt_precision:
                raise ValueError("Width too small for desired precision")
            return f"{_value:{sign_char}#{'0' if zero_pad else ''}{_width}.{tgt_precision}f}"

        # Choose between float or exp form by whichever allows more significant digits
        if 1 + exp_suffix_width < min_float_width and allow_exp:
            # Use exp form
            if exp_suffix_width + 1 > width:
                # Width too small for exponential form
                if exponent < 0:
                    # Print as rounded zero
                    return _format_float(0.0, width, 1)
                raise ValueError("Width to small to accurately represent value")
            fmt_man = _format_float(mantissa, width - exp_suffix_width, 1)
            return f"{fmt_man:s}e{exponent:d}"
        else:
            # Format as float
            if exponent < 0:
                # Value is < 1; therefore it can always be formatted (by rounding to 0/1)
                return _format_float(value, width, 1)
            if width < min_float_width:
                raise ValueError("Width too small to accurately represent value")
            return _format_float(value, width, min_float_width)

    def str_short(self, value: float, max_width: Optional[int] = None) -> str:
        """Format float to fit in the desired width."""
        if max_width is None:
            max_width = self.width
        return self.as_fixed_width(
            value,
            width=max_width,
            precision=self.precision,
            signed=self.signed,
            allow_exp=self.allow_exp,
            zero_pad=self.zero_pad,
        )

    def str_long(self, value: float) -> str:
        """Format float with the desired precision."""
        return self.as_fixed_precision(value, self.precision)

    def compare(self, ref: float, test: float) -> bool:
        """Compare floats, considering both absolute and relative tolerance.

        Like :py:mod:`numpy.isclose`. Not symmetric in arguments. This form expects the
        value to conform to both the absolute and relative tolerances (in comparison
        with the `math` builtin, which only requires one of the tolerances to hold).
        """
        tol = self.abs_tol + self.rel_tol * abs(ref)
        return abs(ref - test) <= tol

    def compare_msg(self, ref: float, test: float) -> str:
        """Display the error between two numeric results."""
        return f"Abs. error {self.as_fixed_precision(test - ref, self.precision)}"


def _print_sequence(
    values: Sequence[str],
    *,
    max_line_length: int = 80,
    indent: int = 4,
    split_each_line: bool = False,
    delim: str = "[]",
) -> str:
    item_lengths = tuple(map(len, values))

    # Entire sequence can fit on one line
    if sum(item_lengths) + 2 * len(item_lengths) < max_line_length:
        return delim[0] + ", ".join(values) + delim[1]

    if not split_each_line:
        # Put as many items as possible on each line
        lines = []
        line_start = 0
        n_items = 0
        while line_start + n_items <= len(values):
            line_len = (
                indent
                + sum(item_lengths[line_start : line_start + n_items])
                + 2 * n_items
            )
            if line_len > max_line_length:
                # Write at least one item (even if it is too long)
                n_items = max(1, n_items - 1)
                lines.append(", ".join(values[line_start : line_start + n_items]))
                line_start += n_items
                n_items = 0
            else:
                n_items += 1
        lines.append(", ".join(values[line_start:]))
    else:
        lines = list(values)

    body = ",\n".join(" " * indent + line for line in lines)
    return f"{delim[0]}\n{body},\n{delim[1]}\n"


@register_quantity_type
class SequenceQuantity(QuantityWrapper[Sequence[_T], _T]):
    """Formatting and comparison for sequences of values."""

    def str_short(self, _: Sequence[_T], max_width: Optional[int] = None) -> str:
        """Return a placeholder string.

        Cannot reliably print a sequence in limited width.
        """
        if max_width is None:
            max_width = self.width
        return "<sequence>"[:max_width]

    def str_long(self, value: Sequence[_T]) -> str:
        """Print all elements of the sequence verbosely."""
        return _print_sequence([self.wrapped_quantity.str_long(el) for el in value])

    def repr_quantity(self, value: Sequence[_T]) -> SerializedType:
        """Represent as a list and pass element representation to wrapped object."""
        return [self.wrapped_quantity.repr_quantity(elem) for elem in value]

    def deserialize_quantity(self, state: SerializedType) -> Sequence[_T]:
        """Load sequence result iteratively from serialized."""
        return [self.wrapped_quantity.deserialize_quantity(elem) for elem in state]

    def compare(self, ref: Sequence[_T], test: Sequence[_T]) -> bool:
        """Ensure that all sequence elements match."""
        if len(ref) != len(test):
            return False
        return all(
            self.wrapped_quantity.compare(ref_el, tst_el)
            for ref_el, tst_el in zip(ref, test)
        )

    def compare_msg(self, ref: Sequence[_T], test: Sequence[_T]) -> str:
        """Print count of non-matching elements."""
        if self.compare(ref, test):
            return "All elements match"
        elif len(ref) != len(test):
            return "Sequence lengths differ"
        else:
            elem_errs = sum(
                not self.wrapped_quantity.compare(e1, e2) for e1, e2 in zip(ref, test)
            )
            return f"Errors in {elem_errs:d} elements"


@register_quantity_type
class MappingQuantity(QuantityWrapper[Mapping[_KT, _T], _T]):
    """Formatting and comparison for mappings."""

    def str_short(self, _: Mapping[_KT, _T], max_width: Optional[int] = None) -> str:
        """Return a placeholder string.

        Cannot reliably print a mapping in limited width.
        """
        if max_width is None:
            max_width = self.width
        return "<mapping>"[:max_width]

    def str_long(self, value: Mapping[_KT, _T]) -> str:
        """Print all elements of the mapping."""
        return _print_sequence(
            [f"{k!s}: {self.wrapped_quantity.str_long(v)}" for k, v in value.items()],
            delim="{}",
        )

    def repr_quantity(self, value: Mapping[_KT, _T]) -> SerializedType:
        """Represent mapping as dict and pass value representation to wrapped object."""
        return {
            str(k): self.wrapped_quantity.repr_quantity(v) for k, v in value.items()
        }

    def deserialize_quantity(self, state: SerializedType) -> Mapping[_KT, _T]:
        """Load mapping from representation."""
        # Note: Only support string-like keys
        return {
            str(k): self.wrapped_quantity.deserialize_quantity(v)
            for k, v in state.items()
        }

    def compare(self, ref: Mapping[_KT, _T], test: Mapping[_KT, _T]) -> bool:
        """Ensure that all keys and values match."""
        if ref.keys() != test.keys():
            return False
        return all(self.wrapped_quantity.compare(ref[k], test[k]) for k in ref)

    def compare_msg(self, ref: Mapping[_KT, _T], test: Mapping[_KT, _T]) -> str:
        """Print count of non-matching elements."""
        if self.compare(ref, test):
            return "All elements match"
        elif ref.keys() != test.keys():
            return "Different keys are present"
        else:
            elem_errs = sum(
                not self.wrapped_quantity.compare(ref[k], test[k]) for k in ref
            )
            return f"Errors in {elem_errs:d} elements"
