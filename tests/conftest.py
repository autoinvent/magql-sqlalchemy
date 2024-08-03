from __future__ import annotations

import typing as t
from datetime import datetime
from datetime import timezone

import graphql
import magql
import pytest
import sqlalchemy as sa
import sqlalchemy.orm as sa_orm
from magql.testing import expect_data
from magql.testing import expect_error
from magql.testing import expect_errors
from magql.testing import expect_validation_error
from sqlalchemy.orm import column_keyed_dict
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from magql_sqlalchemy import ModelGroup
from magql_sqlalchemy import ModelManager


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Model(sa_orm.DeclarativeBase):
    pass


class User(Model):
    """A user."""

    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    """The unique name used to log in the user."""
    tasks: Mapped[list[Task]] = relationship(
        foreign_keys="Task.user_id", back_populates="user"
    )
    tagged_tasks: Mapped[list[Task]] = relationship(
        foreign_keys="Task.tagged_user_id", back_populates="tagged_user"
    )
    """Tasks that this user is tagged in."""

    def __str__(self) -> str:
        return self.username


class Task(Model):
    __tablename__ = "task"
    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column()
    done: Mapped[bool] = mapped_column(default=False)
    group: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=now_utc)
    done_at: Mapped[datetime | None]
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("user.id"))
    user: Mapped[User] = relationship(foreign_keys=user_id, back_populates="tasks")
    tagged_user_id: Mapped[int | None] = mapped_column(sa.ForeignKey("user.id"))
    tagged_user: Mapped[User | None] = relationship(
        foreign_keys=tagged_user_id, back_populates="tagged_tasks"
    )
    parent_id: Mapped[int | None] = mapped_column(sa.ForeignKey("task.id"))
    parent: Mapped[Task | None] = relationship(
        foreign_keys=parent_id, remote_side=id, back_populates="children"
    )
    children: Mapped[dict[str, Task]] = relationship(
        back_populates="parent",
        cascade="all",
        collection_class=column_keyed_dict(message),  # type: ignore[arg-type]
    )

    def __str__(self) -> str:
        return self.message


user_manager = ModelManager(User, search=True)
task_manager = ModelManager(Task, search=True)
group = ModelGroup([user_manager, task_manager])
schema = magql.Schema()
group.register(schema)
schema._find_nodes()

engine = sa.create_engine("sqlite://")
Model.metadata.create_all(engine)


@pytest.fixture()
def session() -> t.Generator[sa_orm.Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = sa_orm.Session(connection)
    yield session
    session.close()
    transaction.close()
    connection.close()


class Execute:
    def __init__(self, session: sa_orm.Session) -> None:
        self._context = {"sa_session": session}

    def expect_data(self, source: str, **kwargs: t.Any) -> dict[str, t.Any]:
        return expect_data(schema, source, context=self._context, **kwargs)

    def expect_errors(self, source: str, **kwargs: t.Any) -> list[graphql.GraphQLError]:
        return expect_errors(schema, source, context=self._context, **kwargs)

    def expect_error(self, source: str, **kwargs: t.Any) -> graphql.GraphQLError:
        return expect_error(schema, source, context=self._context, **kwargs)

    def expect_validation_error(self, source: str, **kwargs: t.Any) -> dict[str, t.Any]:
        return expect_validation_error(schema, source, context=self._context, **kwargs)


@pytest.fixture()
def execute(session: sa_orm.Session) -> Execute:
    return Execute(session)
