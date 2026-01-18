import aiohttp
from typing import Optional
from config import config

class HeyGenService:
    def __init__(self):
        self.api_key = config.HEYGEN_API_KEY
        self.base_url = config.HEYGEN_BASE_URL
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def _headers(self) -> dict:
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "x-api-key": self.api_key
        }
    
    async def list_avatars(self) -> list[dict]:
        """Получает список доступных аватаров"""
        if not self.is_available():
            raise RuntimeError("HeyGen API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v2/avatars",
                headers=self._headers()
            ) as resp:
                data = await resp.json()
                return data.get("data", {}).get("avatars", [])
    
    async def list_voices(self, language: str = "ru") -> list[dict]:
        """Получает список доступных голосов"""
        if not self.is_available():
            raise RuntimeError("HeyGen API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v2/voices",
                headers=self._headers()
            ) as resp:
                data = await resp.json()
                voices = data.get("data", {}).get("voices", [])
                # Фильтруем по языку
                return [v for v in voices if v.get("language", "").startswith(language)]
    
    async def generate_video(
        self,
        script: str,
        avatar_id: str,
        voice_id: str,
        title: str = "Generated Video",
        enable_captions: bool = True,
        width: int = 1920,
        height: int = 1080,
        callback_url: Optional[str] = None
    ) -> dict:
        """Создаёт видео с аватаром"""
        if not self.is_available():
            raise RuntimeError("HeyGen API недоступен")
        
        payload = {
            "caption": enable_captions,
            "title": title,
            "dimension": {"width": width, "height": height},
            "video_inputs": [{
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal"
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": voice_id
                },
                "background": {
                    "type": "color",
                    "value": "#FFFFFF"
                }
            }]
        }
        
        if callback_url:
            payload["callback_url"] = callback_url
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v2/video/generate",
                headers=self._headers(),
                json=payload
            ) as resp:
                return await resp.json()
    
    async def get_video_status(self, video_id: str) -> dict:
        """Проверяет статус генерации видео"""
        if not self.is_available():
            raise RuntimeError("HeyGen API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v1/video_status.get?video_id={video_id}",
                headers=self._headers()
            ) as resp:
                return await resp.json()

heygen_service = HeyGenService()
