import aiohttp
import asyncio
import json
from typing import Optional
from dataclasses import dataclass
from config import config

@dataclass
class MotionTask:
    task_id: str
    status: str
    error: Optional[str] = None

class KlingMotionService:
    """Сервис для работы с Kling 2.6 Motion Control через kie.ai"""
    
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
    
    async def create_motion_video(
        self,
        image_url: str,
        video_url: str,
        prompt: str = "",
        character_orientation: str = "video",
        mode: str = "720p",
        callback_url: Optional[str] = None
    ) -> dict:
        """
        Создаёт видео с Motion Control через Kling 2.6
        
        Args:
            image_url: URL фото аватара (jpeg/png/jpg, до 10MB, >300px, aspect 2:5 to 5:2)
            video_url: URL видео с движениями (mp4/mov/mkv, до 100MB, 3-30 сек)
            prompt: Описание желаемого результата (до 2500 символов)
            character_orientation: 
                - "image" — ориентация как на фото (макс 10 сек видео)
                - "video" — ориентация как в видео (макс 30 сек видео)
            mode: Разрешение — "720p" или "1080p"
            callback_url: URL для колбэка
        
        Returns:
            dict с taskId или ошибкой
        """
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "model": "kling-2.6/motion-control",
            "input": {
                "input_urls": [image_url],
                "video_urls": [video_url],
                "character_orientation": character_orientation,
                "mode": mode
            }
        }
        
        if prompt:
            payload["input"]["prompt"] = prompt[:2500]
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/jobs/createTask",
                headers=self._headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                result = await resp.json()
                return result
    
    async def get_task_status(self, task_id: str) -> dict:
        """Проверяет статус задачи через unified endpoint"""
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
        timeout: int = 900,  # 15 минут
        poll_interval: int = 15
    ) -> Optional[str]:
        """Ожидает завершения и возвращает URL результата"""
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
                result_json = data.get("resultJson", {})
                if isinstance(result_json, str):
                    try:
                        result_json = json.loads(result_json)
                    except:
                        result_json = {}
                
                urls = result_json.get("resultUrls", [])
                if urls:
                    return urls[0]
                
                return data.get("videoUrl") or data.get("url")
            
            elif state in ("failed", "error"):
                return None
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        return None

kling_motion_service = KlingMotionService()