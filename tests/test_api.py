import pytest
from sqlalchemy.orm import Session

from .conftest import Execute
from .conftest import Task
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


def test_item(execute: Execute) -> None:
    result = execute.expect_data("{ user_item(id: 1) { id username _display_value } }")
    assert result == {"user_item": {"id": 1, "username": "a", "_display_value": "a"}}


def test_item_missing(execute: Execute) -> None:
    """Missing item returns None."""
    result = execute.expect_data("{ user_item(id: 100) { id username } }")
    assert result == {"user_item": None}


def test_list(execute: Execute) -> None:
    result = execute.expect_data("{ task_list { items { id message } total } }")
    data = result["task_list"]
    items = data["items"]
    assert data["total"] == 101
    assert len(items) == 10
    # The first few items sorted by id.
    assert items[0]["id"] == 1
    assert items[1]["id"] == 2


def test_filter_path(execute: Execute) -> None:
    """Filter across relationship."""
    result = execute.expect_data(
        '{ task_list(filter: { path: "user.username", op: "eq", value: "ex1" })'
        " { items { message } } }"
    )
    items = result["task_list"]["items"]
    assert len(items) == 1
    assert items[0]["message"] == "ex1"


def test_sort_path(execute: Execute) -> None:
    """Sort across relationship."""
    result = execute.expect_data(
        '{ task_list(sort: ["-user.username", "-message"]) { items { id message } } }'
    )
    items = result["task_list"]["items"]
    assert items[0]["message"] == "ex1"
    assert items[1]["message"] == "a99"


def test_create(execute: Execute) -> None:
    result = execute.expect_data(
        """mutation { task_create(message: "b", user: 1) { id } }"""
    )
    task_id = result["task_create"]["id"]
    execute.expect_data(
        "query($id: Int!) { task_item(id: $id) { id } }",
        variables={"id": task_id},
    )


def test_update(execute: Execute) -> None:
    execute.expect_data(
        """mutation { task_update(id: 1, message: "updated") { id } }"""
    )
    result = execute.expect_data("{ task_item(id: 1) { id message } }")
    assert result == {"task_item": {"id": 1, "message": "updated"}}


def test_delete(execute: Execute) -> None:
    result = execute.expect_data("""mutation { task_delete(id: 1) }""")
    assert result == {"task_delete": True}
    result = execute.expect_data("{ task_item(id: 1) { id } }")
    assert result == {"task_item": None}
