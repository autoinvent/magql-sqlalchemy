API
===

Anything documented here is part of the public API that Magql-SQLAlchemy provides,
unless otherwise indicated. Anything not documented here is considered internal or
private and may change at any time.


Models
------

```{eval-rst}
.. currentmodule:: magql_sqlalchemy
.. autoclass:: ModelGroup
.. autoclass:: ModelManager
```


Resolvers
---------

```{eval-rst}
.. currentmodule:: magql_sqlalchemy.resolvers
.. autoclass:: ItemResolver
.. autoclass:: ListResolver
.. autoclass:: CreateResolver
.. autoclass:: UpdateResolver
.. autoclass:: DeleteResolver
.. currentmodule:: magql_sqlalchemy.filters
.. autodata:: type_ops
```


Search
------

```{eval-rst}
.. currentmodule:: magql_sqlalchemy.search
.. autoclass:: ColumnSearchProvider
```


Check Delete
------------

```{eval-rst}
.. currentmodule:: magql_sqlalchemy.check_delete
.. autoclass:: CheckDelete
```


Validators
----------

```{eval-rst}
.. currentmodule:: magql_sqlalchemy.validators
.. autoclass:: ItemExistsValidator
.. autoclass:: ListExistsValidator
.. autoclass:: UniqueValidator
.. currentmodule:: magql_sqlalchemy.pagination
.. autofunction:: validate_page
.. autoclass:: PerPageValidator
```
