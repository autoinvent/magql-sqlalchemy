Global Search Query
===================

Magql provides a `search` query field that will perform a global search using
registered providers. Magql-SQLAlchemy registers a provider for each model that
will search all string columns.


The Query and Results
---------------------

The `search` query field takes one argument, `value`, the string to search for.
It returns a list of items.

The items in the list have the following keys:

-   `type`, the name of the model class.
-   `id`, the primary key of the row.
-   `value`, the string representation of the model row (`str(item)`).
-   `extra`, currently unused, arbitrary extra information about the row.

Using the `type` and `id`, a UI could present search results that link to that
item.


Disabling for a Model
---------------------

When using {class}`.ModelGroup.from_declarative_base`, it takes a `search`
argument to control what models are searchable.

By default, `search` is `True`, which generates a search provider for ever
model. You can reassign {attr}`.ModelManager.search_provider` to `None` to
disable search for that model. If you set `search` to `False`, no providers will
be generated.

You can pass a set of model classes and/or model names to `search` to
generate providers only for those models.


Customizing a Provider
----------------------

The default search provider for each model is {class}`.ColumnSearchProvider`,
which generates a `ILIKE` query against all of the model's string-like columns.

{attr}`.ModelManager.search_provider` can be reassigned to any callable that
takes a `value` argument and returns a list of
{class}`magql.search.SearchResult` instances.
