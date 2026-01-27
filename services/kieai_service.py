import aiohttp
from typing import Optional, Literal
from config import config

class KieAIService:
    """Сервис для работы с Sora2, Veo3, 4o Image и Nano Banana через kie.ai"""
    
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
        """Статус задачи Sora2/Nano Banana (unified endpoint)"""
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
        """Генерация изображения через Google Nano Banana (для аватаров)"""
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
    
    async def generate_nano_banana_pro_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        resolution: str = "2K",
        output_format: str = "png",
        image_input: Optional[list[str]] = None,
        callback_url: Optional[str] = None
    ) -> dict:
        """
        Генерация изображения через Google Nano Banana Pro (более мощная модель)
        
        Args:
            prompt: Описание желаемого результата (max 10000 символов)
            aspect_ratio: Соотношение сторон ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "auto")
            resolution: Разрешение ("1K", "2K", "4K")
            output_format: Формат вывода ("png" или "jpg")
            image_input: Опциональные входные изображения (до 8 шт)
            callback_url: URL для колбэка
        
        Returns:
            dict с taskId или ошибкой
        """
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "model": "nano-banana-pro",
            "input": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "output_format": output_format,
                "image_input": image_input or []
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
    
    async def generate_nano_banana_edit(
        self,
        prompt: str,
        image_urls: list[str],
        aspect_ratio: str = "1:1",
        output_format: str = "png",
        callback_url: Optional[str] = None
    ) -> dict:
        """
        Редактирование изображения через Google Nano Banana Edit
        
        Args:
            prompt: Описание желаемого результата (max 5000 символов)
            image_urls: Список URL изображений для редактирования (до 10 шт)
            aspect_ratio: Соотношение сторон ("1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9", "auto")
            output_format: Формат вывода ("png" или "jpeg")
            callback_url: URL для колбэка
        
        Returns:
            dict с taskId или ошибкой
        """
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "model": "google/nano-banana-edit",
            "input": {
                "prompt": prompt,
                "image_urls": image_urls,
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
    
    async def generate_4o_image(
        self,
        prompt: str,
        size: Literal["1:1", "3:2", "2:3"] = "1:1",
        n_variants: int = 1,
        is_enhance: bool = False,
        files_url: Optional[list[str]] = None,
        mask_url: Optional[str] = None,
        callback_url: Optional[str] = None,
        enable_fallback: bool = False
    ) -> dict:
        """
        Генерация изображения через 4o Image API (GPT-4o Image)
        
        Args:
            prompt: Текстовое описание для генерации
            size: Соотношение сторон ("1:1", "3:2", "2:3")
            n_variants: Количество вариантов (1, 2 или 4)
            is_enhance: Улучшение промпта для сложных сцен
            files_url: URL изображений для редактирования (до 5 шт)
            mask_url: URL маски для редактирования
            callback_url: URL для колбэка
            enable_fallback: Автопереключение на Flux при недоступности
        
        Returns:
            dict с taskId или ошибкой
        """
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "prompt": prompt,
            "size": size,
            "nVariants": n_variants,
            "isEnhance": is_enhance
        }
        
        if files_url:
            payload["filesUrl"] = files_url
        
        if mask_url:
            payload["maskUrl"] = mask_url
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        if enable_fallback:
            payload["enableFallback"] = True
            payload["fallbackModel"] = "FLUX_MAX"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/gpt4o-image/generate",
                headers=self._headers(),
                json=payload
            ) as resp:
                return await resp.json()
    
    async def get_4o_image_status(self, task_id: str) -> dict:
        """Статус задачи 4o Image API"""
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/gpt4o-image/record-info",
                headers=self._headers(),
                params={"taskId": task_id}
            ) as resp:
                return await resp.json()
    
    async def get_4o_image_download_url(self, task_id: str, image_url: str) -> dict:
        """Получает прямую ссылку для скачивания 4o Image (действует 20 минут)"""
        if not self.is_available():
            raise RuntimeError("Kie.ai API недоступен")
        
        payload = {
            "taskId": task_id,
            "url": image_url
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/gpt4o-image/download-url",
                headers=self._headers(),
                json=payload
            ) as resp:
                return await resp.json()

kieai_service = KieAIService()