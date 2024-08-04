## Version 1.1.1

Unreleased


## Version 1.1.0

Released 2024-08-03

-   The description for a model's object, and for an attribute's field and
    argument, is set from their docstrings. {issue}`19`
-   Handle fragments when inspecting query to load relationships. {issue}`21`
-   Clearer error when SQLAlchemy session is not passed in GraphQL context.
-   List sorts can be paths across relationships, like `user.name` from `Task`.
    Filters can already be across relationships. {issue}`27`
-   Default mutation resolvers have a separate `prepare_obj` method that
    creates/updates/deletes the object in the session but does not commit. This
    can be used to avoid extra commits when wrapping the default resolver with
    extra behavior. {issue}`25`
-   Resolver classes and `ModelManager`, and their methods, are generic on the
    model class passed to them.
-   `ModelManager` has class attributes to override the
    item/list/create/update/delete resolver factories. `ModelGroup` has a class
    attribute to override the manager class. This can be used to customize the
    default behaviors. {issue}`26`
-   Every generated object has a `_display_value` field that returns `str(obj)`.
    {issue}`32`


## Version 1.0.0

Released 2023-07-29

-   Initial release.
