"""Parsing and sorting for benchmark version stamps."""

import re
from abc import ABC, abstractmethod
from functools import total_ordering
from typing import ClassVar, Iterable, Self, TypeVar, Union


class VersionError(ValueError):
    pass


_T = TypeVar("_T", bound="Version")


# Global registry mapping stamp prefixes to version classes
_version_formats: dict[str, type["Version"]] = {}


def register_version_fmt(cls: type["Version"]) -> type["Version"]:
    """Register a version format class in a global registry.

    Raises:
        ValueError: If the version format uses the same stamp prefix as one already registered
    """
    if cls.stamp_prefix in _version_formats:
        raise ValueError(f"Version prefix '{cls.stamp_prefix}' already in use")
    _version_formats[cls.stamp_prefix] = cls
    return cls


def version_from_stamp(stamp: str) -> "Version":
    """Try to parse a version string using registered version formats."""
    for prefix, ver_cls in _version_formats.items():
        if stamp.startswith(prefix):
            return ver_cls.from_stamp(stamp)
    raise VersionError(f"Stamp '{stamp}' matched no known version formats")


@total_ordering
class Version(ABC):
    """Parses and orders different benchmark/test version strings."""

    priority: ClassVar[int] = -1
    stamp_prefix: ClassVar[str] = ""

    def __init__(self, *args):
        # type: (*Union[str, int, None]) -> None
        self.components = tuple(args)

    @property
    @abstractmethod
    def stamp(self) -> str:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_stamp(cls, stamp: str) -> Self:
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        if self.priority == other.priority:
            return self.cls_eq(other)
        else:
            return False

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        # Instances of different subclasses are sorted by class priority
        if self.priority == other.priority:
            return self.cls_lt(other)
        else:
            return self.priority < other.priority

    def cls_eq(self, other: Self) -> bool:
        return self.components == other.components

    @abstractmethod
    def cls_lt(self, other: Self) -> bool:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.stamp

    def __repr__(self) -> str:
        arg_str = ", ".join(map(repr, self.components))
        return f"{self.__class__.__name__}({arg_str})"


@register_version_fmt
class DateVersion(Version):
    """Version interpreted as a date."""

    priority = 5
    stamp_prefix = "d"
    _date_ver_re = re.compile(r"^(\d{4})_(\d{2})_(\d{2})$")

    def __init__(self, *args):
        # type: (*Union[str, int]) -> None
        if len(args) != 3:
            raise ValueError
        year, month, day = args
        self.year = int(year)
        self.month = int(month)
        self.day = int(day)
        super().__init__(year, month, day)

    @property
    def stamp(self) -> str:
        return f"d{self.year:04d}_{self.month:02d}_{self.day:02d}"

    @classmethod
    def from_stamp(cls, stamp: str) -> Self:
        if not stamp.startswith(cls.stamp_prefix):
            raise VersionError("Malformed stamp " + stamp)
        match = cls._date_ver_re.match(stamp[1:])
        if not match:
            raise VersionError("Bad date " + stamp[1:])
        return cls(*map(int, match.groups()))

    @classmethod
    def today(cls) -> Self:
        from datetime import date

        today = date.today()
        return cls(today.year, today.month, today.day)

    def cls_lt(self, other: Self) -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError
        return self.components < other.components


@register_version_fmt
class SemVersion(Version):
    """Version interpreted according to the semantic version spec."""

    priority = 10
    stamp_prefix = "v"
    _sem_ver_re = re.compile(
        r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
        r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
        r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
        r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
    )
    _pr_numeric_re = re.compile(r"^(?:0|[1-9]\d*)$")

    def __init__(self, *args):
        # type: (*Union[str, int, None]) -> None
        if len(args) != 5:
            raise ValueError
        major, minor, patch, pre_rel, build = args
        if major is None or minor is None or patch is None:
            raise ValueError
        self.version_core = (int(major), int(minor), int(patch))
        self.pre_release = str(pre_rel) if pre_rel is not None else None
        self.build_meta = str(build) if build is not None else None
        super().__init__(*args)

    @property
    def stamp(self) -> str:
        version_string = "v{!s}.{!s}.{!s}".format(*self.version_core)
        if self.pre_release is not None:
            version_string += f"-{self.pre_release}"
        if self.build_meta is not None:
            version_string += f"+{self.build_meta}"
        return version_string

    @classmethod
    def from_stamp(cls, stamp: str) -> Self:
        if not stamp.startswith(cls.stamp_prefix):
            raise VersionError(f"Malformed stamp {stamp}")
        match = cls._sem_ver_re.match(stamp[1:])
        if not match:
            raise VersionError(f"Bad semantic version {stamp[1:]}")
        components: list[Union[str, int, None]] = [
            int(match.group(k)) for k in ("major", "minor", "patch")
        ]
        for k in ("prerelease", "buildmetadata"):
            try:
                components.append(match.group(k))
            except IndexError:
                components.append("")

        return cls(*components)

    def cls_eq(self, other: Self) -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError
        # Ignore build metadata in comparison
        return self.components[:4] == other.components[:4]

    def cls_lt(self, other: Self) -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError
        # Compare version core
        if self.version_core != other.version_core:
            return self.version_core < other.version_core
        # Compare pre-release
        if self.pre_release == other.pre_release:
            # Pre-release versions equal; build metadata does not factor into comparison
            return False
        elif self.pre_release is None:
            # Other has a pre-release version; normal versions have precedence over pre-release versions
            return False
        elif other.pre_release is None:
            # This is a pre-release but other is not
            return True
        else:
            # Compare pre-release versions
            return self._compare_pre_release(self.pre_release, other.pre_release)

    @classmethod
    def _compare_pre_release(cls, this_pr: str, other_pr: str) -> bool:
        this_h, _, this_rest = this_pr.partition(".")
        other_h, _, other_rest = other_pr.partition(".")
        if this_h != other_h:
            # Difference found; order based on this component
            this_num_mat = cls._pr_numeric_re.match(this_h)
            other_num_mat = cls._pr_numeric_re.match(other_h)
            if this_num_mat and other_num_mat:
                # Both fields numeric; compare as ints
                return int(this_h) < int(other_h)
            elif this_num_mat or other_num_mat:
                # Numeric fields have lower precedence
                return this_num_mat is not None
            else:
                # Compare non-numeric fields lexicographically
                return this_h < other_h
        elif this_rest == "" or other_rest == "":
            # More fields is higher precedence; should not both be empty (but if so, order is arbitrary)
            return this_rest == ""
        else:
            # Order using the rest of the version string
            return cls._compare_pre_release(this_rest, other_rest)


def get_latest_version(version_strings: Iterable[str]) -> str:
    versions = [version_from_stamp(v_str) for v_str in version_strings]
    return max(versions).stamp
