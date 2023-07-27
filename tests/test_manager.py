from __future__ import annotations

import enum
import typing as t
import uuid
from datetime import datetime

import magql
import pytest
import sqlalchemy as sa
import sqlalchemy.orm as sa_orm
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from .conftest import task_manager
from .conftest import User
from .conftest import user_manager
from magql_sqlalchemy import ModelManager
from magql_sqlalchemy.manager import camel_to_snake_case


def test_object() -> None:
    """The generated Object has expected properties."""
    type = user_manager.object
    assert type.name == "User"
    assert type.fields.keys() == {"id", "username", "tasks", "tagged_tasks"}
    task_type = type.fields["tasks"].type
    assert isinstance(task_type, magql.NonNull)
    assert isinstance(task_type.type, magql.List)
    assert isinstance(task_type.type.type, magql.NonNull)
    assert task_type.type.type.type == task_manager.object


def test_item_field() -> None:
    """The generated item Field has expected properties."""
    field = user_manager.item_field
    assert field.type is user_manager.object
    assert field.args.keys() == {"id"}
    assert field.args["id"].type is magql.Int.non_null


def test_list_field() -> None:
    """The generated list Field has expected properties."""
    type = user_manager.list_result
    assert type.fields.keys() == {"items", "total"}
    assert type.fields["items"].type is user_manager.object.non_null.list.non_null
    field = user_manager.list_field
    assert field.type is type.non_null
    assert field.args.keys() == {"filter", "sort", "page", "per_page"}


def test_create_field() -> None:
    """The generated create Field has expected properties."""
    field = user_manager.create_field
    assert field.type is user_manager.object.non_null
    assert field.args.keys() == {"username", "tasks", "tagged_tasks"}
    assert field.args["username"].type is magql.String.non_null


def test_update_field() -> None:
    """The generated update Field has expected properties."""
    field = user_manager.update_field
    assert field.type is user_manager.object.non_null
    assert field.args.keys() == {"id", "username", "tasks", "tagged_tasks"}
    assert field.args["id"].type == magql.Int.non_null
    assert field.args["username"].type is magql.String


def test_delete_field() -> None:
    """The generated delete Field has expected properties."""
    field = user_manager.delete_field
    assert field.type is magql.Boolean.non_null
    assert field.args.keys() == {"id"}
    assert field.args["id"].type == magql.Int.non_null


def test_register() -> None:
    """After registering a manager, the expected types and fields are present in
    the schema.
    """
    schema = magql.Schema()
    user_manager = ModelManager(User)
    user_manager.register(schema)
    schema._find_nodes()
    assert schema.type_map.keys() >= {"User", "UserListResult", "FilterItem", "Task"}
    assert schema.type_map["Task"] is None
    query_keys = schema.query.fields.keys()
    assert query_keys == {"user_item", "user_list"}
    mut_keys = schema.mutation.fields.keys()
    assert mut_keys == {"user_create", "user_update", "user_delete"}


@pytest.mark.parametrize(
    ("value", "expect"),
    [
        ("One", "one"),
        ("ONE", "one"),
        ("OneTwo", "one_two"),
        ("ONETwo", "one_two"),
        ("1Two", "1_two"),
        ("One2", "one2"),
        ("One2Three", "one2_three"),
        ("OneTWOThree", "one_two_three"),
    ],
)
def test_camel_to_snake_case(value: str, expect: str) -> None:
    """Different camel case examples will convert to snake case correctly."""
    assert camel_to_snake_case(value) == expect


# Must be defined at the module level so Mapped annotation can be resolved.
class Color(enum.Enum):
    red = enum.auto()
    green = enum.auto()
    blue = enum.auto()


def test_convert_type():
    """Check each SQLAlchemy type that can be converted to a Magql type."""

    class Model(sa_orm.DeclarativeBase):
        pass

    class Node(Model):
        __tablename__ = "node"
        id: Mapped[int] = mapped_column(primary_key=True)
        str_data: Mapped[str | None]
        int_data: Mapped[int | None]
        float_data: Mapped[float | None]
        bool_data: Mapped[bool | None]
        datetime_data: Mapped[datetime | None]
        json_data: Mapped[t.Any | None] = mapped_column(sa.JSON)
        enum_data: Mapped[Color | None]
        literal_data: Mapped[t.Literal["a", "b", "c"] | None]
        choices_data: Mapped[str | None] = mapped_column(sa.Enum("d", "e", "f"))
        array_data: Mapped[list[int] | None] = mapped_column(sa.ARRAY(sa.Integer))
        nested_data: Mapped[list[list[int]] | None] = mapped_column(
            sa.ARRAY(sa.Integer, dimensions=2)
        )
        uuid_data: Mapped[uuid.UUID | None]

    node_manager = ModelManager(Node)
    fields = node_manager.object.fields
    assert fields["id"].type is magql.Int.non_null
    assert fields["str_data"].type is magql.String
    assert fields["int_data"].type is magql.Int
    assert fields["float_data"].type is magql.Float
    assert fields["bool_data"].type is magql.Boolean
    assert fields["datetime_data"].type is magql.DateTime
    assert fields["json_data"].type is magql.JSON
    assert isinstance(fields["enum_data"].type, magql.Enum)
    assert isinstance(fields["literal_data"].type, magql.Enum)
    assert isinstance(fields["choices_data"].type, magql.Enum)
    assert fields["array_data"].type is magql.Int.non_null.list
    assert fields["nested_data"].type is magql.Int.non_null.list.non_null.list
    # Unknown SQLAlchemy type, fall back to String
    assert fields["uuid_data"].type is magql.String


def test_no_primary_key_column():
    """We don't know how to convert a model that does not have a column marked
    as primary key directly.
    """

    class Model(sa_orm.DeclarativeBase):
        pass

    class Node(Model):
        __tablename__ = "node"
        v1: Mapped[str] = mapped_column()
        __mapper_args__ = {"primary_key": [v1]}

    with pytest.raises(TypeError):
        ModelManager(Node)
