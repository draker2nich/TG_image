import asyncio
import json
import os
import tempfile
import subprocess
from typing import Optional
from dataclasses import dataclass
from config import config
from services.openai_service import openai_service

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

# Параметры шаблонов
TEMPLATE_CONFIGS = {
    "light": {
        "file": "templates/carousel/light.png",
        "title": {
            "font": "Geometria-Bold",
            "size": 22,
            "color": "2a292a",
            "max_chars": 33,
            "x": 630,
            "y": 316,
            "w": 718,
            "h": 320
        },
        "text": {
            "font": "Geometria",
            "size": 14,
            "color": "2a292a",
            "max_chars": 80,
            "x": 630,
            "y": 650,
            "w": 718,
            "h": 320
        }
    },
    "dark": {
        "file": "templates/carousel/dark.png",
        "title": {
            "font": "Geometria-Bold",
            "size": 12,
            "color": "fbeacb",
            "max_chars": 26,
            "x": 530,
            "y": 196,
            "w": 718,
            "h": 180
        },
        "text": {
            "font": "Geometria",
            "size": 8,
            "color": "fbeacb",
            "max_chars": 80,
            "x": 650,
            "y": 440,
            "w": 718,
            "h": 320
        }
    },
    "gradient": {
        "file": "templates/carousel/gradient.png",
        "title": {
            "font": "Geometria-Bold",
            "size": 12,
            "color": "fbfdfb",
            "max_chars": 33,
            "x": 530,
            "y": 670,
            "w": 718,
            "h": 180
        },
        "text": {
            "font": "Geometria",
            "size": 8,
            "color": "fbfdfb",
            "max_chars": 80,
            "x": 650,
            "y": 440,
            "w": 718,
            "h": 320
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
    
    def _wrap_text(self, text: str, max_width: int, font_size: int) -> list[str]:
        """
        Разбивает текст на строки с учетом максимальной ширины
        Простая эвристика: примерно 0.6 * font_size пикселей на символ
        """
        chars_per_line = int(max_width / (font_size * 0.6))
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            word_length = len(word) + 1  # +1 для пробела
            if current_length + word_length > chars_per_line and current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length
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
- Заголовки: МАКСИМУМ 33 символа (для светлого/градиент) или 26 символов (для темного)
- Текст слайда: МАКСИМУМ 80 символов
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
        """
        Генерирует изображение слайда наложением текста на шаблон через FFmpeg
        
        Returns:
            bytes изображения PNG
        """
        # Получаем конфигурацию шаблона
        template_config = TEMPLATE_CONFIGS.get(color_scheme)
        if not template_config:
            raise ValueError(f"Неизвестная цветовая схема: {color_scheme}")
        
        template_path = template_config["file"]
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Шаблон не найден: {template_path}")
        
        # Обрезаем текст под лимиты
        title_config = template_config["title"]
        text_config = template_config["text"]
        
        title = self._truncate_text(slide.title, title_config["max_chars"])
        content = self._truncate_text(slide.content, text_config["max_chars"])
        
        # Разбиваем контент на строки
        content_lines = self._wrap_text(content, text_config["w"], text_config["size"])
        
        # Создаем временный файл для вывода
        output_fd, output_path = tempfile.mkstemp(suffix=".png")
        os.close(output_fd)
        
        try:
            # Собираем FFmpeg фильтры для наложения текста
            filters = []
            
            # Заголовок
            title_escaped = title.replace("'", "'\\''").replace(":", "\\:")
            title_filter = (
                f"drawtext=text='{title_escaped}':"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"fontsize={title_config['size']}:"
                f"fontcolor=#{title_config['color']}:"
                f"x={title_config['x']}:y={title_config['y']}:"
                f"line_spacing=5"
            )
            filters.append(title_filter)
            
            # Контент (многострочный)
            line_height = text_config["size"] + 5
            for i, line in enumerate(content_lines):
                line_escaped = line.replace("'", "'\\''").replace(":", "\\:")
                y_offset = text_config['y'] + (i * line_height)
                
                content_filter = (
                    f"drawtext=text='{line_escaped}':"
                    f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
                    f"fontsize={text_config['size']}:"
                    f"fontcolor=#{text_config['color']}:"
                    f"x={text_config['x']}:y={y_offset}"
                )
                filters.append(content_filter)
            
            # Индикатор слайда (внизу справа)
            indicator_text = f"{slide.slide_number}/{slide.total_slides}"
            indicator_escaped = indicator_text.replace("'", "'\\''")
            indicator_filter = (
                f"drawtext=text='{indicator_escaped}':"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
                f"fontsize=12:"
                f"fontcolor=#999999:"
                f"x=w-tw-20:y=h-th-20"
            )
            filters.append(indicator_filter)
            
            # Объединяем фильтры
            filter_complex = ",".join(filters)
            
            # Запускаем FFmpeg
            cmd = [
                "ffmpeg", "-y",
                "-i", template_path,
                "-vf", filter_complex,
                "-frames:v", "1",
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode()[:500]
                raise Exception(f"FFmpeg error: {error_msg}")
            
            # Читаем результат
            with open(output_path, 'rb') as f:
                return f.read()
        
        finally:
            # Удаляем временный файл
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
            
            # Небольшая задержка между слайдами
            await asyncio.sleep(0.5)
        
        return results

carousel_service = CarouselService()