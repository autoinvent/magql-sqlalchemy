Preview Delete Effects Query
============================

Magql-SQLAlchemy provides a `check_delete` query field that can show the effects
of deleting a row. This is done purely through introspection and does not
perform an actual deletion. This can be used in a UI to show an "Are you sure
you want to delete?" prompt with helpful information, or an explanation about
why something can't be deleted.


The Query and Results
---------------------

The field takes two arguments, `type` is the name of the model, and `id` is the
primary key of the row. It returns three lists, with items in the same format
as {doc}`q-search`.

-   `affected`, model rows that would change somehow. A nullable to-one
    relationship is cleared, or the row is removed from a to-many relationship.
-   `deleted`, model rows that would be deleted along with the checked row. Rows
    in a relationship that has `cascade='delete'` (or usually `all`) set.
-   `prevented`, model rows that would cause the deletion to fail. A non-null
    relationship.

The items in each list have the following keys:

-   `type`, the name of the model class.
-   `id`, the primary key of the row.
-   `value`, the string representation of the model row (`str(item)`).
-   `extra`, currently unused, arbitrary extra information about the row.


How It Works
------------

The query finds the SQLAlchemy model by name, then selects the row by id from
the database. Then it examines all the relationship properties of the model to
build the lists described above. Therefore, only data with SQLAlchemy
`relationship` properties can be returned in the result.

It's recommended that all relationships are two-way, with a property on each
model and with `back_populates` set on both. If one side does not have a
relationship, then checking its deletion cannot warn about affected rows or
that the database will raise an error.


Excluding Models
----------------

If you don't want to be able check a given model, you can remove it from the
{class}`.CheckDelete.managers` map. However, it may still show up in the results
of deleting other models if they have relationships to it.

```python
del model_group.check_delete.managers["UserSession"]
```
