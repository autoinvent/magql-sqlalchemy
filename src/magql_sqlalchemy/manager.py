from __future__ import annotations

import ast
import inspect
import re
import textwrap
import typing as t
from itertools import pairwise

import magql.nodes
import sqlalchemy as sa
import sqlalchemy.orm as sa_orm
from magql.filters import filter_item
from magql.search import Search
from magql.search import SearchProvider
from sqlalchemy.sql.type_api import TypeEngine

from .pagination import PerPageValidator
from .pagination import validate_page
from .resolvers import CreateResolver
from .resolvers import DeleteResolver
from .resolvers import ItemResolver
from .resolvers import ListResolver
from .resolvers import resolve_display_value
from .resolvers import UpdateResolver
from .search import ColumnSearchProvider
from .validators import ItemExistsValidator
from .validators import ListExistsValidator
from .validators import UniqueValidator

M = t.TypeVar("M", bound=sa_orm.DeclarativeBase)


class ResolverFactory(t.Protocol):
    def __call__(
        self, model: type[sa_orm.DeclarativeBase]
    ) -> magql.nodes.ResolverCallable: ...


class ModelManager(t.Generic[M]):
    """The API for a single SQLAlchemy model class. Generates Magql types, fields,
    resolvers, etc. These are exposed as attributes on this manager, and can be further
    customized after generation.

    :param model: The SQLAlchemy model class.
    :param search: Whether this model will provide results in global search.
    """

    item_factory: t.ClassVar[ResolverFactory] = ItemResolver
    """Callable that takes the model class and creates the resolver callable for
    :attr:`item_field`.

    .. versionadded:: 1.1
    """

    list_factory: t.ClassVar[ResolverFactory] = ListResolver
    """Callable that takes the model class and creates the resolver callable for
    :attr:`list_field`.

    .. versionadded:: 1.1
    """

    create_factory: t.ClassVar[ResolverFactory] = CreateResolver
    """Callable that takes the model class and creates the resolver callable for
    :attr:`create_field`.

    .. versionadded:: 1.1
    """

    update_factory: t.ClassVar[ResolverFactory] = UpdateResolver
    """Callable that takes the model class and creates the resolver callable for
    :attr:`update_field`.

    .. versionadded:: 1.1
    """

    delete_factory: t.ClassVar[ResolverFactory] = DeleteResolver
    """Callable that takes the model class and creates the resolver callable for
    :attr:`delete_field`.

    .. versionadded:: 1.1
    """

    model: type[M]
    """The SQLAlchemy model class."""

    object: magql.Object
    """The object type and fields representing the model and its columns. The type name
    is the model name.

    .. code-block:: text

        type Model {
            id: Int!
            name: String!
        }
    """

    item_field: magql.Field
    """Query that selects a row by id from the database. Will return null if the
    id doesn't exist. The field name is the snake case model name with ``_item``
    appended. Uses :class:`.ItemResolver`.

    .. code-block:: text

        type Query {
            model_item(id: Int!): Model
        }
    """

    list_result: magql.Object
    """The object type representing the result of the list query. The type name is the
    model name with ``ListResult`` appended. :class:`.ListResult` is the Python type
    corresponding to this Magql type.

    .. code-block: graphql

        type ModelListResult {
            items: [Model!]!
            total: Int!
        }
    """

    list_field: magql.Field
    """Query that selects multiple rows from the database. The field name is the snake
    case model name with ``_list`` appended. Uses :class:`.ListResolver`.

    .. code-block:: text

        type Query {
            model_list(
                filter: [[FilterItem!]!],
                sort: [String!],
                page: Int,
                per_page: Int
            ): ModelListResult!
        }
    """

    create_field: magql.Field
    """Mutation that inserts a row into the database. The field name is the snake case
    model name with ``_create`` appended. An argument is generated for each column in
    the model except the primary key. An argument is required if its column is not
    nullable and doesn't have a default. Uses :class:`.CreateResolver`.

    .. code-block:: text

        type Mutation {
            model_create(name: String!): Model!
        }
    """

    update_field: magql.Field
    """Mutation that updates a row in the database. The field name is the snake case
    model name with ``_update`` appended. An argument is generated for each column in
    the model. The primary key argument is required, all others are not. Columns are not
    updated if their argument is not given. Uses :class:`.UpdateResolver`.

    .. code-block:: text

        type Mutation {
            model_update(id: Int!, name: String): Model!
        }
    """

    delete_field: magql.Field
    """Mutation that deletes a row from the database. The field name is the snake case
    model name with ``_delete`` appended. Uses :class:`.DeleteResolver`.

    .. code-block:: text

        type Mutation {
            model_delete(id: Int!): Boolean!
        }
    """

    search_provider: SearchProvider | None = None
    """A global search provider function. Enabling search will create a
    :class:`.ColumnSearchProvider` that checks if any of the model's string columns
    contains the search term. This can be set to a custom function to change search
    behavior.
    """

    def __init__(self, model: type[M], search: bool = False) -> None:
        self.model = model
        model_name = model.__name__
        mapper: sa_orm.Mapper[M] = sa_orm.class_mapper(model)  # pyright: ignore
        # Find the primary key column and its Magql type.
        pk_name, pk_col = _find_pk(model_name, mapper.columns)
        pk_type = _convert_column_type(model_name, pk_name, pk_col)
        self.object = object = magql.Object(
            model_name,
            description=get_obj_doc(model),
            fields={
                "_display_value": magql.Field(
                    "String!",
                    description="Representation of this object for links.",
                    resolve=resolve_display_value,
                ),
            },
        )
        attr_docs = get_attr_docs(model)
        item_exists = ItemExistsValidator(model, pk_name, pk_col)
        update_args: dict[str, magql.Argument] = {
            pk_name: magql.Argument(pk_type.non_null, validators=[item_exists])
        }
        create_args: dict[str, magql.Argument] = {}

        for key, col in mapper.columns.items():
            # Foreign key columns are assumed to have relationships, handled later.
            if col.foreign_keys:
                continue

            col_type = _convert_column_type(model_name, key, col)
            doc = attr_docs.get(key)

            if col.nullable:
                object.fields[key] = magql.Field(col_type, description=doc)
            else:
                object.fields[key] = magql.Field(col_type.non_null, description=doc)

            # The primary key column is assumed to be generated, only used as an input
            # when querying an item by id.
            if col.primary_key:
                continue

            update_args[key] = magql.Argument(col_type, description=doc)

            # When creating an object, a field is required if it's not nullable and
            # doesn't have a default value.
            if col.nullable or col.default:
                create_args[key] = magql.Argument(col_type, description=doc)
            else:
                create_args[key] = magql.Argument(col_type.non_null, description=doc)

        for key, rel in mapper.relationships.items():
            target_model = rel.entity.class_
            target_name = target_model.__name__
            # Assume a single primary key column for the input type. Can't use a local
            # foreign key because that won't exist for to-many.
            target_pk_name, target_pk_col = _find_pk(target_name, rel.mapper.columns)
            target_pk_type = _convert_column_type(
                target_name, target_pk_name, target_pk_col
            )
            doc = attr_docs.get(key)

            if rel.direction is sa_orm.MANYTOONE:
                # To-one is like a column but with an object type instead of a scalar.
                # Assume a single foreign key column.
                col = next(iter(rel.local_columns))  # type: ignore[arg-type]

                if col.nullable:
                    object.fields[key] = magql.Field(target_name, description=doc)
                else:
                    object.fields[key] = magql.Field(
                        magql.NonNull(target_name), description=doc
                    )

                rel_item_exists = ItemExistsValidator(
                    target_model, target_pk_name, target_pk_col
                )
                update_args[key] = magql.Argument(
                    target_pk_type, validators=[rel_item_exists], description=doc
                )

                if col.nullable or col.default:
                    create_args[key] = magql.Argument(
                        target_pk_type, validators=[rel_item_exists], description=doc
                    )
                else:
                    create_args[key] = magql.Argument(
                        target_pk_type.non_null,
                        validators=[rel_item_exists],
                        description=doc,
                    )
            else:
                # To-many is a non-null list of non-null objects.
                field_type = magql.NonNull(target_name).list.non_null
                object.fields[key] = magql.Field(field_type, description=doc)
                # The input list can be empty or null, but the ids are non-null.
                rel_list_exists = ListExistsValidator(
                    target_model, target_pk_name, target_pk_col
                )
                update_args[key] = magql.Argument(
                    target_pk_type.non_null.list,
                    validators=[rel_list_exists],
                    description=doc,
                )
                create_args[key] = magql.Argument(
                    target_pk_type.non_null.list,
                    validators=[rel_list_exists],
                    description=doc,
                )

        self.item_field = magql.Field(
            object,
            args={"id": magql.Argument(pk_type.non_null)},
            resolve=self.item_factory(model),
        )
        self.list_result = magql.Object(
            f"{model_name}ListResult",
            fields={
                "items": magql.Field(object.non_null.list.non_null),
                "total": magql.Field(magql.Int.non_null),
            },
        )
        self.list_field = magql.Field(
            self.list_result.non_null,
            args={
                "filter": magql.Argument(filter_item.non_null.list.non_null.list),
                "sort": magql.Argument(magql.String.non_null.list),
                "page": magql.Argument(magql.Int, validators=[validate_page]),
                "per_page": magql.Argument(magql.Int, validators=[PerPageValidator()]),
            },
            resolve=self.list_factory(model),
        )
        unique_validators = []
        local_table = t.cast(sa.Table, mapper.local_table)

        for constraint in local_table.constraints:
            if not isinstance(constraint, sa.UniqueConstraint):
                continue

            unique_validators.append(
                UniqueValidator(
                    model,
                    constraint.columns,  # type: ignore[arg-type]
                    pk_name,
                    pk_col,
                )
            )

        self.create_field = magql.Field(
            self.object.non_null,
            args=create_args,  # type: ignore[arg-type]
            resolve=self.create_factory(model),
            validators=[*unique_validators],
        )
        self.update_field = magql.Field(
            self.object.non_null,
            args=update_args,  # type: ignore[arg-type]
            resolve=self.update_factory(model),
            validators=[*unique_validators],
        )
        self.delete_field = magql.Field(
            magql.Boolean.non_null,
            args={pk_name: magql.Argument(pk_type.non_null, validators=[item_exists])},
            resolve=self.delete_factory(model),
        )

        if search:
            self.search_provider = ColumnSearchProvider(model)

    def register(self, schema: magql.Schema) -> None:
        """Register this manager's query and mutation fields on the given
        :class:`magql.Schema` instance.

        :param schema: The schema instance to register on.
        """
        name = camel_to_snake_case(self.model.__name__)
        schema.query.fields[f"{name}_item"] = self.item_field
        schema.query.fields[f"{name}_list"] = self.list_field
        schema.mutation.fields[f"{name}_create"] = self.create_field
        schema.mutation.fields[f"{name}_update"] = self.update_field
        schema.mutation.fields[f"{name}_delete"] = self.delete_field

    def register_search(self, search: Search) -> None:
        """If a search provider is enabled for this manager, register it on the given
        :class:`.Search` instance.

        Typically the search instance is managed by the :class:`ModelGroup`, which will
        register it on a schema.

        :param search: The search instance to register on.
        """
        if self.search_provider is not None:
            search.provider(self.search_provider)


