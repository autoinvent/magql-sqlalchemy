from __future__ import annotations

import dataclasses
import typing as t

import graphql
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy import sql
from sqlalchemy.engine import Result

from . import filters

M = t.TypeVar("M", bound=orm.DeclarativeBase)


class ModelResolver(t.Generic[M]):
    """Base class for the SQLAlchemy model API resolvers used by :class:`.ModelManager`.
    Subclasses must implement ``__call__``.

    A resolver is for a specific model, and does some introspection on the model to
    know what the mapper and primary key are.

    In order to execute the SQL expression, ``info.context`` must be a dict with the
    key ``sa_session` set to the SQLAlchemy session.
    """

    def __init__(self, model: type[M]) -> None:
        from .manager import _find_pk

        self.model = model
        self._mapper: orm.Mapper[M] = sa.inspect(model)
        self.pk_name: str
        self.pk_col: sa.Column[t.Any]
        self.pk_name, self.pk_col = _find_pk(self.model.__name__, self._mapper.columns)

    def _load_relationships(
        self,
        info: graphql.GraphQLResolveInfo,
        node: graphql.FieldNode
        | graphql.FragmentDefinitionNode
        | graphql.InlineFragmentNode,
        model: type[t.Any],
        load_path: orm.Load | None = None,
    ) -> list[orm.Load]:
        """Given the AST node representing the GraphQL operation, find all the
        SQLAlchemy relationships that should be eagerly loaded, recursively, and
        generate load expressions for them. This makes resolving the graph very
        efficient by letting SQLAlchemy preload related data rather than issuing
        individual queries for every attribute access.

        :param info: The GraphQL info about the operation, which contains the
            fragment references.
        :param node: The AST node being inspected.
        :param model: The model containing the relationships. Starts as the model for
            this resolver, then the relationship's target model during recursion.
        :param load_path: During recursion, the SQLAlchemy load that has been performed
            to get to this relationship and should be extended.

        .. versionchanged:: 1.1
            Handle fragments.
        """
        if node.selection_set is None:
            return []

        out = []

        for selection in node.selection_set.selections:
            if isinstance(selection, graphql.FragmentSpreadNode):
                # Fragments are an extra nested level. Find the definition,
                # recurse, then continue.
                fragment = info.fragments[selection.name.value]
                out.extend(self._load_relationships(info, fragment, model, load_path))
                continue

            if isinstance(selection, graphql.InlineFragmentNode):
                # Inline fragments are an extra nested level. Recurse, then continue.
                out.extend(self._load_relationships(info, selection, model, load_path))
                continue

            inner_node = t.cast(graphql.FieldNode, selection)

            # Only consider AST nodes for relationships, which are ones with further
            # selections for the object's fields.
            if inner_node.selection_set is None:
                continue

            field_name = inner_node.name.value
            mapper = sa.inspect(model)
            rel_prop = mapper.relationships.get(field_name)

            if rel_prop is None:
                # This somehow isn't a relationship even though it's an object type.
                # Could happen if a custom extra field+resolver was added.
                continue

            rel_attr = rel_prop.class_attribute

            if load_path is None:
                # At the base level, start a new load expression.
                extended_path = t.cast(orm.Load, orm.selectinload(rel_attr))
            else:
                # Recursion, extend the existing load expression.
                extended_path = load_path.selectinload(rel_attr)

            # Recurse to find any relationship fields selected in the child object.
            out.extend(
                self._load_relationships(
                    info, inner_node, rel_prop.entity.class_, extended_path
                )
            )

        if not out:
            if load_path is not None:
                # This was a relationship, and there were no child relationships.
                return [load_path]

            # There were no relationships selected at all.
            return []

        # There were child relationships, and this is the full collection.
        return out

    def __call__(
        self, parent: t.Any, info: graphql.GraphQLResolveInfo, **kwargs: t.Any
    ) -> t.Any:
        raise NotImplementedError


class QueryResolver(ModelResolver[M]):
    """Base class for SQLAlchemy model API queries used by :class:`.ModelManager`.
    Subclasses must implement :meth:`build_query` and :meth:`transform_result`, and can
    override ``__call__``.
    """

    def build_query(
        self, parent: t.Any, info: graphql.GraphQLResolveInfo, **kwargs: t.Any
    ) -> sql.Select[tuple[M]]:
        """Build the query to execute."""
        raise NotImplementedError

    def transform_result(self, result: Result[tuple[M]]) -> t.Any:
        """Get the model instance or list of instances from a SQLAlchemy result."""
        raise NotImplementedError

    def __call__(
        self, parent: t.Any, info: graphql.GraphQLResolveInfo, **kwargs: t.Any
    ) -> t.Any:
        """Build and execute the query, then return the result."""
        query = self.build_query(parent, info, **kwargs)
        session = _get_sa_session(info)
        result = session.execute(query)
        return self.transform_result(result)


