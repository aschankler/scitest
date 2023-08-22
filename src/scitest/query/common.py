"""Implementation of standard query types."""

import re
from typing import (
    Any,
    Callable,
    Generic,
    Iterable,
    List,
    Mapping,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

import attrs

from scitest.exceptions import QueryError
from scitest.query.base import (
    QUERY_EXCLUDE_KEY,
    QUERY_REQUIRED_KEY,
    UNSET,
    OutputQueryBase,
    register_query_type,
)

_T = TypeVar("_T")


def _parse_yes_no(value: str) -> bool:
    """Convert a yes/no value into a boolean."""
    value = value.lower().strip()
    if value == "yes":
        return True
    elif value == "no":
        return False
    else:
        raise QueryError


_parse_query_result_fns: dict[str, Callable[[str], Any]] = {
    "float": float,
    "int": int,
    "str": str,
    "yesno": _parse_yes_no,
}


def _parse_query_result(result_type: str, value: str) -> Any:
    """Parse query result string into the desired type.

    Args:
        result_type: how to parse the result. Valid values are {"float", "int", "str", "yesno"}
        value: string value to parse
    """
    try:
        parse_result = _parse_query_result_fns[result_type]
    except KeyError as exe:
        raise ValueError(f"Invalid result type {result_type}") from exe
    return parse_result(value)


def _private_field(**kwargs) -> Any:
    if "metadata" not in kwargs:
        kwargs["metadata"] = {}
    kwargs["metadata"].update({QUERY_EXCLUDE_KEY: True})
    kwargs.update({"init": False, "eq": False})
    return attrs.field(**kwargs)


@register_query_type
@attrs.define(order=False, repr=False)
class RegexQuery(OutputQueryBase[_T]):
    """Extract data from file by matching against a regex.

    Attributes:
        query_name: Name of query instance. Should be unique
        quantity: Quantity object used to format the query result
        file_ext: If specified, run query on the file "{prefix}.{file_ext}"
        search_regex: Regex used to match query result in file (required)
        regex_group: capture group in the search_regex containing the result
        result_type: how to interpret the regex result from string
        search_start_regex: Only begin searching after this regex matches
        search_end_regex: Match must be found before this regex
    """

    search_regex: str = attrs.field(
        default=UNSET,
        kw_only=True,
        validator=attrs.validators.instance_of((str, type(UNSET))),
        metadata={QUERY_REQUIRED_KEY: True},
    )
    regex_group: int | str = attrs.field(
        default=1, kw_only=True, validator=attrs.validators.instance_of((int, str))
    )
    result_type: str = attrs.field(
        default="float",
        kw_only=True,
        validator=attrs.validators.in_(_parse_query_result_fns.keys()),
    )
    search_start_regex: str = attrs.field(
        default="", kw_only=True, validator=attrs.validators.instance_of(str)
    )
    search_end_regex: str = attrs.field(
        default="", kw_only=True, validator=attrs.validators.instance_of(str)
    )

    # Private attributes
    _start_re_cache: None | re.Pattern = _private_field(default=None)
    _end_re_cache: None | re.Pattern = _private_field(default=None)

    def start_search_region(self, line_no: int, line: str) -> bool:
        """Signal when entering the search region."""
        if not self.search_start_regex:
            return True
        if self._start_re_cache is None:
            self._start_re_cache = re.compile(self.search_start_regex)
        return bool(self._start_re_cache.match(line))

    def end_search_region(self, line_no: int, line: str) -> bool:
        """Signal when exiting the search region."""
        if not self.search_end_regex:
            return False
        if self._end_re_cache is None:
            self._end_re_cache = re.compile(self.search_end_regex)
        return bool(self._end_re_cache.match(line))

    def parse_file(self, lines: Iterable[str]) -> _T:
        """Match lines against the search regex."""
        search_region = False
        search_regex = re.compile(self.search_regex)

        for line_no, line in enumerate(lines):
            if not search_region:
                if not self.start_search_region(line_no, line):
                    continue
                search_region = True

            if self.end_search_region(line_no, line):
                break

            if match := search_regex.match(line):
                result_str = match.group(self.regex_group)
                return _parse_query_result(self.result_type, result_str)

        raise QueryError(self.query_name, "Could not find matching line")


@register_query_type
@attrs.define(order=False, repr=False)
class TableQuery(OutputQueryBase[Union[Sequence[_T], Mapping[str, _T]]], Generic[_T]):
    """Extract data from each row of a table.

    Attributes:
        query_name: Name of query instance. Should be unique
        quantity: Quantity object used to format the query result
        file_ext: If specified, run query on the file "{prefix}.{file_ext}"
        table_start: regex to match the table header (required)
        table_end: regex to detect the end of the table
        table_skip_rows: number of rows to skip after matching the table header
        table_delimiter: string used to separate columns (default: whitespace)
        key_field: table column to use as the mapping index for the results
        result_field: table column containing the query result (required)
        allow_ragged: whether to throw an error if rows have an unequal number of
            columns. Indexing to retrieve result field must still succeed
        allow_empty: expect empty cells in table
        result_type: how to interpret the regex result from string
        search_start_regex: Only begin searching after this regex matches
        search_end_regex: Match must be found before this regex
    """

    table_start: str = attrs.field(
        default=UNSET,
        kw_only=True,
        validator=attrs.validators.instance_of((str, type(UNSET))),
        metadata={QUERY_REQUIRED_KEY: True},
    )
    table_end: str = attrs.field(
        default=r"^\s*$", kw_only=True, validator=attrs.validators.instance_of(str)
    )
    table_skip_rows: int = attrs.field(
        default=0,
        kw_only=True,
        validator=[attrs.validators.instance_of(int), attrs.validators.ge(0)],
    )
    table_delimiter: str | None = attrs.field(
        default=None,
        kw_only=True,
        validator=attrs.validators.instance_of((str, type(None))),
    )
    key_field: int | None = attrs.field(
        default=None,
        kw_only=True,
        validator=attrs.validators.instance_of((int, type(None))),
    )
    result_field: int = attrs.field(
        default=UNSET,
        kw_only=True,
        validator=attrs.validators.instance_of((int, type(UNSET))),
        metadata={QUERY_REQUIRED_KEY: True},
    )
    allow_ragged: bool = attrs.field(
        default=False, kw_only=True, validator=attrs.validators.instance_of(bool)
    )
    allow_empty: bool = attrs.field(
        default=False, kw_only=True, validator=attrs.validators.instance_of(bool)
    )
    result_type: str = attrs.field(
        default="float",
        kw_only=True,
        validator=attrs.validators.in_(_parse_query_result_fns.keys()),
    )
    search_start_regex: str = attrs.field(
        default="", kw_only=True, validator=attrs.validators.instance_of(str)
    )
    search_end_regex: str = attrs.field(
        default="", kw_only=True, validator=attrs.validators.instance_of(str)
    )

    # Private fields
    _start_re_cache: None | re.Pattern = _private_field(default=None)
    _end_re_cache: None | re.Pattern = _private_field(default=None)
    _table_columns: None | int = _private_field(default=None)

    def start_search_region(self, line_no: int, line: str) -> bool:
        """Signal when entering the search region."""
        if not self.search_start_regex:
            return True
        if self._start_re_cache is None:
            self._start_re_cache = re.compile(self.search_start_regex)
        return bool(self._start_re_cache.match(line))

    def end_search_region(self, line_no: int, line: str) -> bool:
        """Signal when exiting the search region."""
        if not self.search_end_regex:
            return False
        if self._end_re_cache is None:
            self._end_re_cache = re.compile(self.search_end_regex)
        return bool(self._end_re_cache.match(line))

    def _parse_table_row(self, row: str) -> Union[_T, Tuple[str, _T]]:
        split_row = row.split(self.table_delimiter)

        # Check if the table is ragged
        if self._table_columns is None:
            self._table_columns = len(split_row)
        if not self.allow_ragged and len(split_row) != self._table_columns:
            raise QueryError(self.query_name, "Table is ragged")

        # Get result
        # Todo: Empty cell check does not work if tables are whitespace delimited
        try:
            result_str = split_row[self.result_field]
        except IndexError as exe:
            if not self.allow_empty:
                raise QueryError(
                    self.query_name, f"Could not get column {self.result_field}"
                ) from exe
            result_value = None
        else:
            result_value = _parse_query_result(self.result_type, result_str)

        # Get key if needed
        if self.key_field is not None:
            try:
                key_str = split_row[self.key_field]
            except IndexError as exe:
                raise QueryError(
                    self.query_name, f"Could not get column {self.result_field}"
                ) from exe
            return key_str, result_value
        return result_value

    def parse_file(self, lines: Iterable[str]) -> Union[Sequence[_T], Mapping[str, _T]]:
        """Find a table and extract a value from each row."""
        search_region = False
        table_region = False
        skip_count = 0
        rows_data = []  # type: List[Union[_T, Tuple[str, _T]]]
        table_start_re = re.compile(self.table_start)
        table_end_re = re.compile(self.table_end)

        for line_no, line in enumerate(lines):
            if not search_region:
                if not self.start_search_region(line_no, line):
                    continue
                search_region = True

            if self.end_search_region(line_no, line):
                break

            if table_start_re.match(line):
                table_region = True

            if table_region:
                if skip_count < self.table_skip_rows:
                    skip_count += 1
                    continue
                if table_end_re.match(line):
                    if self.key_field is not None:
                        # Return a mapping if rows are labeled by keys
                        return dict(rows_data)
                    return rows_data
                rows_data.append(self._parse_table_row(line))

        if not table_region:
            raise QueryError(self.query_name, "Could not find table")
        raise QueryError(self.query_name, "End of table not found")
