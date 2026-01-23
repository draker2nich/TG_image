import aiohttp
from typing import Optional, Literal
from config import config

class KieAIService:
    """Сервис для работы с Sora2 и Veo3 через kie.ai"""
    
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
    
    async def generate_sora2_video(
        self,
        prompt: str,
        mode: Literal["text", "image"] = "text",
        image_urls: Optional[list[str]] = None,
        aspect_ratio: str = "landscape",
        n_frames: str = "10",
        callback_url: Optional[str] = None
    ) -> dict:
        """Генерация видео через Sora 2"""
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        model = "sora-2-image-to-video" if mode == "image" and image_urls else "sora-2-text-to-video"
        
        payload = {
            "model": model,
            "input": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "n_frames": n_frames,
                "remove_watermark": True
            }
        }
        
        if mode == "image" and image_urls:
            payload["input"]["image_urls"] = image_urls
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/jobs/createTask",
                headers=self._headers(),
                json=payload
            ) as resp:
                return await resp.json()
    
    async def generate_veo3_video(
        self,
        prompt: str,
        model: Literal["veo3", "veo3_fast"] = "veo3_fast",
        image_urls: Optional[list[str]] = None,
        aspect_ratio: str = "16:9",
        generation_type: Optional[str] = None,
        callback_url: Optional[str] = None
    ) -> dict:
        """Генерация видео через Veo 3.1"""
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "prompt": prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "enableTranslation": True
        }
        
        if image_urls:
            payload["imageUrls"] = image_urls
            generation_type = generation_type or "FIRST_AND_LAST_FRAMES_2_VIDEO"
        else:
            generation_type = generation_type or "TEXT_2_VIDEO"
        
        payload["generationType"] = generation_type
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/veo/generate",
                headers=self._headers(),
                json=payload
            ) as resp:
                return await resp.json()
    
    async def get_task_status(self, task_id: str) -> dict:
        """Статус задачи Sora2 (unified endpoint)"""
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/jobs/recordInfo",
                headers=self._headers(),
                params={"taskId": task_id}
            ) as resp:
                return await resp.json()
    
    async def get_veo_status(self, task_id: str) -> dict:
        """Статус задачи Veo3"""
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/veo/record-info",
                headers=self._headers(),
                params={"taskId": task_id}
            ) as resp:
                return await resp.json()
    
    async def generate_nano_banana_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        output_format: str = "png",
        callback_url: Optional[str] = None
    ) -> dict:
        """Генерация изображения через Google Nano Banana"""
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "model": "google/nano-banana",
            "input": {
                "prompt": prompt,
                "output_format": output_format,
                "image_size": aspect_ratio
            }
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/jobs/createTask",
                headers=self._headers(),
                json=payload
            ) as resp:
                return await resp.json()

kieai_service = KieAIService()