class ItemResolver(QueryResolver[M]):
    """Get a single row from the database by id. Used by
    :attr:`.ModelManager.item_field`. ``id`` is the only GraphQL argument. Returns a
    single model instance, or ``None`` if the id wasn't found.

    :param model: The SQLAlchemy model.
    """

    def build_query(
        self, parent: t.Any, info: graphql.GraphQLResolveInfo, **kwargs: t.Any
    ) -> sql.Select[tuple[M]]:
        field_node = _get_field_node(info)
        load = self._load_relationships(info, field_node, self.model)
        return (
            sa.select(self.model)
            .options(*load)
            .where(self.pk_col == kwargs[self.pk_name])
        )

    def transform_result(self, result: Result[tuple[M]]) -> t.Any:
        return result.scalar_one_or_none()


class ListResolver(QueryResolver[M]):
    """Get a list of rows from the database, with support for filtering, sorting, and
    pagination. If any relationships, arbitrarily nested, are selected, they are
    eagerly loaded to Used by :attr:`.ModelManager.list_field`. Returns a
    :class:`ListResult`, which has the list of model instances selected for this page,
    as well as the total available rows.

    Pagination is always applied to the query to avoid returning thousands of results at
    once for large data sets. The default ``page`` is 1. The default ``per_page`` is
    10, with a max of 100.

    The ``sort`` argument is a list of column names from the :attr:`.ModelManager.sort`
    enum. By default the rows are sorted by their primary key column, otherwise the
    order wouldn't be guaranteed consistent across pages. A name that begins with ``-``
    sorts in descending order.

    Filtering applies one or more filter rules to the query. The ``filter`` argument is
    a list of lists of rules. Each rule is a ``{path, op, not, value}`` dict. The rules
    in a list will be combined with ``AND``, and the lists will be combined with ``OR``.
    The ``path`` in a rule is the name of a column attribute on the model like ``name``,
    or a dotted path to an arbitrarily nested relationship's column like
    ``user.friend.color.name``. Different ``op`` names are available based on the
    column's type. The ``value`` can be any JSON data that the op understands. Most ops
    support a list of values in addition to a single value. See
    :func:`apply_filter_item` and :data:`.type_ops`.

    If any relationships are selected anywhere in the GraphQL query, SQLAlchemy eager
    loads are generated them. This makes resolving the graph very efficient by letting
    SQLAlchemy preload related data rather than issuing individual queries for every
    attribute access.

    :param model: The SQLAlchemy model.
    """

    def apply_filter(
        self,
        query: sql.Select[tuple[M]],
        filter_arg: list[list[dict[str, t.Any]]] | None,
    ) -> sql.Select[tuple[M]]:
        if not filter_arg:
            return query

        # TODO use aliases to support filtering on different paths to the same model
        or_clauses = []

        for filter_group in filter_arg:
            and_clauses = []

            for filter_item in filter_group:
                query, col = self._process_join_path(filter_item["path"], query)
                clause = filters.apply_filter_item(col, filter_item)
                and_clauses.append(clause)

            or_clauses.append(sa.and_(*and_clauses))

        return query.filter(sa.or_(*or_clauses))

    def apply_sort(
        self, query: sql.Select[tuple[M]], sort_arg: list[str] | None = None
    ) -> sql.Select[tuple[M]]:
        if not sort_arg:
            return query.order_by(self.pk_col)

        out = []

        for sort_item in sort_arg:
            if desc := sort_item[0] == "-":
                sort_item = sort_item[1:]

            query, col = self._process_join_path(sort_item, query)

            if not desc:
                out.append(col.asc())
            else:
                out.append(col.desc())

        return query.order_by(*out)

    def _process_join_path(
        self, path: str, query: sql.Select[tuple[M]]
    ) -> tuple[sql.Select[tuple[M]], sa.Column[t.Any]]:
        """A filter or sort path may be a dotted path across one or more
        relationships. For example, ``task.user.name``. Given a path, apply any
        joins to get to the related model, then get the referenced column from
        that model.

        :param path: The dotted path to process, like `task.user.name`.
        :param query: The query to apply joins to.
        :return: The new query, and the indicated column.
        """
        path, _, name = path.rpartition(".")
        mapper = self._mapper

        if path:
            for path_part in path.split("."):
                rel = mapper.relationships[path_part]
                mapper = rel.mapper
                query = query.join(rel.class_attribute)

        col = mapper.columns[name]
        return query, col

    def apply_page(
        self,
        query: sql.Select[tuple[M]],
        page: t.Any | None,
        per_page: int | None,
    ) -> sql.Select[tuple[M]]:
        if page is None:
            page = 1

        if per_page is None:
            per_page = 10

        per_page = min(per_page, 100)
        return query.offset((page - 1) * per_page).limit(per_page)

    def build_query(
        self, parent: t.Any, info: graphql.GraphQLResolveInfo, **kwargs: t.Any
    ) -> sql.Select[tuple[M]]:
        field_node = _get_field_node(info, list_name="items")
        load = self._load_relationships(info, field_node, self.model)
        query = sa.select(self.model).options(*load)
        query = self.apply_filter(query, kwargs.get("filter"))
        query = self.apply_sort(query, kwargs.get("sort"))
        query = self.apply_page(query, kwargs.get("page"), kwargs.get("per_page"))
        return query

    def get_items(self, session: orm.Session, query: sql.Select[tuple[M]]) -> list[M]:
        result = session.execute(query)
        return result.scalars().all()  # type: ignore[return-value]

    def get_count(self, session: orm.Session, query: sql.Select[tuple[M]]) -> int:
        """After generating the query with any filters, get the total row count for
        pagination purposes. Remove any eager loads, sorts, and pagination, then execute
        a SQL ``count()`` query.

        :param session: The SQLAlchemy session.
        :param query: The fully constructed list query.
        """
        sub = (
            query.options(orm.lazyload("*"))
            .order_by(None)
            .limit(None)
            .offset(None)
            .subquery()
        )
        value = session.execute(sa.select(sa.func.count()).select_from(sub)).scalar()
        return value  # type: ignore[return-value]

    def __call__(
        self, parent: t.Any, info: graphql.GraphQLResolveInfo, **kwargs: t.Any
    ) -> t.Any:
        query = self.build_query(parent, info, **kwargs)
        session = _get_sa_session(info)
        items = self.get_items(session, query)
        total = self.get_count(session, query)
        return ListResult(items=items, total=total)


