from __future__ import annotations

import typing as t
from types import SimpleNamespace

from graphql import FieldNode
from graphql import GraphQLResolveInfo
from magql import Object
from magql import Schema

from magql_sqlalchemy.resolvers import _get_field_node

schema = Schema()


@schema.query.field("item", "Boolean!")
def _resolve_one(parent: t.Any, info: GraphQLResolveInfo, **kwargs: t.Any) -> bool:
    info.context.node = _get_field_node(info)
    return True


@schema.query.field(
    "list", Object("ListResult", fields={"items": "[Boolean!]!", "total": "Int!"})
)
def _resolve_list(
    parent: t.Any, info: GraphQLResolveInfo, **kwargs: t.Any
) -> SimpleNamespace:
    info.context.node = _get_field_node(info, "items")
    return SimpleNamespace(items=[], total=0)


def _execute(source: str) -> FieldNode:
    """Execute a query and return the result of _get_field_node. The resolvers
    store the result in the context object.
    """
    context = SimpleNamespace()
    result = schema.execute(source, context=context)

    if result.errors:
        raise result.errors[0]

    return t.cast(FieldNode, context.node)


def test_item_node() -> None:
    """The first node is found."""
    node = _execute("query { item }")
    assert node.name.value == "item"


def test_list_node() -> None:
    """The items node in a list result is found."""
    node = _execute("query { list { total items } }")
    assert node.name.value == "items"


def test_list_fragment() -> None:
    """Fragment on list result is handled by recursing into dereferenced nodes."""
    node = _execute(
        "fragment a on ListResult { items }\n"
        "fragment b on ListResult { total ...a }\n"
        "query { list { ...b } }"
    )
    assert node.name.value == "items"


def test_inline_fragment() -> None:
    """Inline fragment on list result is handled by recursing into the node."""
    node = _execute(
        "fragment a on ListResult { items }\n"
        "query { list { ... on ListResult { total ...a } } }"
    )
    assert node.name.value == "items"


def test_top_fragment() -> None:
    """Fragments on Query are automatically flattened during parsing and don't
    need to be handled specially.
    """
    node = _execute(
        "fragment a on Query { item }\n"
        "fragment b on Query { ...a }\n"
        "query { ...b }"
    )
    assert node.name.value == "item"