def _find_pk(
    model_name: str, columns: sa.ColumnCollection[str, sa.Column[t.Any]]
) -> tuple[str, sa.Column[t.Any]]:
    """Find the first primary key column in a column collection."""
    for name, column in columns.items():
        if column.primary_key:
            return name, column

    # Can happen with __mapper_args__ = {"primary_key": [c]}. If we change to
    # detect this, we can tell coverage to ignore the missed branch.
    raise TypeError(f"No primary key on '{model_name}'.")


def _convert_column_type(
    model_name: str,
    key: str,
    column: sa.Column[t.Any],
    nested_type: TypeEngine[t.Any] | None = None,
) -> magql.nodes.Type:
    """Convert a SQLAlchemy column type to a Magql scalar type.

    :param model_name: The model's name, used when generating an :class:`.Enum`.
    :param key: The column's attribute name, used when generating an :class:`Enum`.
    :param column: The SQLAlchemy column instance.
    :param nested_type: The inner type of a SQLAlchemy ``ARRAY``, used when recursively
        generating a :class:`.List`.
    """

    if nested_type is None:
        ct = column.type
    else:
        ct = nested_type

    # sa.Enum inherits sa.String, must be checked first.
    if isinstance(ct, sa.Enum):
        name = f"{model_name}{key.title()}"

        if ct.enum_class is not None:
            return magql.Enum(name, {k: ct.enum_class[k] for k in ct.enums})

        return magql.Enum(name, ct.enums)

    if isinstance(ct, sa.String):
        return magql.String

    if isinstance(ct, sa.Integer):
        return magql.Int

    if isinstance(ct, sa.Float):
        return magql.Float

    if isinstance(ct, sa.Boolean):
        return magql.Boolean

    if isinstance(ct, sa.DateTime):
        return magql.DateTime

    if isinstance(ct, sa.JSON):
        return magql.JSON

    if isinstance(ct, sa.ARRAY):
        # Convert the item type. Array items are non-null.
        out = _convert_column_type(model_name, key, column, ct.item_type).non_null.list

        # Dimensions > 1 add extra non-null list wrapping.
        for _ in range((ct.dimensions or 1) - 1):
            out = out.non_null.list

        return out

    return magql.String


