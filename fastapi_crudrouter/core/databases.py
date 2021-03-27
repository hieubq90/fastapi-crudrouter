from typing import Any, Callable, List, Mapping, Type, Coroutine

from fastapi import HTTPException

from . import CRUDGenerator, NOT_FOUND, _utils
from ._types import PAGINATION, PYDANTIC_SCHEMA

try:
    from sqlalchemy.sql.schema import Table
    from databases.core import Database
except ImportError:
    databases_installed = False
else:
    databases_installed = True

Model = Mapping[Any, Any]
CALLABLE = Callable[..., Coroutine[Any, Any, Model]]
CALLABLE_LIST = Callable[..., Coroutine[Any, Any, List[Model]]]


class DatabasesCRUDRouter(CRUDGenerator[PYDANTIC_SCHEMA]):
    def __init__(
        self,
        schema: Type[PYDANTIC_SCHEMA],
        table: "Table",
        database: "Database",
        *args: Any,
        **kwargs: Any
    ) -> None:
        assert (
            databases_installed
        ), "Databases and SQLAlchemy must be installed to use the DatabasesCRUDRouter."
        self.table = table
        self.db = database
        self._pk = table.primary_key.columns.values()[0].name
        self._pk_col = self.table.c[self._pk]
        self._pk_type: type = _utils.get_pk_type(schema, self._pk)

        if "prefix" not in kwargs:
            kwargs["prefix"] = table.name

        if "create_schema" not in kwargs:
            kwargs["create_schema"] = _utils.schema_factory(schema, self._pk)

        super().__init__(schema, *args, **kwargs)

    def _get_all(self, *args: Any, **kwargs: Any) -> CALLABLE_LIST:
        async def route(
            pagination: PAGINATION = self.pagination,
        ) -> List[Model]:
            skip, limit = pagination.get("skip"), pagination.get("limit")

            query = self.table.select().limit(limit).offset(skip)
            return await self.db.fetch_all(query)

        return route

    def _get_one(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(item_id: self._pk_type) -> Model:  # type: ignore
            query = self.table.select().where(self._pk_col == item_id)
            model = await self.db.fetch_one(query)

            if model:
                return model
            else:
                raise NOT_FOUND

        return route

    def _create(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(
            schema: self.create_schema,  # type: ignore
        ) -> Model:
            try:
                query = self.table.insert()
                rid = await self.db.execute(query=query, values=schema.dict())
                return {self._pk: rid, **schema.dict()}
            except Exception:
                raise HTTPException(422, "Key already exists")

        return route

    def _update(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(
            item_id: self._pk_type, schema: self.update_schema  # type: ignore
        ) -> Model:
            query = self.table.update().where(self._pk_col == item_id)
            rid = await self.db.execute(
                query=query, values=schema.dict(exclude={self._pk})
            )

            if rid:
                return {self._pk: rid, **schema.dict()}
            else:
                raise NOT_FOUND

        return route

    def _delete_all(self, *args: Any, **kwargs: Any) -> CALLABLE_LIST:
        async def route() -> List[Model]:
            query = self.table.delete()
            await self.db.execute(query=query)

            return await self._get_all()(pagination={"skip": 0, "limit": None})

        return route

    def _delete_one(self, *args: Any, **kwargs: Any) -> CALLABLE:
        async def route(item_id: self._pk_type) -> Model:  # type: ignore
            query = self.table.delete().where(self._pk_col == item_id)

            row = await self._get_one()(item_id)
            rid = await self.db.execute(query=query)

            if rid:
                return row
            else:
                raise NOT_FOUND

        return route
