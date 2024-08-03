from __future__ import annotations

import pytest
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session

from magql_sqlalchemy import ModelGroup
from magql_sqlalchemy import ModelManager

from .conftest import Execute
from .conftest import Model
from .conftest import Task
from .conftest import User


@pytest.mark.parametrize("search", [True, False])
def test_manager_enable(search: bool) -> None:
    manager = ModelManager(User, search=search)
    assert (manager.search_provider is not None) is search


@pytest.mark.parametrize("search", [True, False])
def test_group_enable_all(search: bool) -> None:
    group = ModelGroup.from_declarative_base(Model, search=search)
    assert all(
        (m.search_provider is not None) is search for m in group.managers.values()
    )


@pytest.mark.parametrize("ref", [User, "User"])
def test_group_enable_some(ref: type[DeclarativeBase] | str) -> None:
    group = ModelGroup.from_declarative_base(Model, search={ref})
    assert group.managers["User"].search_provider is not None
    assert group.managers["Task"].search_provider is None


def test_search(session: Session, execute: Execute) -> None:
    session.add(Task(message="test magql", user=User(username="magql")))
    session.commit()
    result = execute.expect_data("""{ search(value: "gql") { type id value } }""")
    assert result == {
        "search": [
            {"type": "User", "id": "1", "value": "magql"},
            {"type": "Task", "id": "1", "value": "test magql"},
        ]
    }
