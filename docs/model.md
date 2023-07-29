Model Conversion
================

This describes how Magql-SQLAlchemy will inspect and convert a SQLAlchemy model
class to a GraphQL object and operation fields.


Names
-----

The object name will be the same as the model class's name. For example,
`UserProfile`. This is used as the type name in the `check_delete` query and
search result items as well.

The operation field names will be prefixed with the model class's name converted
from CamelCase to snake_case. For example, `user_profile_create`.

The `model_list` query field returns a container object to represent the list
of rows as well as the total row count for pagination. For example,
`UserProfileListResult`.

If a column has a SQLAlchemy enum type, it will create a Magql enum type with
the name as the model class name and field name joined in CamelCase, like
`UserProfileFavoriteColor`.


Column Types
------------

For each column, a Magql scalar type will be chosen for the field and argument.
This uses `isinstance` checks, so subclass types like `Text` will still become
`String`. If a SQLAlchemy type is not recognized, `String` is used.

-   {class}`sqlalchemy.types.String` to {class}`magql.String`
-   {class}`sqlalchemy.types.Integer` to {class}`magql.Int`
-   {class}`sqlalchemy.types.Float` to {class}`magql.Float`
-   {class}`sqlalchemy.types.Boolean` to {class}`magql.Boolean`
-   {class}`sqlalchemy.types.DateTime` to {class}`magql.DateTime`
-   {class}`sqlalchemy.types.JSON` to {class}`magql.JSON`
-   {class}`sqlalchemy.types.ARRAY` wraps the inner type in {class}`magql.List`.
    This works for N-dimension arrays.
-   {class}`sqlalchemy.types.Enum` will create a {class}`magql.Enum` type with
    the CamelCase `ModelField` name. This works for {class}`enum.Enum`,
    {class}`typing.Literal`, or a list of choices.

Primary keys and foreign keys use their real type rather than the
{class}`magql.ID` type.

If the column is not nullable and does not have a default, then it is wrapped
in {class}`magql.NonNull` appropriately for field and argument types.


Relationships
-------------

For each relationship, a field will be generated on the object with the type of
the related model's object. To-one relationships will be single objects, to-many
relationships will be wrapped in {class}`magql.List`.

Relationships are also available as arguments to the `model_create` and
`model_update` mutation fields. In this case, they accept primary key value (or
values), and validate that the referenced rows exists.

When querying and selecting nested objects and fields across relationships,
Magql-SQLAlchemy will generate efficient eager loads for the selected
relationships. This means SQLAlchemy will emit a minimal number of queries to
load all data. You can observe this by turing `echo=True` on for your
SQLAlchemy engine.


Validators
----------

Two types of validators are automatically generated as needed:

-   For each column marked `unique=True`, and for each `UniqueConstraint` that
    applies to one or more columns, a validator will check that the values given
    during create or update are unique. The validator can handle multiple
    columns, defaults, and existing values for partial update. See
    {class}`.UniqueValidator`.
-   For each relationship, a validator will check that the given primary keys
    exist, for to-one and to-many relationships. See
    {class}`.ItemExistsValidator` and {class}`.ListExistsValidator`.
