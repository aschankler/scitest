"""Exceptions for the test program."""


class TestCodeError(RuntimeError):
    """Base error in query code."""


class SerializationError(TestCodeError):
    """Error serializing or deserializing test descriptions."""


class TestSetupError(TestCodeError):
    """Input conditions cannot be set up."""


class ProgramError(TestCodeError):
    """Error running the program under test."""


class QueryError(TestCodeError):
    """Error running a query on test output."""

    def __init__(self, query_name: str, message: str) -> None:
        self.query_name = query_name
        self.message = message

    def __str__(self) -> str:
        return f"Error in query {self.query_name}: {self.message}"


class TestFailure(TestCodeError):
    """Test ran correctly, but gave incorrect result."""

    def __init__(self, test, ref):
        self.test = test
        self.ref = ref
