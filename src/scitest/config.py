"""Parse and validate config."""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, Iterable, Optional, Sequence, Set, TypeVar, Union

import yaml

from scitest.print_util import wrap_line


class ConfigError(RuntimeError):
    pass


_T = TypeVar("_T")
_in_T = TypeVar("_in_T")


class _ConfigFieldBase(Generic[_in_T, _T], ABC):
    """Field descriptor for config class. Defines validation methods and input processing."""

    def __set_name__(self, owner, name):
        # type: (type, str) -> None
        if hasattr(owner, "config_fields"):
            owner.config_fields = (name, *owner.config_fields)
        else:
            owner.config_fields = (name,)
        # pylint: disable=attribute-defined-outside-init
        self.public_name = name
        self.private_name = "_" + name

    def __get__(self, instance, owner=None):
        # type: (Optional[object], type) -> Optional[_T]
        if instance is None:
            raise AttributeError(self.public_name)
        try:
            val = getattr(instance, self.private_name)
        except AttributeError:
            return None
        else:
            return val

    def __set__(self, instance, value):
        # type: (object, Optional[_in_T]) -> None
        if value is None:
            # Null input is ignored. To delete the field, use __delete__
            return
        new_val = self.normalize_value(value)
        try:
            self.validate(new_val)
        except ConfigError as exc:
            raise ConfigError(
                f"Bad value {new_val!r} for param {self.public_name!r}"
            ) from exc
        if hasattr(instance, self.private_name):
            if getattr(instance, self.private_name) is not None:
                new_val = self.merge(getattr(instance, self.private_name), new_val)
        setattr(instance, self.private_name, new_val)

    def __delete__(self, instance):
        # type: (object) -> None
        setattr(instance, self.private_name, None)

    @abstractmethod
    def normalize_value(self, value):
        # type: (_in_T) -> _T
        raise NotImplementedError

    @abstractmethod
    def validate(self, value):
        # type: (_T) -> None
        """Raise exception if `value` is invalid."""
        raise NotImplementedError

    @abstractmethod
    def merge(self, old_val, new_val):
        # type: (_T, _T) -> _T
        raise NotImplementedError


class _VersionField(_ConfigFieldBase[str, str]):
    """Config field containing a version string."""

    def normalize_value(self, value):
        # type: (str) -> str
        return value

    def validate(self, value):
        # type: (str) -> None
        if not re.match(r"^[-+.\w]+$", value):
            raise ConfigError(f"Invalid characters in version {value!r}")

    def merge(self, _, new_val):
        # type: (str, str) -> str
        return new_val


class _PathField(_ConfigFieldBase[Union[str, Path], Path]):
    """Config field containing a path.

    Args:
        must_exist: Validate that the provided path exists
    """

    def __init__(self, must_exist=False):
        # type: (bool) -> None
        self.must_exist = must_exist

    def normalize_value(self, value):
        # type: (Union[str, Path]) -> Path
        return Path(value)

    def validate(self, value):
        # type: (Path) -> None
        if self.must_exist:
            if not value.exists():
                raise ConfigError(f"Path {value!s} does not exist")

    def merge(self, _, new_val):
        # type: (Path, Path) -> Path
        return new_val


class _PathSetField(_ConfigFieldBase[Iterable[Union[str, Path]], Set[Path]]):
    """Config field containing a set of paths.

    Args:
        all_exist: Verify that all paths in the set exist
    """

    def __init__(self, all_exist=False):
        # type: (bool) -> None
        self.all_exist = all_exist

    def normalize_value(self, value):
        # type: (Iterable[Union[str, Path]]) -> Set[Path]
        return set(Path(x) for x in value)

    def validate(self, value):
        # type: (Set[Path]) -> None
        if self.all_exist:
            missing = [p for p in value if not p.exists()]
            if len(missing) > 0:
                raise ConfigError(f"Path {missing[0]!s} does not exist")

    def merge(self, old_val, new_val):
        # type: (Set[Path], Set[Path]) -> Set[Path]
        return old_val | new_val