def camel_to_snake_case(name: str) -> str:
    """Convert a ``CamelCase`` name to ``snake_case``."""
    name = re.sub(r"((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))", r"_\1", name)
    return name.lower().lstrip("_")


def get_obj_doc(obj: type[t.Any]) -> str | None:
    """Return :func:`inspect.cleandoc` on ``obj.__doc__`` if it's set, otherwise
    return None.
    """
    if obj.__doc__ is None:
        return None

    return inspect.cleandoc(obj.__doc__)


def get_attr_docs(cls: type[t.Any]) -> dict[str, str]:
    """Get any docstrings placed after attribute assignments in a class body.
    This is a convention for documenting attributes, but is not exposed in the
    Python runtime. Instead, parse the AST for the source text associated with
    the class. Find string expressions after assignments, and record the value
    for the name. Attributes without docs will not be present in the output.
    """
    cls_node = ast.parse(textwrap.dedent(inspect.getsource(cls))).body[0]

    if not isinstance(cls_node, ast.ClassDef):
        raise TypeError("Given object was not a class.")

    out = {}

    # Consider each pair of nodes to find docs after assignments.
    for a, b in pairwise(cls_node.body):
        # Must be an assignment and a constant string expr.
        if (
            not isinstance(a, ast.Assign | ast.AnnAssign)
            or not isinstance(b, ast.Expr)
            or not isinstance(b.value, ast.Constant)
            or not isinstance(b.value.value, str)
        ):
            continue

        doc = inspect.cleandoc(b.value.value)

        if isinstance(a, ast.Assign):
            # An assignment can have multiple targets (a = b = value). Shouldn't
            # happen with models, but handle it.
            targets = a.targets
        else:
            # An annotated assignment only has one target.
            targets = [a.target]

        for target in targets:
            # Must be assigning to a plain name.
            if not isinstance(target, ast.Name):
                continue

            out[target.id] = doc

    return out
