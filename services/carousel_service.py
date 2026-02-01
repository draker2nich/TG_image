import asyncio
import json
import os
import io
import logging
from typing import Optional
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont
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

# Конфигурация шаблонов
TEMPLATE_CONFIGS = {
    "light": {
        "file": "templates/carousel/light.png",
        "title": {
            "font": "fonts/Geometria-Bold.otf",
            "emoji_font": "fonts/NotoColorEmoji.ttf",
            "size": 70,
            "color": (41, 38, 39),
            "max_chars": 50,
            "y": 200,
            "x_percent": 0.13,
            "line_spacing": 8,
            "max_width_percent": 0.74,
        },
        "text": {
            "font": "fonts/Geometria.otf",
            "emoji_font": "fonts/NotoColorEmoji.ttf",
            "size": 48,
            "color": (41, 38, 39),
            "max_chars": 120,
            "line_spacing": 8,
            "max_width_percent": 0.74,
        }
    },
    "dark": {
        "file": "templates/carousel/dark.png",
        "title": {
            "font": "fonts/Geometria-Bold.otf",
            "emoji_font": "fonts/NotoColorEmoji.ttf",
            "size": 70,
            "color": (247, 233, 208),
            "max_chars": 50,
            "y": 200,
            "x_percent": 0.13,
            "line_spacing": 8,
            "max_width_percent": 0.74,
        },
        "text": {
            "font": "fonts/Geometria.otf",
            "emoji_font": "fonts/NotoColorEmoji.ttf",
            "size": 48,
            "color": (247, 233, 208),
            "max_chars": 120,
            "line_spacing": 8,
            "max_width_percent": 0.74,
        }
    },
    "gradient": {
        "file": "templates/carousel/gradient.png",
        "title": {
            "font": "fonts/Geometria-Bold.otf",
            "emoji_font": "fonts/NotoColorEmoji.ttf",
            "size": 70,
            "color": (255, 255, 255),
            "max_chars": 50,
            "y": 200,
            "x_percent": 0.13,
            "line_spacing": 8,
            "max_width_percent": 0.74,
        },
        "text": {
            "font": "fonts/Geometria.otf",
            "emoji_font": "fonts/NotoColorEmoji.ttf",
            "size": 48,
            "color": (255, 255, 255),
            "max_chars": 120,
            "line_spacing": 8,
            "max_width_percent": 0.74,
        }
    }
}


