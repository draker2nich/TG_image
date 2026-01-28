import asyncio
import json
import os
import tempfile
import subprocess
import logging
from typing import Optional
from dataclasses import dataclass
from config import config
from services.openai_service import openai_service

logger = logging.getLogger(__name__)

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

# УЛУЧШЕННЫЕ параметры шаблонов для качественного отображения текста
TEMPLATE_CONFIGS = {
    "light": {
        "file": "templates/carousel/light.png",
        "title": {
            "font": "fonts/Geomrtria-Bold.ttf",
            "size": 60,
            "color": "292627",  
            "max_chars": 60,
            "y": 200,  
            "line_spacing": 8,
            "max_width": 635,  
        },
        "text": {
            "font": "fonts/Geomrtria-Light.ttf",
            "size": 38,
            "color": "292627",
            "max_chars": 450,
            "line_spacing": 8,
            "max_width": 620,
        }
    },
    "dark": {
        "file": "templates/carousel/dark.png",
        "title": {
            "font": "fonts/Geomrtria-Bold.ttf",
            "size": 60,
            "color": "f7e9d0",
            "max_chars": 60,
            "y": 200,
            "line_spacing": 8,
            "max_width": 750,
        },
        "text": {
            "font": "fonts/Geomrtria-Light.ttf",
            "size": 38,
            "color": "f7e9d0",
            "max_chars": 450,
            "line_spacing": 8,
            "max_width": 750,
        }
    },
    "gradient": {
        "file": "templates/carousel/gradient.png",
        "title": {
            "font": "fonts/Geomrtria-Bold.ttf",
            "size": 60,
            "color": "ffffff",
            "max_chars": 60,
            "y": 200,  # Внизу для градиента
            "line_spacing": 8,
            "max_width": 750,
        },
        "text": {
            "font": "fonts/Geomrtria-Light.ttf",
            "size": 38,
            "color": "ffffff",
            "max_chars": 450,
            "line_spacing": 8,
            "max_width": 750,
        }
    }
}

