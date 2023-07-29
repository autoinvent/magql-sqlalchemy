List Query Filters
==================

The `model_list` query field generated for each model supports building
arbitrarily complex filters with the `filter` argument.

The `filter` argument takes a list of lists of filter item structures. Each
filter item in a list is combined with `AND`. Each list of filter items is
combined with `OR`. As a shortcut, GraphQL will wrap a single item in the two
lists implicitly.

Each filter item has the following keys:

-   `path`, a column name on the model being queried, or a dotted path that
    can access columns through one or more relationships from the initial model.
-   `op`, an operator name, which is dependant on the column's type. See the
    next section for the default operators.
-   `not`, an optional boolean to negate the filter. For example, the `eq` op
    can be turned into `not eq` without needing to define a separate operator.
-   `value`, the value to filter on. In simple cases, this will be a single
    value, but some operators like `eq` support a list of values as a shortcut
    to specifying multiple filter items. It can be arbitrary JSON data to
    support anything custom operators might use.


Operators
---------

Different filter operations are available depending on the type of the column.
The {data}`.filters.type_ops` data structure maps SQLAlchemy types to operation
names to functions that apply the operation.

-   {class}`~sqlalchemy.types.String`
    -   `eq`, exact equality. Accepts a single value or list.
    -   `like`, case-insensitive partial match. Accepts a single value or list.
        SQL wildcard characters are escaped.
-   {class}`~sqlalchemy.types.Integer`, {class}`~sqlalchemy.types.Float`,
    {class}`~sqlalchemy.types.DateTime`
    -   `eq`, exact equality. Accepts a single value or list.
    -   `lt`, less than a single value.
    -   `le`, less than or equal to a single value.
    -   `ge`, greater than or equal to a single value.
    -   `gt`, greater than a single value.
-   {class}`~sqlalchemy.types.Boolean`
    -   `eq`, true or false.
-   {class}`~sqlalchemy.types.DateTime`
    -   `eq`, exact equality. Accepts a single value or list.


Custom Operators
----------------

You can add operators for other types, or add to the operators for an existing
type, by modifying the {data}`.filter.type_ops` structure. An operator function
takes the SQLAlchemy column being filtered, and the list of values (will be a
list even if a single value was given), and should return a SQLAlchemy
expression that can be used with `WHERE`.
