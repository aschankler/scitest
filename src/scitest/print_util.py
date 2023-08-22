"""Basic utilities for formatting output text."""

import sys
from typing import Sequence, TextIO, Tuple


def wrap_line(line, max_length=80, indent=4, sep=" "):
    # type: (str, int, int, str) -> str
    """Wrap string into lines of bounded length.

    Args:
        line: Input string to wrap
        max_length: Maximum length of a line in the output
        indent: Leading indent for wrapped lines
        sep: Split lines on this character

    Returns:
        Multiline wrapped string

    Raises:
        RuntimeError: if the line cannot be wrapped by splitting on the separators
    """

    if len(line) < max_length:
        return line
    else:
        first = True
        line_buffer = []
        while len(line) > max_length:
            # Pick next split
            split = line.rfind(sep, 0, max_length if first else max_length - indent)
            if split < 0:
                split = line.find(sep)
                if split < 0:
                    break
            this_line = line[:split]
            line = line[split:].strip()

            if not first:
                this_line = sep * indent + this_line
            line_buffer.append(this_line)
            first = False
        line_buffer.append(sep * indent + line)
        return "\n".join(line_buffer) + "\n"


class OutputTable:
    """Write a table of data onto and output stream.

    Args:
        fields: Sequence of field names + widths
        out_stream: Stream to write the table onto.
    """

    def __init__(self, fields, out_stream=sys.stdout):
        # type: (Sequence[Tuple[str, int]], TextIO) -> None
        self.fields = fields
        self.out_stream = out_stream
        self.field_names, self.field_widths = zip(*fields)

    @property
    def table_width(self):
        # type: () -> int
        """Total width of the table."""
        return sum(self.field_widths) + len(self.fields) + 1

    def _write_hsep(self):
        # type: () -> None
        self.out_stream.write("-" * self.table_width + "\n")

    @staticmethod
    def _format_entry(value, width):
        # type: (str, int) -> str
        if len(value) > width:
            return value[: width - 1] + "$"
        else:
            return value.center(width)

    def write_header(self):
        # type: () -> None
        """Write table row with column headers."""
        self._write_hsep()
        self.write_row(self.field_names)
        self._write_hsep()

    def write_row(self, values):
        # type: (Sequence[str]) -> None
        """Write table row of provided data.

        Args:
            values: Sequence of fields to write into table

        Raises:
            ValueError: If `values` is incorrectly sized for the table
        """
        self.out_stream.write("|")
        assert len(values) == len(self.fields)
        entries = [self._format_entry(v, w) for v, w in zip(values, self.field_widths)]
        self.out_stream.write("|".join(entries))
        self.out_stream.write("|\n")

    def write_footer(self):
        # type: () -> None
        """Write footer for the table."""
        self._write_hsep()
