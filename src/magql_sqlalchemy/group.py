from __future__ import annotations

import magql
from magql.search import Search
from sqlalchemy import orm as sa_orm

from .check_delete import CheckDelete
from .manager import ModelManager


class ModelGroup:
    """Collects multiple model managers and manages higher-level APIs such as search and
    check delete.

    Typically there will be one group for all the models. If more than one group is used
    for some reason, the field names for its :attr:`search` and :attr:`check_delete`
    instances should be changed.

    :param managers: The model managers that are part of this group.
    """

    def __init__(self, managers: list[ModelManager] | None = None) -> None:
        self.managers: dict[str, ModelManager] = {}
        """Maps SQLAlchemy model names to their :class:`ModelManager` instance. Use
        :meth:`add_manager` to add to this.
        """

        self.search: Search = Search()
        """The :class:`.Search` instance model providers will be registered on."""

        self.check_delete: CheckDelete = CheckDelete(self.managers)
        """The :class:`.CheckDelete` instance models will be registered on."""

        if managers is not None:
            for manager in managers:
                self.add_manager(manager)

    @classmethod
    def from_declarative_base(
        cls,
        base: type[sa_orm.DeclarativeBase] | sa_orm.DeclarativeMeta,
        *,
        search: (
            bool | set[type[sa_orm.DeclarativeBase] | sa_orm.DeclarativeMeta | str]
        ) = True,
    ) -> ModelGroup:
        """Create a group of model managers for all models in the given SQLAlchemy
        declarative base class.

        :param base: The SQLAlchemy declarative base class.
        :param search: A bool to enable or disable search for all models. Or a
            set of models or names.
        """
        managers = []

        for mapper in base.registry.mappers:
            model = mapper.class_

            if isinstance(search, set):
                model_search = model in search or model.__name__ in search
            else:
                model_search = search

            managers.append(ModelManager(model, search=model_search))

        return cls(managers)

    def add_manager(self, manager: ModelManager) -> None:
        """Add another model manager after the group was created.

        :param manager: The model manager to add.
        """
        self.managers[manager.model.__name__] = manager

    def register(self, schema: magql.Schema) -> None:
        """Register this group's managers and APIs on the given
        :class:`magql.Schema` instance.

        :param schema: The schema instance to register on.
        """
        for manager in self.managers.values():
            manager.register(schema)
            manager.register_search(self.search)

        self.search.register(schema)
        self.check_delete.register(schema)