@dataclasses.dataclass()
class ListResult(t.Generic[M]):
    """The return value for :class:`ListResolver` and :attr:`.ModelManager.list_field`.
    :attr:`.ModelManager.list_result` is the Magql type corresponding to this Python
    type.
    """

    items: list[M]
    """The list of model instances for this page."""

    total: int
    """The total number of rows if pagination was not applied."""


def _get_field_node(
    info: graphql.GraphQLResolveInfo, list_name: str | None = None
) -> graphql.FieldNode:
    """Get the node that describes the fields being selected by the current
    query. The returned node's AST is later scanned to load any relationships.

    Assumes a single top-level field.

    :param info: The GraphQL info about the operation, which contains the AST.
    :param list_name: For a list query, the name of the field containing the
        list of results. Should be ``"items"``.

    .. versionchanged:: 1.1
        Handle fragments.
    """
    node = info.field_nodes[0]
    # TODO handle multiple top-level fields

    # For a list query, the items field is nested in the list result type.
    if list_name is not None:
        return _get_list_root(info, node, list_name)

    # Don't need to handle fragments here because top-level fragments like
    # `query { ...fragment }` are already dereferenced in info.field_nodes.
    return node


def _get_list_root(
    info: graphql.GraphQLResolveInfo,
    node: graphql.FieldNode
    | graphql.FragmentDefinitionNode
    | graphql.InlineFragmentNode,
    name: str,
) -> graphql.FieldNode:
    """Scan the selected fields within a node to find the items field in a list
    result type. Handle fragments by recursively scanning through references.

    :param info: The GraphQL info about the operation, which contains the
        fragment references.
    :param node: The node being scanned.
    :param name: The name of the field containing the list of results.

    .. versionadded:: 1.1
        Added for easier recursion when handling fragments.
    """
    assert node.selection_set is not None

    for selection in node.selection_set.selections:
        if isinstance(selection, graphql.FragmentSpreadNode):
            # Fragments are an extra nested level, recurse.
            fragment = info.fragments[selection.name.value]
            result = _get_list_root(info, fragment, name)

            if result is not fragment:
                return result

        elif isinstance(selection, graphql.InlineFragmentNode):
            # Inline fragments are an extra nested level, recurse.
            result = _get_list_root(info, selection, name)

            if (result := _get_list_root(info, selection, name)) is not selection:
                return result

        else:
            inner_node = t.cast(graphql.FieldNode, selection)

            if inner_node.name.value == name:
                return inner_node

    # Don't know how to inspect this node further, return it directly.
    # This cast will eventually be right when recursion ends.
    return t.cast(graphql.FieldNode, node)


