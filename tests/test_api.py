import pytest
from sqlalchemy.orm import Session

from .conftest import Task
from .conftest import TPExecute
from .conftest import User


@pytest.fixture(autouse=True)
def _populate_db(session: Session) -> None:
    users = [
        User(username="a", tasks=[Task(message=f"a{i}") for i in range(100)]),
        User(username="ex1", tasks=[Task(message="ex1")]),
    ]
    users[1].tasks[0].tagged_user = users[0]
    session.add_all(users)
    session.commit()


def test_item(schema_execute: TPExecute) -> None:
    result = schema_execute("{ user_item(id: 1) { id username _display_value } }")
    assert result.errors is None
    assert result.data == {
        "user_item": {"id": 1, "username": "a", "_display_value": "a"}
    }


def test_item_missing(schema_execute: TPExecute) -> None:
    """Missing item returns None."""
    result = schema_execute("{ user_item(id: 100) { id username } }")
    assert result.errors is None
    assert result.data == {"user_item": None}


def test_list(schema_execute: TPExecute) -> None:
    result = schema_execute("{ task_list { items { id message } total } }")
    assert result.errors is None
    assert result.data is not None
    data = result.data["task_list"]
    items = data["items"]
    assert data["total"] == 101
    assert len(items) == 10
    # The first few items sorted by id.
    assert items[0]["id"] == 1
    assert items[1]["id"] == 2


def test_filter_path(schema_execute: TPExecute) -> None:
    """Filter across relationship."""
    result = schema_execute(
        '{ task_list(filter: { path: "user.username", op: "eq", value: "ex1" })'
        " { items { message } } }"
    )
    assert result.errors is None
    assert result.data is not None
    items = result.data["task_list"]["items"]
    assert len(items) == 1
    assert items[0]["message"] == "ex1"


def test_sort_path(schema_execute: TPExecute) -> None:
    """Sort across relationship."""
    result = schema_execute(
        '{ task_list(sort: ["-user.username", "-message"]) { items { id message } } }'
    )
    assert result.errors is None
    assert result.data is not None
    items = result.data["task_list"]["items"]
    assert items[0]["message"] == "ex1"
    assert items[1]["message"] == "a99"


def test_create(schema_execute: TPExecute) -> None:
    result = schema_execute(
        """mutation { task_create(message: "b", user: 1) { id } }"""
    )
    assert result.errors is None
    assert result.data is not None
    task_id = result.data["task_create"]["id"]
    result = schema_execute(
        "query($id: Int!) { task_item(id: $id) { id } }",
        variables={"id": task_id},
    )
    assert result.data is not None


def test_update(schema_execute: TPExecute) -> None:
    result = schema_execute(
        """mutation { task_update(id: 1, message: "updated") { id } }"""
    )
    assert result.errors is None
    result = schema_execute("{ task_item(id: 1) { id message } }")
    assert result.errors is None
    assert result.data == {"task_item": {"id": 1, "message": "updated"}}


def test_delete(schema_execute: TPExecute) -> None:
    result = schema_execute("""mutation { task_delete(id: 1) }""")
    assert result.errors is None
    assert result.data == {"task_delete": True}
    result = schema_execute("{ task_item(id: 1) { id } }")
    assert result.errors is None
    assert result.data == {"task_item": None}
