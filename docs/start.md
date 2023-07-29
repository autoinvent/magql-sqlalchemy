Getting Started
===============

```{currentmodule} magql_sqlalchemy
```

Magql-SQLAlchemy is meant to be very simple to use, generating an initial
{class}`magql.Schema` with no configuration, then taking advantage of Magql's
ability to modify the schema before finalizing. Therefore, the
[Magql Documentation][magql] will have most of the information you'll need.

[magql]: https://magql.autoinvent.dev


Defining the Schema
-------------------

All you need is a SQLAlchemy declarative base class with some models defined.
Then pass it to {meth}`ModelGroup.from_declarative_base`. Most of the code
below is the SQLAlchemy setup. Only the last two lines are where
Magql-SQLAlchemy generates the API and registers it on the schema.

```python
from sqlalchemy import create_engine, ForeignKey
from sqlalchemy.orm import Session, DeclarativeBase, Mapped, mapped_column, relationship

import magql
from magql_sqlalchemy import ModelGroup

class Model(DeclarativeBase):
    pass

class User(Model):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    tasks: Mapped[list["Task"]] = relationship(back_populates="user")

class Task(Model):
    __tablename__ = "task"
    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str]
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    user: Mapped[User] = relationship(back_populates="tasks")

engine = create_engine("sqlite:///example.db", echo=True)
session = Session(engine)
Model.metadata.create_all(engine)

schema = magql.Schema()

# Generate an API from the models, then register it on the schema.
model_group = ModelGroup.from_declarative_base(Model)
model_group.register(schema)
```


Executing Queries
-----------------

The resolvers require passing the SQLAlchemy session in the GraphQL execution
context. They expect the context to be a dict, and the session to be on the
`sa_session` key.

```python
result = schema.execute(
    "{ user_item(id: 1) { username } }",
    context={"sa_session": session}
)
```


Generated API
-------------

With those two lines, the Magql-SQLAlchemy {class}`ModelGroup` has created a
{class}`ModelManager` for each model, which generated the following API
operations:

```text
type Query {
  task_item(id: Int!): Task
  task_list(filter: [[FilterItem!]!], sort: [String!], page: Int, per_page: Int): TaskListResult!
  user_item(id: Int!): User
  user_list(filter: [[FilterItem!]!], sort: [String!], page: Int, per_page: Int): UserListResult!
  search(value: String!): [SearchResult!]!
  check_delete(type: String!, id: ID!): CheckDeleteResult
}

type Mutation {
  task_create(message: String!, user: Int!): Task!
  task_update(id: Int!, message: String, user: Int): Task!
  task_delete(id: Int!): Boolean!
  user_create(username: String!, tasks: [Int!]): User!
  user_update(id: Int!, username: String, tasks: [Int!]): User!
  user_delete(id: Int!): Boolean!
}
```

{class}`ModelManager` creates objects, fields, arguments, resolvers, and validators for
a model. Let's look at what it created for the `Task` model:

*   `Task` object type with fields corresponding to each column and
    relationship. See {attr}`ModelManager.object` and {doc}`model`.
*   `task_item` query field that will return a row by id, or null if not found.
    See {attr}`ModelManager.item_field`.
*   `task_list` query field that will return a result object with a list of rows
    and a total count. See {attr}`ModelManager.list_field`.
    *   The `filter` argument can apply filters to any column, including across
        relationships; see {doc}`filters`.
    *   The `sort` argument can be one or more column names to sort by. A name
        can begin with `-` to sort descending. Defaults to the primary key.
    *   The `page` and `per_page` arguments apply pagination, defaulting to page
        1 with 10 per page. Currently, pagination cannot be disabled and has a
        max of 100 per page.
*   `task_create` mutation field to create a new row, with arguments for each
    column and relationship. Arguments are optional if the column is nullable or
    has a default. See {attr}`ModelManager.create_field`.
*   `task_update` mutation field to update a row by id, with arguments for each
    column and relationship. All column arguments are optional.
    See {attr}`ModelManager.update_field`.
*   `task_delete` mutation field to delete a row by id. See
    {attr}`ModelManager.delete_field`.

It also provides two global queries:

*   `search` takes a value and searches all string columns in all models. A UI
    could use this to provide a global search bar. See {doc}`q-search`.
*   `check_delete(type, id)` takes a model name and row id and checks what would
    be affected if the row was deleted. See {doc}`q-check_delete`.


Customizing the Schema
----------------------

After generating the {class}`ModelGroup`, you can modify what it generated.
This can be done before or after registering it on the schema. Just like plain
Magql, it cannot be modified after the schema is finalized by calling
{func}`Magql.to_graphql` (or `execute`, etc.).

{attr}`ModelGroup.managers` maps model names to {class}`ModelManager` instances.
The manager has attributes for each object and field it generated.

For example, you could add a new field and resolver to an object.

```python
user_manager = model_group.managers["User"]

@user_manager.object.field("greet", "String!")
def resolve_user_greet(parent: User, info, **kwargs) -> str:
    return f"Hello, {parent.username}!"
```

You could remove a field that should not be exposed in the API.

```python
del user_manager.object.fields["password"]
```

You could add a validator to an argument.

```python
@user_manager.create_field.args["username"].validator
def validate_username(info, value: str, data):
    if not value.islower():
        raise magql.ValidationError("Must be lowercase.")
```

Anything that is possible with Magql is possible with the model group's
generated API. Be sure to review the [Magql documentation][magql].
