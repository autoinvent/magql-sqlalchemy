from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .conftest import Task
from .conftest import TPExecute
from .conftest import User

query = """\
query($type: String!, $id: ID!) {
    check_delete(type: $type, id: $id) {
        affected { type id }
        deleted { type id }
        prevented { type id }
    }
}
"""


def test_invalid_type(schema_execute: TPExecute) -> None:
    """An invalid type name will return an input validation error."""
    result = schema_execute(query, variables={"type": "Bad", "id": "1"})
    assert result.errors is not None
    assert len(result.errors) == 1
    assert result.errors[0].message == "magql argument validation"
    assert result.errors[0].extensions is not None
    assert result.errors[0].extensions["type"][0] == "Unknown type 'Bad'."


def test_affected(session: Session, schema_execute: TPExecute) -> None:
    """Deleting a task will show that its user is affected because its tasks
    list will be changed.
    """
    user = User(username="a", tasks=[Task(message="a")])
    session.add(user)
    session.commit()
    result = schema_execute(query, variables={"type": "Task", "id": "1"})
    assert not result.errors
    assert result.data == {
        "check_delete": {
            "affected": [{"type": "User", "id": "1"}],
            "deleted": [],
            "prevented": [],
        }
    }
    session.delete(user.tasks[0])
    session.commit()
    assert len(user.tasks) == 0


def test_affected_many(session: Session, schema_execute: TPExecute) -> None:
    """Deleting a user will show that a task that references it as tagged_user
    is affected instead of prevented, because tagged_user is nullable."""
    task = Task(message="a", user=User(username="a"), tagged_user=User(username="b"))
    session.add(task)
    session.commit()
    result = schema_execute(query, variables={"type": "User", "id": "2"})
    assert not result.errors
    assert result.data == {
        "check_delete": {
            "affected": [{"type": "Task", "id": "1"}],
            "deleted": [],
            "prevented": [],
        }
    }
    session.delete(task.tagged_user)
    session.commit()
    assert task.tagged_user is None


def test_prevented(session: Session, schema_execute: TPExecute) -> None:
    """Deleting a user with tasks will be prevented because the tasks have a
    non-null reference to the user.
    """
    user = User(username="a", tasks=[Task(message="a"), Task(message="b")])
    session.add(user)
    session.commit()
    result = schema_execute(query, variables={"type": "User", "id": "1"})
    assert not result.errors
    assert result.data == {
        "check_delete": {
            "affected": [],
            "deleted": [],
            "prevented": [{"type": "Task", "id": "1"}, {"type": "Task", "id": "2"}],
        }
    }
    session.delete(user)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_deleted(session: Session, schema_execute: TPExecute) -> None:
    """Deleting a parent task shows its child is deleted because the
    relationship has delete cascade enabled. The user is also affected.
    """
    user = User(username="a")
    session.add(
        Task(message="child", user=user, parent=Task(message="parent", user=user))
    )
    session.commit()
    result = schema_execute(query, variables={"type": "Task", "id": "1"})
    assert not result.errors
    assert result.data == {
        "check_delete": {
            "affected": [{"type": "User", "id": "1"}],
            "deleted": [{"type": "Task", "id": "2"}],
            "prevented": [],
        }
    }
    session.delete(user.tasks[0])
    session.commit()
    assert len(user.tasks) == 0


def test_many_empty(session: Session, schema_execute: TPExecute) -> None:
    """If a to-many collection is empty, the check stops early."""
    session.add(User(username="a"))
    session.commit()
    result = schema_execute(query, variables={"type": "User", "id": "1"})
    assert result.data == {
        "check_delete": {"affected": [], "deleted": [], "prevented": []}
    }
