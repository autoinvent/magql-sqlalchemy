from __future__ import annotations

import typing as t
from datetime import datetime
from datetime import timezone

import graphql
import magql
import pytest
import sqlalchemy as sa
import sqlalchemy.orm as sa_orm
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
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    tasks: Mapped[list[Task]] = relationship(
        foreign_keys="Task.user_id", back_populates="user"
    )
    tagged_tasks: Mapped[list[Task]] = relationship(
        foreign_keys="Task.tagged_user_id", back_populates="tagged_user"
    )

    def __str__(self):
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
        collection_class=column_keyed_dict(message),  # pyright: ignore
    )

    def __str__(self):
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


class TPExecute(t.Protocol):
    def __call__(
        self, source: str, variables: dict[str, t.Any] | None = None
    ) -> graphql.ExecutionResult:
        ...


@pytest.fixture()
def schema_execute(session: sa_orm.Session) -> TPExecute:
    def schema_execute(
        source: str, variables: dict[str, t.Any] | None = None
    ) -> graphql.ExecutionResult:
        return schema.execute(
            source, variables=variables, context={"sa_session": session}
        )

    return schema_execute