class MutationResolver(ModelResolver[M]):
    """Base class for SQLAlchemy model API mutations used by :class:`.ModelManager`.
    Subclasses must implement ``__call__``.
    """

    def get_item(self, info: graphql.GraphQLResolveInfo, kwargs: dict[str, t.Any]) -> M:
        """Get the model instance by primary key value."""
        session = _get_sa_session(info)
        field_node = _get_field_node(info)
        load = self._load_relationships(info, field_node, self.model)
        return session.execute(
            sa.select(self.model)
            .options(*load)
            .where(self.pk_col == kwargs[self.pk_name])
        ).scalar_one()

    def prepare_item(
        self, info: graphql.GraphQLResolveInfo, kwargs: dict[str, t.Any]
    ) -> M:
        """Get and modify the model instance in the SQLAlchemy session, but do
        not commit the session. Calling the resolver calls this and then calls
        commit, but this can be used directly when wrapping the resolver with
        other behavior.

        .. versionadded:: 1.1
        """
        raise NotImplementedError

    def apply_related(self, session: orm.Session, kwargs: dict[str, t.Any]) -> None:
        """For all relationship arguments, replace the id values with their model
        instances.
        """
        from .manager import _find_pk

        for key, rel in self._mapper.relationships.items():
            value = kwargs.get(key)

            # skip missing, None, and empty list values
            if not value:
                continue

            target_model = rel.entity.class_
            target_pk_name, target_pk_col = _find_pk(
                target_model.__name__, rel.mapper.columns
            )

            if rel.direction == orm.MANYTOONE:
                kwargs[key] = session.execute(
                    sa.select(target_model).filter(target_pk_col == value)
                ).scalar_one()
            else:
                kwargs[key] = (
                    session.execute(
                        sa.select(target_model).filter(target_pk_col.in_(value))
                    )
                    .scalars()
                    .all()
                )

    def __call__(
        self, parent: t.Any, info: graphql.GraphQLResolveInfo, **kwargs: t.Any
    ) -> t.Any:
        item = self.prepare_item(info, kwargs)
        session = _get_sa_session(info)
        session.commit()
        return item


class CreateResolver(MutationResolver[M]):
    """Create a new row in the database. Used by :attr:`.ModelManager.create_field`. The
    field has arguments for each of the model's column attributes. An argument is not
    required if its column is nullable or has a default. Unique constraints on will
    already be validated. Returns the new model instance.

    :param model: The SQLAlchemy model.
    """

    def prepare_item(
        self, info: graphql.GraphQLResolveInfo, kwargs: dict[str, t.Any]
    ) -> M:
        session = _get_sa_session(info)
        self.apply_related(session, kwargs)
        item = self.model(**kwargs)
        session.add(item)
        return item


class UpdateResolver(MutationResolver[M]):
    """Updates a row in the database by id. Used by :attr:`.ModelManager.update_field`.
    The field has arguments for each of the model's column attributes. Only the primary
    key argument is required. Columns are only updated if a value is provided, which is
    distinct from setting the value to ``None``. Unique constraints will already be
    validated. Returns the updated model instance.

    :param model: The SQLAlchemy model.
    """

    def prepare_item(
        self, info: graphql.GraphQLResolveInfo, kwargs: dict[str, t.Any]
    ) -> M:
        session = _get_sa_session(info)
        self.apply_related(session, kwargs)
        item = self.get_item(info, kwargs)

        for key, value in kwargs.items():
            if key == self.pk_name:
                continue

            setattr(item, key, value)

        return item


class DeleteResolver(MutationResolver[M]):
    """Deletes a row in the database by id. Used by :attr:`.ModelManager.update_field`.
    Use the :class:`.CheckDelete` API first to check if the row can be safely deleted.
    Returns ``True``.

    :param model: The SQLAlchemy model.
    """

    def prepare_item(
        self, info: graphql.GraphQLResolveInfo, kwargs: dict[str, t.Any]
    ) -> M:
        session = _get_sa_session(info)
        item = self.get_item(info, kwargs)
        session.delete(item)
        return item

    def __call__(
        self, parent: t.Any, info: graphql.GraphQLResolveInfo, **kwargs: t.Any
    ) -> t.Any:
        super().__call__(parent, info, **kwargs)
        return True


def _get_sa_session(info: graphql.GraphQLResolveInfo) -> orm.Session:
    """Get the SQLAlchemy session from the context."""

    try:
        return info.context["sa_session"]  # type: ignore[no-any-return]
    except (TypeError, KeyError) as e:
        raise RuntimeError("'sa_session' must be set in execute context dict.") from e
