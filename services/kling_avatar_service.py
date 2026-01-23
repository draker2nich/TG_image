import aiohttp
import asyncio
import json
from typing import Optional, Literal
from dataclasses import dataclass
from config import config

@dataclass
class AvatarTask:
    """Результат создания задачи аватара"""
    task_id: str
    status: str
    error: Optional[str] = None

class KlingAvatarService:
    """Сервис для работы с Kling AI Avatar через kie.ai"""
    
    def __init__(self):
        self.api_key = config.KIEAI_API_KEY
        self.base_url = config.KIEAI_BASE_URL
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def generate_avatar_image(
        self,
        prompt: str,
        style: str = "photorealistic portrait",
        aspect_ratio: str = "1:1",
        callback_url: Optional[str] = None
    ) -> dict:
        """
        Генерирует фото-аватар через Nano Banana Pro
        
        Args:
            prompt: Описание аватара
            style: Стиль изображения
            aspect_ratio: Соотношение сторон
            callback_url: URL для колбэка
        
        Returns:
            dict с task_id или ошибкой
        """
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        full_prompt = f"{style}, {prompt}, high quality, professional lighting, clean background"
        
        payload = {
            "model": "nano-banana-pro",
            "input": {
                "prompt": full_prompt,
                "image_input": [],
                "aspect_ratio": aspect_ratio,
                "resolution": "1K",
                "output_format": "png"
            }
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/jobs/createTask",
                headers=self._headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                return await resp.json()
    
    async def create_avatar_video(
        self,
        source_video_url: str,
        avatar_image_url: str,
        mode: Literal["audio", "video"] = "audio",
        callback_url: Optional[str] = None
    ) -> dict:
        """
        Создаёт видео с AI-аватаром через Kling-2.6
        Синхронизирует губы аватара с аудио из исходного видео
        
        Args:
            source_video_url: URL видео с записью голоса (источник аудио)
            avatar_image_url: URL фото аватара
            mode: Режим - audio (только аудио) или video (видео + аудио)
            callback_url: URL для колбэка
        
        Returns:
            dict с task_id или ошибкой
        """
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "model": "kling-2.6/image-to-video",
            "input": {
                "image_url": avatar_image_url,
                "video_url": source_video_url,
                "mode": mode,
                "duration": "auto"
            }
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/jobs/createTask",
                headers=self._headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                return await resp.json()
    
    async def create_lip_sync_video(
        self,
        avatar_image_url: str,
        audio_url: str,
        callback_url: Optional[str] = None
    ) -> dict:
        """
        Создаёт видео с lip-sync по аудио
        Альтернативный метод если нужно передать только аудио
        
        Args:
            avatar_image_url: URL фото аватара
            audio_url: URL аудиофайла
            callback_url: URL для колбэка
        
        Returns:
            dict с task_id или ошибкой
        """
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "model": "kling-2.6/image-to-video",
            "input": {
                "image_url": avatar_image_url,
                "audio_url": audio_url,
                "mode": "audio"
            }
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/jobs/createTask",
                headers=self._headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                return await resp.json()
    
    async def get_task_status(self, task_id: str) -> dict:
        """Проверяет статус задачи"""
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/jobs/recordInfo",
                headers=self._headers(),
                params={"taskId": task_id}
            ) as resp:
                return await resp.json()
    
    async def wait_for_result(
        self,
        task_id: str,
        timeout: int = 600,
        poll_interval: int = 10
    ) -> Optional[str]:
        """
        Ожидает завершения задачи и возвращает URL результата
        
        Args:
            task_id: ID задачи
            timeout: Максимальное время ожидания в секундах
            poll_interval: Интервал проверки в секундах
        
        Returns:
            URL готового видео/изображения или None
        """
        elapsed = 0
        
        while elapsed < timeout:
            result = await self.get_task_status(task_id)
            
            if result.get("code") != 200:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue
            
            data = result.get("data", {})
            state = data.get("state", "").lower()
            
            if state in ("success", "completed", "done"):
                # Пытаемся найти URL результата
                result_json = data.get("resultJson", {})
                if isinstance(result_json, str):
                    try:
                        result_json = json.loads(result_json)
                    except:
                        result_json = {}
                
                urls = result_json.get("resultUrls", [])
                if urls:
                    return urls[0]
                
                # Альтернативные поля
                return (
                    data.get("videoUrl") or 
                    data.get("imageUrl") or 
                    data.get("url")
                )
            
            elif state in ("failed", "error"):
                return None
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        return None
    
    async def upload_file_and_get_url(
        self,
        file_content: bytes,
        filename: str
    ) -> Optional[str]:
        """
        Загружает файл и получает публичный URL
        Примечание: Kie.ai может требовать публичные URL,
        поэтому файлы нужно загружать на доступный сервер
        
        В текущей реализации используем Telegram file URL
        """
        # Это заглушка - в реальности нужен сервер для хостинга файлов
        # или использовать Google Drive с публичными ссылками
        pass

kling_avatar_service = KlingAvatarService()