class CarouselService:
    def __init__(self):
        pass
    
    def is_available(self) -> bool:
        return openai_service.is_available() and self._check_ffmpeg()
    
    def _check_ffmpeg(self) -> bool:
        """Проверяет доступность FFmpeg"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Обрезает текст до максимального количества символов"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars-3] + "..."
    
    def _wrap_text_improved(self, text: str, max_width_px: int, font_size: int, font_weight: str = "normal") -> list[str]:
        """
        Улучшенный перенос текста с учетом реальной ширины символов
        
        Примерные множители ширины:
        - Normal font: ~0.55 от font_size
        - Bold font: ~0.62 от font_size
        """
        char_width = font_size * (0.62 if "Bold" in font_weight else 0.55)
        chars_per_line = int(max_width_px / char_width)
        
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            word_length = len(word) + (1 if current_line else 0)  # +1 для пробела
            
            if current_length + word_length > chars_per_line and current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
            else:
                current_line.append(word)
                current_length += word_length
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
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

ВАЖНЫЕ ОГРАНИЧЕНИЯ ПО ДЛИНЕ:
- Заголовки: МАКСИМУМ 60 символов (для хорошей читаемости)
- Текст слайда: МАКСИМУМ 140 символов
- Используй короткие, емкие фразы
- НЕ используй эмодзи

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
    
    async def generate_slide_image(
        self,
        slide: CarouselSlide,
        color_scheme: str = "dark"
    ) -> bytes:

        logger.info(f"=== Generating slide {slide.slide_number} ===")
        logger.info(f"Title: {slide.title}")
        logger.info(f"Content: {slide.content}")
        logger.info(f"Color scheme: {color_scheme}")
        
        template_config = TEMPLATE_CONFIGS.get(color_scheme)
        if not template_config:
            raise ValueError(f"Неизвестная цветовая схема: {color_scheme}")
        
        template_path = template_config["file"]
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Шаблон не найден: {template_path}")
        
        # Конфигурации для заголовка и текста
        title_cfg = template_config["title"]
        text_cfg = template_config["text"]
        
        # ИСПРАВЛЕНИЕ: Обрезаем текст под лимиты
        title = self._truncate_text(slide.title, title_cfg["max_chars"])
        # Используем content, НЕ пустую строку
        content = self._truncate_text(slide.content, text_cfg["max_chars"]) if slide.content else ""
        
        # Разбиваем на строки с учетом реальной ширины
        title_lines = self._wrap_text_improved(
            title, 
            title_cfg["max_width"], 
            title_cfg["size"],
            title_cfg["font"]
        )
        
        title_start_y = title_cfg["y"]
        title_font_size = title_cfg["size"]
        title_line_spacing = title_cfg["line_spacing"]

        title_lines_count = len(title_lines)

        if title_lines_count > 0:
            title_height = (
                title_lines_count * title_font_size
                + (title_lines_count - 1) * title_line_spacing
            )
        else:
            title_height = 0

        content_start_y = title_start_y + title_height + 40
        content_lines = []
        if content:
            content_lines = self._wrap_text_improved(
                content,
                text_cfg["max_width"],
                text_cfg["size"],
                text_cfg["font"]
            )
        
        # Создаем временный файл
        output_fd, output_path = tempfile.mkstemp(suffix=".png")
        os.close(output_fd)
        
        try:
            filters = []
            
            # === ЗАГОЛОВОК (ОБЯЗАТЕЛЬНО РИСУЕМ) ===
            title_start_y = title_cfg["y"]
            if title_lines:  # Проверяем что есть заголовок
                for i, line in enumerate(title_lines):
                    line_escaped = line.replace("'", "'\\''").replace(":", "\\:").replace(",", "\\,")
                    y_pos = title_start_y + (i * (title_cfg["size"] + title_cfg["line_spacing"]))
                    
                    # Основной текст с обводкой и тенью
                    title_filter = (
                        f"drawtext=text='{line_escaped}':"
                        f"fontfile=fonts/Geomrtria-Bold.ttf:"
                        f"fontsize={title_cfg['size']}:"
                        f"fontcolor=#{title_cfg['color']}:"
                        f"x=w*0.13:"  # Центрирование
                        f"y={y_pos}:"
                    )
                    
                    # Добавляем тень если нужно
                    if title_cfg.get("shadow"):
                        title_filter += f"shadowx=3:shadowy=3:shadowcolor=black@0.5:"
                    
                    title_filter = title_filter.rstrip(":")
                    filters.append(title_filter)
                    
                    logger.info(f"Added title filter for line {i+1}: {line[:30]}...")
            
            # === ОСНОВНОЙ ТЕКСТ (КОНТЕНТ СЛАЙДА) ===
            text_start_y = content_start_y
            if content_lines:  # Проверяем что есть контент
                for i, line in enumerate(content_lines):
                    line_escaped = line.replace("'", "'\\''").replace(":", "\\:").replace(",", "\\,")
                    y_pos = text_start_y + (i * (text_cfg["size"] + text_cfg["line_spacing"]))
                    
                    text_filter = (
                        f"drawtext=text='{line_escaped}':"
                        f"fontfile=fonts/Geomrtria-Bold.ttf:"
                        f"fontsize={text_cfg['size']}:"
                        f"fontcolor=#{text_cfg['color']}:"
                        f"x=w*0.13:"
                        f"y={y_pos}:"
                    )
                    
                    if text_cfg.get("shadow"):
                        text_filter += f"shadowx=2:shadowy=2:shadowcolor=black@0.5:"
                    
                    text_filter = text_filter.rstrip(":")
                    filters.append(text_filter)
                    
                    logger.info(f"Added content filter for line {i+1}: {line[:30]}...")
            
            # === ИНДИКАТОР СЛАЙДА ===
            indicator_text = f"{slide.slide_number}/{slide.total_slides}"
            indicator_escaped = indicator_text.replace("'", "'\\''")
            indicator_filter = (
                f"drawtext=text='{indicator_escaped}':"
                f"fontfile=fonts/Geomrtria-Bold.ttf:"
                f"fontsize=28:"
                f"fontcolor=#ffffff:"
                f"x=w-tw-40:y=h-th-40"
            )
            filters.append(indicator_filter)
            
            # Объединяем все фильтры
            filter_complex = ",".join(filters)
            
            # Запускаем FFmpeg
            cmd = [
                "ffmpeg", "-y",
                "-i", template_path,
                "-vf", filter_complex,
                "-frames:v", "1",
                "-q:v", "2",  # Высокое качество
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode()[:1000]
                raise Exception(f"FFmpeg error: {error_msg}")
            
            # Читаем результат
            with open(output_path, 'rb') as f:
                return f.read()
        
        finally:
            if os.path.exists(output_path):
                try:
                    os.unlink(output_path)
                except:
                    pass
    
    async def generate_carousel_images(
        self,
        content: CarouselContent
    ) -> list[dict]:
        """
        Генерирует изображения для всех слайдов
        
        Returns:
            list[dict] с полями: slide_number, image_data (bytes), status
        """
        results = []
        
        for slide in content.slides:
            try:
                image_data = await self.generate_slide_image(
                    slide=slide,
                    color_scheme=content.color_scheme
                )
                
                results.append({
                    "slide_number": slide.slide_number,
                    "image_data": image_data,
                    "status": "success"
                })
            except Exception as e:
                results.append({
                    "slide_number": slide.slide_number,
                    "image_data": None,
                    "status": "error",
                    "error": str(e)
                })
            
            await asyncio.sleep(0.5)
        
        return results

carousel_service = CarouselService()