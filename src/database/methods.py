from sqlalchemy import select


class Database:
    def __init__(self, session_wrapper):
        self._sw = session_wrapper

    async def get(self, owner: str, key: str, default=None):
        """
        Ищет настройку по имени модуля (owner) и ключу (key).
        """
        async for db in self._sw.get_db():
            stmt = select(self._sw.Settings).where(
                self._sw.Settings.owner == owner,
                self._sw.Settings.key == key
            )
            result = await db.scalar(stmt)
            
            if result is not None:
                return result.value
            
            return default

    async def set(self, owner: str, key: str, value: any):
        """
        Создает или обновляет строку в базе данных.
        Если это новый модуль или новый ключ - автоматически добавит строку.
        """
        async for db in self._sw.get_db():
            stmt = select(self._sw.Settings).where(
                self._sw.Settings.owner == owner,
                self._sw.Settings.key == key
            )
            result = await db.execute(stmt)
            obj = result.scalar_one_or_none()

            if obj:
                obj.value = value
            else:
                new = self._sw.Settings(owner=owner, key=key, value=value)
                db.add(new)
            
            await db.commit()
            return True