class _TestSuiteSetField(_ConfigFieldBase[Iterable[str], Set[str]]):
    """Config field containing a set of test suite names."""

    def normalize_value(self, value):
        # type: (Iterable[str]) -> Set[str]
        return set(value)

    def validate(self, value):
        # type: (Set[str]) -> None
        for suite_name in value:
            if not re.match(r"^\w+$", suite_name):
                raise ConfigError(f"Invalid test suite name {suite_name!r}")

    def merge(self, old_val, new_val):
        # type: (Set[str], Set[str]) -> Set[str]
        return old_val | new_val


class TestConfig:
    """Config object for test code."""

    config_fields: Sequence[str] = ()
    test_dirs = _PathSetField()
    ref_dirs = _PathSetField(all_exist=True)
    query_dirs = _PathSetField(all_exist=True)
    exe_path = _PathField(must_exist=True)
    test_out = _PathField()
    bench_out = _PathField()
    ref_ver = _VersionField()
    cmp_ver = _VersionField()
    out_ver = _VersionField()
    test_suites = _TestSuiteSetField()

    # Private fields
    _path_vars = ("exe_path", "test_out", "bench_out")
    _path_group_vars = ("test_dirs", "ref_dirs", "query_dirs")
    _str_vars = ("ref_ver", "cmp_ver", "out_ver")
    _str_group_vars = ("test_suites",)

    def __init__(
        self,
        *,
        # Paths used during test execution
        exe_path: Path = None,
        test_out: Path = None,
        bench_out: Path = None,
        # Paths to search for test configuration
        test_dirs: Iterable[Union[str, Path]] = None,
        ref_dirs: Iterable[Union[str, Path]] = None,
        query_dirs: Iterable[Union[str, Path]] = None,
        # Version selection
        ref_ver: str = None,
        cmp_ver: str = None,
        out_ver: str = None,
        test_suites: Iterable[str] = None,
        **_,
    ):
        self.exe_path = exe_path
        self.test_out = test_out
        self.bench_out = bench_out
        self.test_dirs = test_dirs
        self.ref_dirs = ref_dirs
        self.query_dirs = query_dirs
        self.ref_ver = ref_ver
        self.cmp_ver = cmp_ver
        self.out_ver = out_ver
        self.test_suites = test_suites

    def __str__(self):
        # type: () -> str
        # TODO: print function
        raise NotImplementedError

    def __repr__(self):
        # type: () -> str

        arg_strings = tuple(
            (
                "{}={!r}".format(k, getattr(self, k))
                for k in self.config_fields
                if getattr(self, k) is not None
            )
        )
        return wrap_line(
            "{cls}({args})".format(
                cls=self.__class__.__name__, args=", ".join(arg_strings)
            )
        )

    def check_fields(self, required_fields):
        # type: (Iterable[str]) -> None
        """Raise error if any required fields are unset.

        Raises:
            ValueError: If an invalid field is requested
            ConfigError: If a required field is unset
        """
        for field in required_fields:
            if field not in self.config_fields:
                raise ValueError(f"{field!r} is not a valid field name.")
            if getattr(self, field) is None:
                raise ConfigError(f"Required field {field!r} is unset.")

    def update(self, other):
        # type: (TestConfig) -> None
        """Updates config values from"""
        if self.config_fields != other.config_fields:
            raise RuntimeError("Fields do not match.")
        for name in self.config_fields:
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
    def from_file(cls, file):
        # type: (Path) -> TestConfig
        """Construct config object from config file."""
        # Load the config file
        conf_root = file.parent
        with open(file) as _fh:
            file_conf = yaml.safe_load(_fh)
        for k, v in file_conf.items():
            if k not in cls.config_fields:
                raise ConfigError("Invalid config field {}".format(k))
            if k in cls._path_vars and v is not None:
                file_conf[k] = cls._parse_path(v, conf_root=conf_root)
            elif k in cls._path_group_vars:
                file_conf[k] = set(cls._parse_path(p, conf_root=conf_root) for p in v)
        return cls(**file_conf)
