import os
import aiohttp
from pathlib import Path


class RemoteStorage:
    """Удалённое хранилище медиа. Бот не сохраняет пользовательские файлы локально."""
    def __init__(self):
        self.base_url = os.getenv('MEDIA_STORAGE_URL', '').rstrip('/')
        self.token = os.getenv('MEDIA_STORAGE_TOKEN', '')

    def enabled(self):
        return bool(self.base_url)

    async def upload(self, content: bytes, filename: str, content_type: str = 'application/octet-stream') -> str:
        if not self.base_url:
            raise RuntimeError('MEDIA_STORAGE_URL не задан. Укажите URL отдельного сайта-хранилища.')
        headers = {'Authorization': f'Bearer {self.token}'} if self.token else {}
        data = aiohttp.FormData()
        data.add_field('file', content, filename=Path(filename).name, content_type=content_type)
        async with aiohttp.ClientSession() as session:
            async with session.post(f'{self.base_url}/api/files', data=data, headers=headers, timeout=60) as r:
                body = await r.text()
                if r.status >= 400:
                    raise RuntimeError(f'Хранилище вернуло HTTP {r.status}: {body[:300]}')
                try:
                    payload = await r.json()
                except Exception as e:
                    raise RuntimeError('Хранилище вернуло не JSON.') from e
                url = payload.get('url')
                if not url:
                    raise RuntimeError('В ответе хранилища нет поля url.')
                return url

    def url(self, value: str | None) -> str | None:
        if not value:
            return None
        # Поддержка старых абсолютных URL и новых URL.
        if value.startswith(('http://', 'https://')):
            return value
        if not self.base_url:
            return None
        return f'{self.base_url}/files/{value.lstrip("/")}'


storage = RemoteStorage()
