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

# ИСПРАВЛЕНО: Geometria для текста + Noto Color Emoji для эмодзи
TEMPLATE_CONFIGS = {
    "light": {
        "file": "templates/carousel/light.png",
        "title": {
            "font": "fonts/Geometria-Bold.otf",
            "fallback_font": "fonts/NotoColorEmoji.ttf",
            "size": 70,
            "color": "292627",  
            "max_chars": 50,
            "y": 200,  
            "line_spacing": 8,
            "max_width": 635,
        },
        "text": {
            "font": "fonts/Geometria.otf",
            "fallback_font": "fonts/NotoColorEmoji.ttf",
            "size": 48,
            "color": "292627",
            "max_chars": 120,
            "line_spacing": 8,
            "max_width": 620,
        }
    },
    "dark": {
        "file": "templates/carousel/dark.png",
        "title": {
            "font": "fonts/Geometria-Bold.otf",
            "fallback_font": "fonts/NotoColorEmoji.ttf",
            "size": 70,
            "color": "f7e9d0",
            "max_chars": 50,
            "y": 200,
            "line_spacing": 8,
            "max_width": 750,
        },
        "text": {
            "font": "fonts/Geometria.otf",
            "fallback_font": "fonts/NotoColorEmoji.ttf",
            "size": 48,
            "color": "f7e9d0",
            "max_chars": 120,
            "line_spacing": 8,
            "max_width": 750,
        }
    },
    "gradient": {
        "file": "templates/carousel/gradient.png",
        "title": {
            "font": "fonts/Geometria-Bold.otf",
            "fallback_font": "fonts/NotoColorEmoji.ttf",
            "size": 70,
            "color": "ffffff",
            "max_chars": 50,
            "y": 200,
            "line_spacing": 8,
            "max_width": 750,
        },
        "text": {
            "font": "fonts/Geometria.otf",
            "fallback_font": "fonts/NotoColorEmoji.ttf",
            "size": 48,
            "color": "ffffff",
            "max_chars": 120,
            "line_spacing": 8,
            "max_width": 750,
        }
    }
}

class CarouselService:
    def __init__(self):
        pass
    
    def is_available(self) -> bool:
        """Синхронная проверка (только OpenAI)"""
        return openai_service.is_available()
    
    async def _check_ffmpeg(self) -> bool:
        """Проверяет доступность FFmpeg (асинхронно)"""
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            return process.returncode == 0
        except (FileNotFoundError, Exception) as e:
            logger.error(f"FFmpeg check failed: {e}")
            return False
    
    async def is_available_async(self) -> bool:
        """Асинхронная проверка доступности сервиса"""
        has_openai = openai_service.is_available()
        has_ffmpeg = await self._check_ffmpeg()
        return has_openai and has_ffmpeg
    
    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Обрезает текст до максимального количества символов"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars-3] + "..."
    
    def _wrap_text_justified(self, text: str, max_width_px: int, font_size: int, font_weight: str = "normal") -> list[str]:
        """Перенос текста с выравниванием по ширине"""
        char_width = font_size * 0.6
        chars_per_line = int(max_width_px / char_width)
        
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            word_length = len(word) + (1 if current_line else 0)
            
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

КРИТИЧЕСКИ ВАЖНЫЕ ОГРАНИЧЕНИЯ ПО ДЛИНЕ:
- Заголовки: СТРОГО 50 символов МАКСИМУМ (включая эмодзи)
- Текст слайда: СТРОГО 120 символов МАКСИМУМ (включая эмодзи)
- Это жёсткие лимиты - превышение приведёт к обрезке текста!

СМАЙЛИКИ:
- Добавляй МАКСИМУМ 1-2 ПОДХОДЯЩИХ смайлика на слайд
- Смайлики должны усиливать смысл, не быть случайными
- Размещай в начале или в конце ключевых мыслей
- Примеры: 💡 для идей, ✅ для преимуществ, 🚀 для действий, 💰 для денег, 📈 для роста
- ВАЖНО: Смайлики учитываются в лимите символов!

БАЗА ЗНАНИЙ:
{kb_content[:2000] if kb_content else 'Пуста.'}

Ответь JSON:
{{"slides": [{{"slide_number": 1, "slide_type": "cover", "title": "...", "content": "..."}}]}}

