## Version 1.1.0

Unreleased

-   The description for a model's object, and for an attribute's field and
    argument, is set from their docstrings. {issue}`19`
-   Handle fragments when inspecting query to load relationships. {issue}`21`
-   Clearer error when SQLAlchemy session is not passed in GraphQL context.
-   List sorts can be paths across relationships, like `user.name` from `Task`.
    Filters can already be across relationships. {issue}`27`


## Version 1.0.0

Released 2023-07-29

-   Initial release.