class CarouselService:
    def __init__(self):
        self._font_cache = {}
    
    def is_available(self) -> bool:
        return openai_service.is_available()
    
    def _get_font(self, font_path: str, size: int) -> ImageFont.FreeTypeFont:
        """Кэширует загруженные шрифты"""
        cache_key = f"{font_path}_{size}"
        if cache_key not in self._font_cache:
            try:
                self._font_cache[cache_key] = ImageFont.truetype(font_path, size)
            except Exception as e:
                logger.warning(f"Failed to load font {font_path}: {e}, using default")
                self._font_cache[cache_key] = ImageFont.load_default()
        return self._font_cache[cache_key]
    
    def _is_emoji(self, char: str) -> bool:
        """Проверяет, является ли символ эмодзи"""
        code = ord(char)
        emoji_ranges = [
            (0x1F300, 0x1F9FF),  # Miscellaneous Symbols and Pictographs
            (0x2600, 0x26FF),    # Miscellaneous Symbols
            (0x2700, 0x27BF),    # Dingbats
            (0x1F600, 0x1F64F),  # Emoticons
            (0x1F680, 0x1F6FF),  # Transport and Map
            (0x1F1E0, 0x1F1FF),  # Flags
            (0x2300, 0x23FF),    # Miscellaneous Technical
            (0x2B50, 0x2B55),    # Stars
            (0x200D, 0x200D),    # ZWJ
            (0xFE0F, 0xFE0F),    # Variation Selector
            (0x1FA00, 0x1FA6F),  # Chess, cards
            (0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended-A
            (0x231A, 0x231B),    # Watch, Hourglass
            (0x23E9, 0x23F3),    # AV symbols
            (0x23F8, 0x23FA),    # AV symbols
            (0x25AA, 0x25AB),    # Squares
            (0x25B6, 0x25B6),    # Play
            (0x25C0, 0x25C0),    # Reverse
            (0x25FB, 0x25FE),    # Squares
            (0x2614, 0x2615),    # Umbrella, Coffee
            (0x2648, 0x2653),    # Zodiac
            (0x267F, 0x267F),    # Wheelchair
            (0x2693, 0x2693),    # Anchor
            (0x26A1, 0x26A1),    # High Voltage
            (0x26AA, 0x26AB),    # Circles
            (0x26BD, 0x26BE),    # Soccer, Baseball
            (0x26C4, 0x26C5),    # Snowman, Sun
            (0x26CE, 0x26CE),    # Ophiuchus
            (0x26D4, 0x26D4),    # No Entry
            (0x26EA, 0x26EA),    # Church
            (0x26F2, 0x26F3),    # Fountain, Golf
            (0x26F5, 0x26F5),    # Sailboat
            (0x26FA, 0x26FA),    # Tent
            (0x26FD, 0x26FD),    # Fuel Pump
            (0x2702, 0x2702),    # Scissors
            (0x2705, 0x2705),    # Check Mark
            (0x2708, 0x270D),    # Airplane etc
            (0x270F, 0x270F),    # Pencil
            (0x2712, 0x2712),    # Black Nib
            (0x2714, 0x2714),    # Check Mark
            (0x2716, 0x2716),    # X Mark
            (0x271D, 0x271D),    # Cross
            (0x2721, 0x2721),    # Star of David
            (0x2728, 0x2728),    # Sparkles
            (0x2733, 0x2734),    # Eight Spoked
            (0x2744, 0x2744),    # Snowflake
            (0x2747, 0x2747),    # Sparkle
            (0x274C, 0x274C),    # Cross Mark
            (0x274E, 0x274E),    # Cross Mark
            (0x2753, 0x2755),    # Question Marks
            (0x2757, 0x2757),    # Exclamation
            (0x2763, 0x2764),    # Hearts
            (0x2795, 0x2797),    # Plus, Minus, Division
            (0x27A1, 0x27A1),    # Right Arrow
            (0x27B0, 0x27B0),    # Curly Loop
            (0x27BF, 0x27BF),    # Double Curly
            (0x2934, 0x2935),    # Arrows
            (0x2B05, 0x2B07),    # Arrows
            (0x2B1B, 0x2B1C),    # Squares
            (0x3030, 0x3030),    # Wavy Dash
            (0x303D, 0x303D),    # Part Alternation
            (0x3297, 0x3297),    # Circled Ideograph
            (0x3299, 0x3299),    # Circled Ideograph
        ]
        return any(start <= code <= end for start, end in emoji_ranges)
    
    def _split_text_and_emoji(self, text: str) -> list[tuple[str, bool]]:
        """Разбивает текст на сегменты: (текст, is_emoji)"""
        if not text:
            return []
        
        segments = []
        current_segment = ""
        current_is_emoji = self._is_emoji(text[0])
        
        for char in text:
            char_is_emoji = self._is_emoji(char)
            if char_is_emoji == current_is_emoji:
                current_segment += char
            else:
                if current_segment:
                    segments.append((current_segment, current_is_emoji))
                current_segment = char
                current_is_emoji = char_is_emoji
        
        if current_segment:
            segments.append((current_segment, current_is_emoji))
        
        return segments
    
    def _draw_text_with_emoji(
        self,
        draw: ImageDraw.ImageDraw,
        image: Image.Image,
        text: str,
        position: tuple[int, int],
        text_font: ImageFont.FreeTypeFont,
        emoji_font: ImageFont.FreeTypeFont,
        color: tuple[int, int, int]
    ) -> int:
        """Рисует текст с поддержкой эмодзи"""
        x, y = position
        segments = self._split_text_and_emoji(text)
        
        for segment_text, is_emoji in segments:
            if is_emoji:
                try:
                    bbox = emoji_font.getbbox(segment_text)
                    if bbox:
                        emoji_y = y - 5
                        draw.text((x, emoji_y), segment_text, font=emoji_font, fill=color)
                        x += bbox[2] - bbox[0]
                    else:
                        draw.text((x, y), segment_text, font=text_font, fill=color)
                        bbox = text_font.getbbox(segment_text)
                        if bbox:
                            x += bbox[2] - bbox[0]
                except Exception as e:
                    logger.warning(f"Failed to draw emoji: {e}")
                    draw.text((x, y), "□", font=text_font, fill=color)
                    x += text_font.getbbox("□")[2]
            else:
                draw.text((x, y), segment_text, font=text_font, fill=color)
                bbox = text_font.getbbox(segment_text)
                if bbox:
                    x += bbox[2] - bbox[0]
        
        return x - position[0]
    
    def _truncate_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars-3] + "..."
    
    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Переносит текст по словам"""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0] if bbox else 0
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
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

СМАЙЛИКИ:
- Добавляй 1-2 ПОДХОДЯЩИХ смайлика на слайд
- Примеры: 💡 для идей, ✅ для преимуществ, 🚀 для действий, 💰 для денег, 📈 для роста
- Смайлики учитываются в лимите символов!

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
    
    async def generate_slide_image(self, slide: CarouselSlide, color_scheme: str = "dark") -> bytes:
        """Генерирует изображение слайда через Pillow с поддержкой эмодзи"""
        
        logger.info(f"=== Generating slide {slide.slide_number} with Pillow ===")
        logger.info(f"Title: {slide.title}")
        logger.info(f"Content: {slide.content}")
        
        template_config = TEMPLATE_CONFIGS.get(color_scheme)
        if not template_config:
            raise ValueError(f"Неизвестная цветовая схема: {color_scheme}")
        
        template_path = template_config["file"]
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Шаблон не найден: {template_path}")
        
        image = Image.open(template_path).convert("RGBA")
        draw = ImageDraw.Draw(image)
        
        img_width, img_height = image.size
        
        title_cfg = template_config["title"]
        text_cfg = template_config["text"]
        
        title_font = self._get_font(title_cfg["font"], title_cfg["size"])
        text_font = self._get_font(text_cfg["font"], text_cfg["size"])
        
        emoji_font_path = title_cfg.get("emoji_font", "fonts/NotoColorEmoji.ttf")
        # Пробуем разные шрифты для эмодзи
        emoji_font = None
        for font_path in [emoji_font_path, "fonts/Symbola.otf", "fonts/NotoEmoji-Regular.ttf"]:
            if os.path.exists(font_path):
                try:
                    emoji_font = self._get_font(font_path, title_cfg["size"])
                    logger.info(f"Using emoji font: {font_path}")
                    break
                except:
                    continue
        if not emoji_font:
            emoji_font = title_font
            logger.warning("No emoji font available, using text font")
        
        title = self._truncate_text(slide.title, title_cfg["max_chars"])
        content = self._truncate_text(slide.content, text_cfg["max_chars"]) if slide.content else ""
        
        x_start = int(img_width * title_cfg["x_percent"])
        max_width = int(img_width * title_cfg["max_width_percent"])
        
        title_lines = self._wrap_text(title, title_font, max_width)
        content_lines = self._wrap_text(content, text_font, max_width) if content else []
        
        y = title_cfg["y"]
        for line in title_lines:
            self._draw_text_with_emoji(draw, image, line, (x_start, y), title_font, emoji_font, title_cfg["color"])
            y += title_cfg["size"] + title_cfg["line_spacing"]
        
        y += 40
        
        try:
            text_emoji_font = self._get_font(emoji_font_path, text_cfg["size"])
        except:
            text_emoji_font = text_font
        
        for line in content_lines:
            if y > img_height - 200:
                break
            self._draw_text_with_emoji(draw, image, line, (x_start, y), text_font, text_emoji_font, text_cfg["color"])
            y += text_cfg["size"] + text_cfg["line_spacing"]
        
        indicator = f"{slide.slide_number}/{slide.total_slides}"
        indicator_font = self._get_font(title_cfg["font"], 28)
        indicator_bbox = indicator_font.getbbox(indicator)
        indicator_width = indicator_bbox[2] - indicator_bbox[0]
        indicator_height = indicator_bbox[3] - indicator_bbox[1]
        
        draw.text(
            (img_width - indicator_width - 40, img_height - indicator_height - 40),
            indicator,
            font=indicator_font,
            fill=(255, 255, 255)
        )
        
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", quality=95)
        buffer.seek(0)
        
        result = buffer.getvalue()
        logger.info(f"Successfully generated image, size: {len(result)} bytes")
        
        return result
    
    async def generate_carousel_images(self, content: CarouselContent) -> list[dict]:
        """Генерирует изображения для всех слайдов"""
        results = []
        
        for slide in content.slides:
            try:
                image_data = await self.generate_slide_image(slide=slide, color_scheme=content.color_scheme)
                
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
            
            await asyncio.sleep(0.1)
        
        return results


carousel_service = CarouselService()