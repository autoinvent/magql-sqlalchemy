from __future__ import annotations

import typing as t

import sqlalchemy as sa
import sqlalchemy.orm as sa_orm
from magql.search import SearchResult


class ColumnSearchProvider:
    """A search provider for :class:`.Search` which checks if any string columns in the
    given SQLAlchemy model contains the case-insensitive search value.

    This is generated by :class:`.ModelManager` if search is enabled for that model.

    :param model: SQLAlchemy model class.
    """

    def __init__(self, model: type[t.Any]) -> None:
        self.model = model
        """The SQLAlchemy model being searched."""

        self.columns: list[sa.Column[t.Any]] = find_string_columns(model)
        """The columns to search in."""

    def __call__(self, context: t.Any, value: str) -> list[SearchResult]:
        session: sa_orm.Session = context["sa_session"]
        value = prepare_contains(value)
        query = sa.select(self.model).filter(
            sa.or_(*(c.ilike(value, escape="/") for c in self.columns))
        )
        model_name = self.model.__name__
        return [
            SearchResult(
                type=model_name, id=sa.inspect(item).identity[0], value=str(item)
            )
            for item in session.execute(query).scalars()
        ]


def find_string_columns(model: type[t.Any]) -> list[sa.Column[t.Any]]:
    """Find all columns that can be searched using ``LIKE``.

    :param model: SQLAlchemy model class.
    """
    columns = sa.inspect(model).columns
    return [c for c in columns if isinstance(c.type, sa.String)]


def prepare_contains(value: str) -> str:
    """Prepare a search string for SQL ``LIKE`` from user input. ``%`` and ``_``
    wildcard characters will be escaped with ``/``.

    :param value: Search value.
    """
    value = value.replace("/", "//").replace("%", "/%").replace("_", "/_")
    return f"%{value}%"
