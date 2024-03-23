"""Parse and validate config."""

from collections.abc import Collection, Iterable, Mapping
from pathlib import Path
from typing import Optional, Self, TypeAlias, TypeVar

import attrs
import yaml

_T = TypeVar("_T")
_OptSet: TypeAlias = Optional[set[_T]]

CONFIG_TYPE_KEY = "__config_type"


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
    # pylint: disable=unused-argument
    if value.is_absolute() and not value.exists():
        raise ValueError(f"Path {value!s} does not exist")


def _path_field(must_exist: bool = False):
    """Construct a config field that accepts a single path."""
    validator = attrs.validators.optional(_path_exist_validator) if must_exist else None
    return attrs.field(
        default=None,
        converter=attrs.converters.optional(Path),
        validator=validator,
        metadata={CONFIG_TYPE_KEY: "path"},
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
        converter=attrs.converters.optional(lambda paths: {Path(p) for p in paths}),
        validator=validator,
        on_setattr=_merge_setter,
        metadata={CONFIG_TYPE_KEY: "path_set"},
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
    """Config object for test code.

    Attributes:
        test_dirs: directories to search for test suite definitions
        ref_dirs: directories to search for reference data
        query_dirs: directories to search for query definitions
        exe_path: path to program under test
        test_out: directory to write test results
        bench_out: directory to write benchmark results when produced
        ref_ver: use this version as reference. Default is to use the latest
        cmp_ver: compare this version against the reference
        out_ver: use this version to stamp the test output
        test_suites: run only these test suites
    """

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

    def check_fields(self, required_fields: Iterable[str]) -> None:
        """Raise error if any required fields are unset.

        Raises:
            ValueError: If an invalid field is requested
            AttributeError: If a required field is unset
        """
        # PC does not type attrs classes correctly
        # noinspection PyTypeChecker
        valid_fields = attrs.fields_dict(type(self)).keys()
        for field in required_fields:
            if field not in valid_fields:
                raise ValueError(f"{field!r} is not a valid field name.")
            if getattr(self, field) is None:
                raise AttributeError(f"Required field {field!r} is unset.")

    @staticmethod
    def _root_path(init_path: Path | str, relative_to: Optional[Path] = None) -> Path:
        updated_path = Path(init_path)
        if relative_to is not None and not updated_path.is_absolute():
            # Resolve relative paths if possible
            updated_path = relative_to / updated_path
        return updated_path

    def _resolve_path_field(self, field_name: str, root_point: Path) -> None:
        old_path = getattr(self, field_name)
        if old_path is not None:
            setattr(self, field_name, self._root_path(old_path, root_point))

    def _resolve_path_set_field(self, field_name: str, root_point: Path) -> None:
        old_set = getattr(self, field_name)
        if old_set is None:
            return
        new_set = {self._root_path(_path, root_point) for _path in old_set}
        # First explicitly unset the value to avoid the merge setter
        setattr(self, field_name, None)
        setattr(self, field_name, new_set)

    def resolve_paths(self, root_point: Path) -> None:
        """Resolve relative paths by rooting at a provided directory."""
        # noinspection PyTypeChecker
        for attrib in attrs.fields(type(self)):
            if CONFIG_TYPE_KEY in attrib.metadata:
                if attrib.metadata[CONFIG_TYPE_KEY] == "path":
                    self._resolve_path_field(attrib.name, root_point)
                elif attrib.metadata[CONFIG_TYPE_KEY] == "path_set":
                    self._resolve_path_set_field(attrib.name, root_point)

    def update(self, other: Self) -> None:
        """Updates config values from another config object."""
        for name in attrs.fields_dict(type(other)):
            # Values in other override (unless the field overrides the merge method)
            if getattr(other, name) is not None:
                setattr(self, name, getattr(other, name))
        # noinspection PyTypeChecker
        attrs.validate(self)

    @classmethod
    def from_mapping(
        cls, mapping: Mapping[str, str], *, root_path: Optional[Path] = None
    ) -> Self:
        """Construct config from a mapping."""
        new_conf = cls(**mapping)
        if root_path is not None:
            new_conf.resolve_paths(root_path)
        return new_conf

    @classmethod
    def from_namespace(
        cls,
        namespace: object,
        use_fields: Optional[Collection[str]],
        *,
        root_path: Optional[Path] = None,
    ) -> Self:
        """Construct a config from another dataclass-like object."""
        # noinspection PyTypeChecker
        field_names = attrs.fields_dict(cls).keys()
        if use_fields is not None:
            if any(_name not in field_names for _name in use_fields):
                raise ValueError(f"Unknown fields in {use_fields}")
            field_names = use_fields
        config_dict = {k: v for k, v in vars(namespace).items() if k in field_names}
        return cls.from_mapping(config_dict, root_path=root_path)

    @classmethod
    def from_file(cls, file: Path) -> Self:
        """Construct config object from config file."""
        # Load the config file
        conf_root = file.parent.resolve()
        with open(file, encoding="utf8") as _fh:
            file_conf = yaml.safe_load(_fh)
        return cls.from_mapping(file_conf, root_path=conf_root)
