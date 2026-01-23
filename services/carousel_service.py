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
        """Создаёт промпт для генерации изображения через 4o Image API"""
        
        style_prompts = {
            "современный минималистичный": "Modern minimalist design, clean lines, geometric shapes, elegant typography",
            "яркий и динамичный": "Vibrant dynamic design, bold colors, energetic, eye-catching graphics",
            "профессиональный строгий": "Professional corporate design, structured layout, business aesthetic",
            "креативный и игривый": "Creative playful design, fun illustrations, artistic elements"
        }
        
        color_prompts = {
            "dark": "dark background (#1a1a2e or similar), light text, neon or vibrant accents",
            "light": "light/white background, dark text, colorful modern accents",
            "gradient": "beautiful gradient background (purple-blue or orange-pink), white text"
        }
        
        base_style = style_prompts.get(style, style_prompts["современный минималистичный"])
        color_style = color_prompts.get(color_scheme, color_prompts["dark"])
        
        # Формируем контент для слайда
        if slide.slide_type == "cover":
            content_desc = f"""Instagram/Telegram carousel COVER slide design.
Main headline text: "{slide.title}"
Subtitle: "{slide.content}"
Make the title prominent and eye-catching."""
        
        elif slide.slide_type == "cta":
            content_desc = f"""Instagram/Telegram carousel CTA (call-to-action) slide design.
Main text: "{slide.title}"
Action text: "{slide.content}"
Include visual elements that encourage action (arrows, buttons, icons)."""
        
        else:
            content_desc = f"""Instagram/Telegram carousel CONTENT slide design.
Title: "{slide.title}"
Content/bullet points: {slide.content}
Layout should be clean and easy to read."""

        return f"""{base_style}. {color_style}.

{content_desc}

Important requirements:
- Square format (1:1 aspect ratio) for Instagram carousel
- Slide indicator showing {slide.slide_number}/{slide.total_slides} in bottom corner
- Text must be clearly readable and properly integrated into the design
- High quality, professional social media graphic
- Modern 2024 design trends"""
    
    async def generate_slide_image(
        self,
        slide: CarouselSlide,
        style: str = "современный минималистичный",
        color_scheme: str = "dark",
        callback_url: Optional[str] = None
    ) -> dict:
        """Генерирует изображение через 4o Image API (GPT-4o)"""
        prompt = self._build_slide_prompt(slide, style, color_scheme)
        
        return await kieai_service.generate_4o_image(
            prompt=prompt,
            size="1:1",  # Квадрат для карусели
            n_variants=1,
            is_enhance=True,  # Улучшение для сложных дизайнов
            callback_url=callback_url,
            enable_fallback=True  # Fallback на Flux если GPT-4o недоступен
        )
    
    async def generate_carousel_images(
        self,
        content: CarouselContent,
        callback_url: Optional[str] = None
    ) -> list[dict]:
        """Генерирует изображения для всех слайдов через 4o Image API"""
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
            
            # Небольшая задержка между запросами
            await asyncio.sleep(1)
        
        return tasks
    
    async def wait_for_image(self, task_id: str, timeout: int = 300, poll_interval: int = 10) -> Optional[str]:
        """Ожидает завершения генерации 4o Image"""
        elapsed = 0
        
        while elapsed < timeout:
            result = await kieai_service.get_4o_image_status(task_id)
            
            if result.get("code") != 200:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue
            
            data = result.get("data", {})
            success_flag = data.get("successFlag")
            
            # successFlag: 0 = generating, 1 = success, 2 = failed
            if success_flag == 1:
                # Успешно завершено
                response = data.get("response", {})
                if isinstance(response, dict):
                    urls = response.get("result_urls", [])
                    if urls:
                        return urls[0]
                
                # Альтернативный путь для resultUrls
                result_urls = data.get("resultUrls", [])
                if result_urls:
                    return result_urls[0]
                
                return None
            
            elif success_flag == 2:
                # Ошибка генерации
                error_msg = data.get("errorMessage", "Unknown error")
                print(f"4o Image generation failed: {error_msg}")
                return None
            
            # success_flag == 0, ещё генерируется
            progress = data.get("progress", "0.00")
            print(f"4o Image progress: {float(progress) * 100:.1f}%")
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        return None

carousel_service = CarouselService()