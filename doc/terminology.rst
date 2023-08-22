
Terminology
-----------

As succinctly outlined in `pytest`_, a test can be thought of in four phases:

1. **Arrange**
2. **Act**
3. **Assert**
4. **Cleanup**

In normal unit testing, the **Arrange** phase is the most carefully defined, while the
rest follow naturally from the designed configuration.
Here, we are focused on integration tests of a software package.
Thus, the **Arrange** phase is simply providing the *input-conditions*: writing the
appropriate program input (and potentially setting some environment variables).
The **Act** and **Cleanup** phases are similarly straightforward---the program is run,
producing the *program output*, and the output is eventually discarded.
However, the **Assert** step becomes much more involved, as the program output can have
many constituent results, which all must be validated differently.
A *test* consists of the four phases outlined above applied to one set of input conditions.


.. _pytest : https://docs.pytest.org/en/stable/explanation/anatomy.html


Input conditions
    Input files and environment settings used to run the program under test.

Program output
    The result of the program under test, which will be checked for correctness.

Test
    The totality of checks performed on the program output for one set of input conditions

Query
    A procedure run on program output that extracts a value

Query result
    The result of a query run on a particular program output

Quantity
    The type of a query result. Defines methods to check equality

Query set
    A group of queries. A test applies one or more query sets to a program output

Result set
    The set of query results produced by a query set

