import asyncio
import json
from typing import Optional
from dataclasses import dataclass
from config import config
from services.openai_service import openai_service
from services.kieai_service import kieai_service

@dataclass
class CarouselSlide:
    slide_number: int
    total_slides: int
    title: str
    content: str
    slide_type: str  # cover, content, cta

@dataclass
class CarouselContent:
    topic: str
    style: str
    color_scheme: str
    slides: list[CarouselSlide]

class CarouselService:
    def __init__(self):
        self.api_key = config.KIEAI_API_KEY
    
    def is_available(self) -> bool:
        return bool(self.api_key) and openai_service.is_available()
    
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

Создай контент для карусели из {slides_count} слайдов.

СТРУКТУРА:
1. Слайд 1 (cover) — цепляющий заголовок + подзаголовок
2. Слайды 2-{slides_count-1} (content) — основной контент
3. Слайд {slides_count} (cta) — призыв к действию

ТРЕБОВАНИЯ:
- Заголовки: до 50 символов
- Пункты: до 80 символов
- Используй эмодзи

БАЗА ЗНАНИЙ:
{kb_content[:2000] if kb_content else 'Пуста.'}

Ответь JSON:
{{"slides": [{{"slide_number": 1, "slide_type": "cover", "title": "...", "content": "..."}}]}}"""

        response = await openai_service.client.chat.completions.create(
            model=openai_service.model,
            messages=[
                {"role": "developer", "content": system},
                {"role": "user", "content": f"Тема: {topic}\nСтиль: {style}\nСлайдов: {slides_count}"}
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
        color_scheme: str
    ) -> str:
        """Создаёт промпт для генерации изображения"""
        
        style_prompts = {
            "современный минималистичный": "Modern minimalist design, clean lines, geometric shapes",
            "яркий и динамичный": "Vibrant dynamic design, bold colors, energetic",
            "профессиональный строгий": "Professional corporate design, structured layout",
            "креативный и игривый": "Creative playful design, fun illustrations"
        }
        
        color_prompts = {
            "dark": "dark background, light text, neon accents",
            "light": "light background, dark text, colorful accents",
            "gradient": "gradient background, white text"
        }
        
        base_style = style_prompts.get(style, style_prompts["современный минималистичный"])
        color_style = color_prompts.get(color_scheme, color_prompts["dark"])
        
        if slide.slide_type == "cover":
            content_desc = f'Cover slide. Title: "{slide.title}". Subtitle: "{slide.content}"'
        elif slide.slide_type == "cta":
            content_desc = f'CTA slide. Headline: "{slide.title}". Action: "{slide.content}"'
        else:
            content_desc = f'Content slide. Title: "{slide.title}". Points: {slide.content}'

        return f"""{base_style}. {color_style}.
{content_desc}
Slide {slide.slide_number}/{slide.total_slides} in corner.
Square format 1:1, Instagram carousel style, readable text."""
    
    async def generate_slide_image(
        self,
        slide: CarouselSlide,
        style: str = "современный минималистичный",
        color_scheme: str = "dark",
        callback_url: Optional[str] = None
    ) -> dict:
        """Генерирует изображение через Google Nano Banana"""
        prompt = self._build_slide_prompt(slide, style, color_scheme)
        
        return await kieai_service.generate_nano_banana_image(
            prompt=prompt,
            aspect_ratio="1:1",
            callback_url=callback_url
        )
    
    async def generate_carousel_images(
        self,
        content: CarouselContent,
        callback_url: Optional[str] = None
    ) -> list[dict]:
        """Генерирует изображения для всех слайдов"""
        tasks = []
        
        for slide in content.slides:
            try:
                result = await self.generate_slide_image(
                    slide=slide,
                    style=content.style,
                    color_scheme=content.color_scheme,
                    callback_url=callback_url
                )
                
                if result is None:
                    tasks.append({
                        "slide_number": slide.slide_number,
                        "task_id": None,
                        "status": "error",
                        "error": "Empty response"
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
            
            await asyncio.sleep(0.5)
        
        return tasks
    
    async def wait_for_image(self, task_id: str, timeout: int = 300, poll_interval: int = 5) -> Optional[str]:
        """Ожидает завершения генерации"""
        elapsed = 0
        
        while elapsed < timeout:
            result = await kieai_service.get_task_status(task_id)
            
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
                return data.get("imageUrl") or data.get("url")
            
            elif state in ("failed", "error"):
                return None
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        return None

carousel_service = CarouselService()