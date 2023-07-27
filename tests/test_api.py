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
    result = schema_execute("{ user_item(id: 1) { id username } }")
    assert result.errors is None
    assert result.data == {"user_item": {"id": 1, "username": "a"}}


def test_item_missing(schema_execute: TPExecute) -> None:
    """Missing item returns None."""
    result = schema_execute("{ user_item(id: 100) { id username } }")
    assert result.errors is None
    assert result.data == {"user_item": None}


def test_list(schema_execute: TPExecute) -> None:
    result = schema_execute("{ task_list { items { id } total } }")
    assert result.errors is None
    assert result.data is not None
    assert result.data["task_list"]["total"] == 101
    assert len(result.data["task_list"]["items"]) == 10


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