ПРОВЕРЬ перед отправкой:
- Каждый заголовок <= 50 символов
- Каждый текст <= 120 символов"""

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
        
        template_config = TEMPLATE_CONFIGS.get(color_scheme)
        if not template_config:
            raise ValueError(f"Неизвестная цветовая схема: {color_scheme}")
        
        template_path = template_config["file"]
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Шаблон не найден: {template_path}")
        
        title_cfg = template_config["title"]
        text_cfg = template_config["text"]
        
        # Получаем абсолютные пути к шрифтам
        title_font = os.path.abspath(title_cfg["font"])
        text_font = os.path.abspath(text_cfg["font"])
        emoji_font = os.path.abspath(title_cfg["fallback_font"])
        
        # Проверяем существование шрифтов
        if not os.path.exists(title_font):
            raise FileNotFoundError(f"Шрифт заголовка не найден: {title_font}")
        if not os.path.exists(text_font):
            raise FileNotFoundError(f"Шрифт текста не найден: {text_font}")
        if not os.path.exists(emoji_font):
            logger.warning(f"Шрифт эмодзи не найден: {emoji_font}")
        
        logger.info(f"Title font: {title_font}")
        logger.info(f"Text font: {text_font}")
        logger.info(f"Emoji font: {emoji_font}")
        
        # Обрезаем текст под лимиты
        title = self._truncate_text(slide.title, title_cfg["max_chars"])
        content = self._truncate_text(slide.content, text_cfg["max_chars"]) if slide.content else ""
        
        # Разбиваем на строки
        title_lines = self._wrap_text_justified(
            title, 
            title_cfg["max_width"], 
            title_cfg["size"],
            "bold"
        )
        
        content_lines = []
        if content:
            content_lines = self._wrap_text_justified(
                content,
                text_cfg["max_width"],
                text_cfg["size"],
                "normal"
            )
        
        # Расчёт позиций
        title_start_y = title_cfg["y"]
        title_font_size = title_cfg["size"]
        title_line_spacing = title_cfg["line_spacing"]
        
        title_lines_count = len(title_lines)
        if title_lines_count > 0:
            title_height = title_lines_count * (title_font_size + title_line_spacing)
        else:
            title_height = 0
        
        content_start_y = title_start_y + title_height + 60
        
        logger.info(f"Title lines: {title_lines_count}, height: {title_height}")
        logger.info(f"Content start Y: {content_start_y}")
        logger.info(f"Content lines: {len(content_lines)}")
        
        # Создаем временный файл
        output_fd, output_path = tempfile.mkstemp(suffix=".png")
        os.close(output_fd)
        
        try:
            filters = []
            
            # === ЗАГОЛОВОК ===
            if title_lines:
                for i, line in enumerate(title_lines):
                    # Правильное экранирование для FFmpeg
                    line_escaped = line.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")
                    y_pos = title_start_y + (i * (title_font_size + title_line_spacing))
                    
                    # Используем абсолютный путь и правильно экранируем
                    title_filter = (
                        f"drawtext="
                        f"text='{line_escaped}':"
                        f"fontfile='{title_font}':"
                        f"fontsize={title_cfg['size']}:"
                        f"fontcolor=0x{title_cfg['color']}:"
                        f"x=(w*0.13):"
                        f"y={y_pos}"
                    )
                    
                    filters.append(title_filter)
                    logger.info(f"Title line {i+1}: y={y_pos}, text={line[:30]}...")
            
            # === ОСНОВНОЙ ТЕКСТ ===
            text_start_y = content_start_y
            if content_lines:
                text_font_size = text_cfg["size"]
                text_line_spacing = text_cfg["line_spacing"]
                
                for i, line in enumerate(content_lines):
                    # Правильное экранирование для FFmpeg
                    line_escaped = line.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")
                    y_pos = text_start_y + (i * (text_font_size + text_line_spacing))
                    
                    if y_pos > 1650:
                        logger.warning(f"Content line {i+1} exceeds bounds (y={y_pos}), skipping")
                        break
                    
                    text_filter = (
                        f"drawtext="
                        f"text='{line_escaped}':"
                        f"fontfile='{text_font}':"
                        f"fontsize={text_cfg['size']}:"
                        f"fontcolor=0x{text_cfg['color']}:"
                        f"x=(w*0.13):"
                        f"y={y_pos}"
                    )
                    
                    filters.append(text_filter)
                    logger.info(f"Content line {i+1}: y={y_pos}, text={line[:30]}...")
            
            # === ИНДИКАТОР СЛАЙДА ===
            indicator_text = f"{slide.slide_number}/{slide.total_slides}"
            indicator_escaped = indicator_text.replace("\\", "\\\\").replace("'", "\\'")
            indicator_filter = (
                f"drawtext="
                f"text='{indicator_escaped}':"
                f"fontfile='{title_font}':"
                f"fontsize=28:"
                f"fontcolor=0xffffff:"
                f"x=(w-tw-40):"
                f"y=(h-th-40)"
            )
            filters.append(indicator_filter)
            
            # Объединяем все фильтры
            filter_complex = ",".join(filters)
            
            logger.info(f"Filter complex: {filter_complex[:200]}...")
            
            # Запускаем FFmpeg
            cmd = [
                "ffmpeg", "-y",
                "-i", template_path,
                "-vf", filter_complex,
                "-frames:v", "1",
                "-q:v", "2",
                output_path
            ]
            
            logger.info(f"Running FFmpeg command...")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f"FFmpeg error output: {error_msg}")
                raise Exception(f"FFmpeg failed with return code {process.returncode}")
            
            # Читаем результат
            if not os.path.exists(output_path):
                raise Exception("Output file was not created")
                
            with open(output_path, 'rb') as f:
                result = f.read()
                
            if len(result) == 0:
                raise Exception("Output file is empty")
                
            logger.info(f"Successfully generated image, size: {len(result)} bytes")
            return result
        
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
        """Генерирует изображения для всех слайдов"""
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
                logger.error(f"Failed to generate slide {slide.slide_number}: {e}", exc_info=True)
                results.append({
                    "slide_number": slide.slide_number,
                    "image_data": None,
                    "status": "error",
                    "error": str(e)
                })
            
            await asyncio.sleep(0.5)
        
        return results

carousel_service = CarouselService()