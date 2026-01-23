import aiohttp
import base64
import tempfile
import os
from typing import Optional
from aiogram import Bot

class FileUploadService:
    """Сервис для загрузки файлов на внешний хостинг"""
    
    def __init__(self):
        # Используем бесплатный сервис для временного хостинга файлов
        # Можно заменить на свой сервер или другой сервис
        self.upload_services = [
            self._upload_to_tmpfiles,
            self._upload_to_fileio,
        ]
    
    async def download_telegram_file(self, bot: Bot, file_id: str) -> bytes:
        """Скачивает файл из Telegram"""
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # Скачиваем файл
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to download file: {resp.status}")
                return await resp.read()
    
    async def _upload_to_tmpfiles(self, file_content: bytes, filename: str) -> Optional[str]:
        """Загрузка на tmpfiles.org (хранится 1 час)"""
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', file_content, filename=filename)
                
                async with session.post(
                    'https://tmpfiles.org/api/v1/upload',
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        url = result.get('data', {}).get('url', '')
                        # Преобразуем URL для прямого доступа
                        if url:
                            # tmpfiles.org/123/file.jpg -> tmpfiles.org/dl/123/file.jpg
                            url = url.replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                            return url
        except Exception as e:
            print(f"tmpfiles upload error: {e}")
        return None
    
    async def _upload_to_fileio(self, file_content: bytes, filename: str) -> Optional[str]:
        """Загрузка на file.io (одноразовая ссылка)"""
        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', file_content, filename=filename)
                
                async with session.post(
                    'https://file.io',
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('success'):
                            return result.get('link')
        except Exception as e:
            print(f"file.io upload error: {e}")
        return None
    
    async def upload_file(self, file_content: bytes, filename: str) -> str:
        """Загружает файл и возвращает публичный URL"""
        for upload_fn in self.upload_services:
            url = await upload_fn(file_content, filename)
            if url:
                return url
        
        raise Exception("Не удалось загрузить файл ни на один хостинг")
    
    async def upload_telegram_file(self, bot: Bot, file_id: str, filename: str) -> str:
        """Скачивает файл из Telegram и загружает на хостинг"""
        file_content = await self.download_telegram_file(bot, file_id)
        return await self.upload_file(file_content, filename)

file_upload_service = FileUploadService()
