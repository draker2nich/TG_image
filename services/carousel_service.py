import aiohttp
import asyncio
import json
from typing import Optional
from dataclasses import dataclass
from config import config
from services.openai_service import openai_service

@dataclass
class CarouselSlide:
    """Слайд карусели"""
    slide_number: int
    total_slides: int
    title: str
    content: str
    slide_type: str  # cover, content, cta

@dataclass
class CarouselContent:
    """Контент карусели"""
    topic: str
    style: str
    color_scheme: str
    slides: list[CarouselSlide]

class CarouselService:
    def __init__(self):
        self.api_key = config.KIEAI_API_KEY
        self.base_url = config.KIEAI_BASE_URL
    
    def is_available(self) -> bool:
        return bool(self.api_key) and openai_service.is_available()
    
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def generate_carousel_content(
        self,
        topic: str,
        slides_count: int = 7,
        style: str = "современный минималистичный",
        target_audience: str = "широкая аудитория"
    ) -> CarouselContent:
        """Генерирует контент для карусели через ChatGPT"""
        if not openai_service.is_available():
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = openai_service._load_knowledge_base()
        
        system = f"""Ты — эксперт по созданию вирусных каруселей для Telegram и Instagram.

Создай контент для карусели из {slides_count} слайдов по теме.

ТРЕБОВАНИЯ К СТРУКТУРЕ:
1. Слайд 1 (cover) — цепляющий заголовок + подзаголовок
2. Слайды 2-{slides_count-1} (content) — основной контент, 3-5 пунктов на слайд
3. Слайд {slides_count} (cta) — призыв к действию

ТРЕБОВАНИЯ К ТЕКСТУ:
- Заголовки: короткие, цепляющие (до 50 символов)
- Пункты: лаконичные (до 80 символов каждый)
- Используй эмодзи для акцентов
- Текст должен быть ценным и полезным

БАЗА ЗНАНИЙ (используй если релевантно):
{kb_content[:2000] if kb_content else 'Пуста.'}

Ответь в формате JSON:
{{
    "slides": [
        {{
            "slide_number": 1,
            "slide_type": "cover",
            "title": "Главный заголовок",
            "content": "Подзаголовок или краткое описание"
        }},
        {{
            "slide_number": 2,
            "slide_type": "content",
            "title": "Заголовок раздела",
            "content": "• Пункт 1\\n• Пункт 2\\n• Пункт 3"
        }}
    ]
}}"""

        response = await openai_service.client.chat.completions.create(
            model=openai_service.model,
            messages=[
                {"role": "developer", "content": system},
                {"role": "user", "content": f"Тема: {topic}\nСтиль: {style}\nАудитория: {target_audience}\nКоличество слайдов: {slides_count}"}
            ],
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        slides_data = result.get("slides", [])
        
        slides = []
        for s in slides_data:
            slides.append(CarouselSlide(
                slide_number=s.get("slide_number", len(slides) + 1),
                total_slides=slides_count,
                title=s.get("title", ""),
                content=s.get("content", ""),
                slide_type=s.get("slide_type", "content")
            ))
        
        return CarouselContent(
            topic=topic,
            style=style,
            color_scheme="dark",
            slides=slides
        )
    
    def _build_slide_prompt(
        self,
        slide: CarouselSlide,
        style: str,
        color_scheme: str,
        brand_elements: str = ""
    ) -> str:
        """Создаёт промпт для генерации изображения слайда"""
        
        # Базовый стиль
        style_prompts = {
            "современный минималистичный": "Modern minimalist design, clean lines, lots of white space, geometric shapes",
            "яркий и динамичный": "Vibrant dynamic design, bold colors, energetic composition, gradient backgrounds",
            "профессиональный строгий": "Professional corporate design, structured layout, subtle gradients, business aesthetic",
            "креативный и игривый": "Creative playful design, fun illustrations, rounded shapes, cheerful colors"
        }
        
        color_prompts = {
            "dark": "dark background (#1a1a2e or #16213e), light text, neon accents",
            "light": "light background (#f5f5f5 or white), dark text, colorful accents",
            "gradient": "gradient background (purple to blue or orange to pink), white text"
        }
        
        base_style = style_prompts.get(style, style_prompts["современный минималистичный"])
        color_style = color_prompts.get(color_scheme, color_prompts["dark"])
        
        # Формируем промпт в зависимости от типа слайда
        if slide.slide_type == "cover":
            content_desc = f"""Cover slide for social media carousel.
Large bold title: "{slide.title}"
Subtitle: "{slide.content}"
Eye-catching design, title prominently displayed.
Slide number "{slide.slide_number}/{slide.total_slides}" in corner."""
        
        elif slide.slide_type == "cta":
            content_desc = f"""Call-to-action slide for social media carousel.
Headline: "{slide.title}"
CTA text: "{slide.content}"
Engaging design encouraging action.
Slide number "{slide.slide_number}/{slide.total_slides}" in corner."""
        
        else:  # content
            # Форматируем пункты для промпта
            points = slide.content.replace("•", "-").strip()
            content_desc = f"""Content slide for social media carousel.
Section title: "{slide.title}"
Bullet points:
{points}
Clean readable layout with visual hierarchy.
Slide number "{slide.slide_number}/{slide.total_slides}" in corner."""

        prompt = f"""{base_style}. {color_style}.
{content_desc}
{brand_elements}
Square format (1:1), high quality, Instagram/Telegram carousel style.
Typography: modern sans-serif fonts, good contrast, readable text.
Professional social media design, cohesive visual style."""

        return prompt
    
    async def generate_slide_image(
        self,
        slide: CarouselSlide,
        style: str = "современный минималистичный",
        color_scheme: str = "dark",
        brand_elements: str = "",
        callback_url: Optional[str] = None
    ) -> dict:
        """Генерирует изображение для одного слайда через Nano Banana Pro"""
        if not self.api_key:
            raise RuntimeError("Kie.ai API недоступен")
        
        prompt = self._build_slide_prompt(slide, style, color_scheme, brand_elements)
        
        payload = {
            "model": "nano-banana-pro",
            "input": {
                "prompt": prompt,
                "image_input": [],
                "aspect_ratio": "1:1",
                "resolution": "1K",
                "output_format": "png"
            }
        }
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/v1/jobs/createTask",
                    headers=self._headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return {"code": resp.status, "msg": f"HTTP error: {resp.status}"}
                    return await resp.json()
        except asyncio.TimeoutError:
            return {"code": 408, "msg": "Request timeout"}
        except Exception as e:
            return {"code": 500, "msg": str(e)}
    
    async def generate_carousel_images(
        self,
        content: CarouselContent,
        brand_elements: str = "",
        callback_url: Optional[str] = None
    ) -> list[dict]:
        """Генерирует изображения для всех слайдов карусели"""
        tasks = []
        
        for slide in content.slides:
            try:
                result = await self.generate_slide_image(
                    slide=slide,
                    style=content.style,
                    color_scheme=content.color_scheme,
                    brand_elements=brand_elements,
                    callback_url=callback_url
                )
                
                # Проверяем что result не None
                if result is None:
                    tasks.append({
                        "slide_number": slide.slide_number,
                        "task_id": None,
                        "status": "error",
                        "error": "Empty API response"
                    })
                    continue
                
                data = result.get("data") or {}
                task_id = data.get("taskId")
                code = result.get("code", 0)
                
                tasks.append({
                    "slide_number": slide.slide_number,
                    "task_id": task_id,
                    "status": "pending" if code == 200 and task_id else "error",
                    "error": result.get("msg") if code != 200 else None
                })
            except Exception as e:
                tasks.append({
                    "slide_number": slide.slide_number,
                    "task_id": None,
                    "status": "error",
                    "error": str(e)
                })
            
            # Небольшая задержка между запросами
            await asyncio.sleep(0.5)
        
        return tasks
    
    async def get_image_status(self, task_id: str) -> dict:
        """Проверяет статус генерации изображения"""
        if not self.api_key:
            raise RuntimeError("Kie.ai API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/jobs/recordInfo",
                headers=self._headers(),
                params={"taskId": task_id}
            ) as resp:
                return await resp.json()
    
    async def wait_for_image(self, task_id: str, timeout: int = 300, poll_interval: int = 5) -> Optional[str]:
        """Ожидает завершения генерации и возвращает URL изображения"""
        elapsed = 0
        
        while elapsed < timeout:
            result = await self.get_image_status(task_id)
            
            if result.get("code") != 200:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue
            
            data = result.get("data", {})
            state = data.get("state", "").lower()
            
            if state in ("success", "completed", "done"):
                # Пытаемся найти URL изображения
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
                return data.get("imageUrl") or data.get("url")
            
            elif state in ("failed", "error"):
                return None
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        return None

carousel_service = CarouselService()