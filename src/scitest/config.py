"""Parse and validate config."""

from collections.abc import Iterable
from pathlib import Path
from typing import Optional, Self, TypeAlias, TypeVar, Union

import attrs
import yaml


_T = TypeVar("_T")
_OptSet: TypeAlias = Optional[set[_T]]


# Note: currently `Attribute` is only generic in the stubs, so the type hint is escaped
def _merge_setter(
    inst: attrs.AttrsInstance, attrib: "attrs.Attribute[_OptSet]", value: _OptSet
) -> _OptSet:
    """Setter to merge new and existing values.

    Setting the value to None will clear the contents.
    """
    if value is None:
        # Then we are overriding the value
        return None
    this_val = getattr(inst, attrib.name)
    if this_val is None:
        return value
    return this_val | value


def _version_field():
    """Construct a config field that accepts version strings."""
    return attrs.field(
        default=None,
        validator=attrs.validators.optional(attrs.validators.matches_re(r"^[-+.\w]+$")),
    )


def _path_exist_validator(
    inst: attrs.AttrsInstance, attrib: attrs.Attribute, value: Path
) -> None:
    """Validator to check that a path exists.

    Only applies to absolute paths, so validators should be re-run after paths are resolved.
    """
    if value.is_absolute() and not value.exists():
        raise ValueError(f"Path {value!s} does not exist")


def _path_field(must_exist: bool = False):
    """Construct a config field that accepts a single path."""
    validator = attrs.validators.optional(_path_exist_validator) if must_exist else None
    return attrs.field(
        converter=attrs.converters.optional(Path),
        validator=validator,
    )


def _path_set_field(all_exist: bool = False):
    """Construct a config field that accepts a set of path objects."""
    validator = (
        attrs.validators.optional(attrs.validators.deep_iterable(_path_exist_validator))
        if all_exist
        else None
    )
    return attrs.field(
        default=None,
        converter=attrs.converters.optional(lambda paths: set(Path(p) for p in paths)),
        validator=validator,
        on_setattr=_merge_setter,
    )


def _test_suite_set_field():
    """Construct a config field to accept a set of test suite names."""
    return attrs.field(
        default=None,
        converter=attrs.converters.optional(set),
        validator=attrs.validators.optional(
            attrs.validators.deep_iterable(attrs.validators.matches_re(r"\w+"))
        ),
        on_setattr=_merge_setter,
    )


@attrs.mutable(kw_only=True, eq=False)
class TestConfig:
    """Config object for test code."""

    test_dirs: Optional[set[Path]] = _path_set_field()
    ref_dirs: Optional[set[Path]] = _path_set_field(all_exist=True)
    query_dirs: Optional[set[Path]] = _path_set_field(all_exist=True)
    exe_path: Optional[Path] = _path_field(must_exist=True)
    test_out: Optional[Path] = _path_field()
    bench_out: Optional[Path] = _path_field()
    ref_ver: Optional[str] = _version_field()
    cmp_ver: Optional[str] = _version_field()
    out_ver: Optional[str] = _version_field()
    test_suites: Optional[set[str]] = _test_suite_set_field()

    # Private fields
    _path_vars = ("exe_path", "test_out", "bench_out")
    _path_group_vars = ("test_dirs", "ref_dirs", "query_dirs")
    _str_vars = ("ref_ver", "cmp_ver", "out_ver")
    _str_group_vars = ("test_suites",)

    def __str__(self):
        # type: () -> str
        # TODO: print function
        raise NotImplementedError

    def check_fields(self, required_fields: Iterable[str]) -> None:
        """Raise error if any required fields are unset.

        Raises:
            ValueError: If an invalid field is requested
            AttributeError: If a required field is unset
        """
        valid_fields = attrs.fields_dict(type(self)).keys()
        for field in required_fields:
            if field not in valid_fields:
                raise ValueError(f"{field!r} is not a valid field name.")
            if getattr(self, field) is None:
                raise AttributeError(f"Required field {field!r} is unset.")

    def update(self, other: Self) -> None:
        """Updates config values from another config object."""
        for name in attrs.fields_dict(other):
            # Values in other override (unless the field overrides the merge method)
            if getattr(other, name) is not None:
                setattr(self, name, getattr(other, name))

    @staticmethod
    def _parse_path(path_str, conf_root=None):
        # type: (str, Optional[Union[str, Path]]) -> Path
        fmt_dict = {"program_root": Path(__file__).resolve().parent}
        if conf_root is not None:
            fmt_dict["conf_root"] = str(conf_root)
        # TODO: old style formatting does not play well with yaml
        path_str %= fmt_dict
        return Path(path_str).resolve()

    @classmethod
    def from_namespace(cls, namespace: object) -> Self:
        """Construct a config from another dataclass-like object."""
        field_names = attrs.fields_dict(cls).keys()
        fields = {k: v for k, v in vars(namespace).items() if k in field_names}
        return cls(**fields)

    @classmethod
    def from_file(cls, file: Path) -> Self:
        """Construct config object from config file."""
        # Load the config file
        conf_root = file.parent
        with open(file) as _fh:
            file_conf = yaml.safe_load(_fh)
        for k, v in file_conf.items():
            if k in cls._path_vars and v is not None:
                file_conf[k] = cls._parse_path(v, conf_root=conf_root)
            elif k in cls._path_group_vars:
                file_conf[k] = set(cls._parse_path(p, conf_root=conf_root) for p in v)
        return cls(**file_conf)
