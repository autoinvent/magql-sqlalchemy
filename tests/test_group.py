from __future__ import annotations

import magql

from .conftest import Model
from .conftest import task_manager
from .conftest import user_manager
from magql_sqlalchemy import ModelGroup


def test_managers_init() -> None:
    """Managers can be added while creating the group."""
    group = ModelGroup([user_manager, task_manager])
    assert group.managers.keys() == {"User", "Task"}


def test_add_manager() -> None:
    """Managers can be added after creating the group."""
    group = ModelGroup()
    group.add_manager(user_manager)
    group.add_manager(task_manager)
    assert group.managers.keys() == {"User", "Task"}


def test_register() -> None:
    """After registering a group, the expected types and fields are present in
    the schema.
    """
    schema = magql.Schema()
    group = ModelGroup.from_declarative_base(Model, search={"User"})
    group.register(schema)
    schema._find_nodes()
    assert schema.type_map.keys() >= {
        "User",
        "UserListResult",
        "Task",
        "TaskListResult",
        "FilterItem",
        "SearchResult",
        "CheckDeleteResult",
    }
    assert schema.query.fields.keys() == {
        "user_item",
        "user_list",
        "task_item",
        "task_list",
        "search",
        "check_delete",
    }
    assert schema.mutation.fields.keys() == {
        "user_create",
        "user_update",
        "user_delete",
        "task_create",
        "task_update",
        "task_delete",
    }
