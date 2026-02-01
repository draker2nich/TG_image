import os
import json
from openai import AsyncOpenAI
from config import config

COMPETITORS_FILE = os.path.join(config.KNOWLEDGE_BASE_DIR, "competitors.json")

class OpenAIService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None
        self.model = config.OPENAI_MODEL
    
    def is_available(self) -> bool:
        return self.client is not None
    
    def _read_docx(self, filepath: str) -> str:
        """Читает содержимое .docx файла"""
        try:
            from docx import Document
            doc = Document(filepath)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except ImportError:
            return f"[Ошибка: python-docx не установлен для чтения {filepath}]"
        except Exception as e:
            return f"[Ошибка чтения {filepath}: {e}]"
    
    def _load_files_from_dir(self, dir_path: str) -> list[tuple[str, str]]:
        """Загружает все файлы из директории, возвращает список (filename, content)"""
        if not os.path.exists(dir_path):
            return []
        
        files_content = []
        for filename in os.listdir(dir_path):
            filepath = os.path.join(dir_path, filename)
            if not os.path.isfile(filepath) or filename == "competitors.json":
                continue
            
            try:
                ext = os.path.splitext(filename)[1].lower()
                
                if ext == ".docx":
                    content = self._read_docx(filepath)
                elif ext in (".txt", ".md", ".json", ".csv"):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                elif ext == ".pdf":
                    content = f"[PDF файл: {filename} - требуется парсер]"
                else:
                    continue
                
                files_content.append((filename, content))
            except Exception as e:
                files_content.append((filename, f"[Ошибка: {e}]"))
        
        return files_content
    
    def _load_knowledge_base(self) -> str:
        """Загружает все файлы из базы знаний"""
        files = self._load_files_from_dir(config.KNOWLEDGE_BASE_DIR)
        
        if not files:
            return ""
        
        content_parts = []
        for filename, content in files:
            content_parts.append(f"=== {filename} ===\n{content}")
        
        return "\n\n".join(content_parts)
    
    def _load_competitors_content(self, platforms: list[str] = None) -> str:
        """
        Загружает контент конкурентов для указанных платформ
        
        Args:
            platforms: список платформ ["telegram", "instagram", "youtube", "tiktok"]
                      если None - загружаются все
        """
        if not os.path.exists(COMPETITORS_FILE):
            return ""
        
        try:
            with open(COMPETITORS_FILE, 'r', encoding='utf-8') as f:
                competitors = json.load(f)
        except:
            return ""
        
        # Если платформы не указаны, берём все
        if platforms is None:
            platforms = ["telegram", "instagram", "youtube", "tiktok"]
        
        content_parts = []
        platform_names = {
            "telegram": "Telegram",
            "instagram": "Instagram",
            "youtube": "YouTube",
            "tiktok": "TikTok"
        }
        
        for platform in platforms:
            links = competitors.get(platform, [])
            if links:
                content_parts.append(
                    f"=== Конкуренты {platform_names.get(platform, platform)} ===\n" +
                    "\n".join(f"{i+1}. {link}" for i, link in enumerate(links))
                )
        
        return "\n\n".join(content_parts) if content_parts else ""
    
    async def generate_avatar_script(self, topic: str, duration_seconds: int = 30) -> str:
        """
        Генерирует сценарий для видео с аватаром
        ИСПРАВЛЕНИЕ: Строго 30 секунд, ~60 слов максимум для комфортного чтения
        """
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = self._load_knowledge_base()
        
        # 30 секунд = ~60 слов МАКСИМУМ (2 слова в секунду - комфортная скорость чтения)
        target_words = 60
        
        if kb_content.strip():
            system = f"""Ты — профессиональный копирайтер для видеосценариев.

ТВОЯ ЗАДАЧА: Написать КОРОТКИЙ сценарий для видео на заданную тему.

КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (информация о продукте/компании/бренде):
{kb_content}

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Пиши сценарий на ЛЮБУЮ тему, которую запросит пользователь
2. Если тема связана с продуктом/услугой из базы знаний — активно используй эту информацию
3. Если тема НЕ связана напрямую с базой знаний — всё равно пиши качественный сценарий
4. Пиши ТОЛЬКО на РУССКОМ языке
5. Пиши естественным разговорным языком для озвучки
6. СТРОГО {duration_seconds} секунд = МАКСИМУМ {target_words} слов
7. БЕЗ лишних слов - каждое слово должно нести смысл

СТРУКТУРА СЦЕНАРИЯ:
- Хук (первые 3 секунды) — одно мощное предложение (5-7 слов)
- Основная часть — 1-2 коротких предложения (30-40 слов)
- Завершение — краткий вывод или CTA (10-13 слов)

ПРИМЕР хорошего сценария на 30 сек (58 слов):
"Устали терять клиентов? Вот решение. Используйте триггеры в первых трёх секундах. Говорите на языке аудитории, а не о себе. Добавляйте эмоции в каждый кадр. Это работает для тысяч брендов. Попробуйте прямо сейчас — и через неделю увидите рост вовлечённости."

АБСОЛЮТНО КРИТИЧНО: НЕ превышай {target_words} слов! Считай каждое слово!
ЯЗЫК: ТОЛЬКО русский!"""
        else:
            system = f"""Ты — профессиональный копирайтер для видеосценариев.

ТВОЯ ЗАДАЧА: Написать КОРОТКИЙ сценарий для видео на заданную тему.

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Пиши качественный, вовлекающий сценарий
2. Пиши ТОЛЬКО на РУССКОМ языке
3. Пиши естественным разговорным языком для озвучки
4. СТРОГО {duration_seconds} секунд = МАКСИМУМ {target_words} слов
5. БЕЗ лишних слов - каждое слово должно нести смысл

СТРУКТУРА СЦЕНАРИЯ:
- Хук (первые 3 секунды) — одно мощное предложение (5-7 слов)
- Основная часть — 1-2 коротких предложения (30-40 слов)
- Завершение — краткий вывод или CTA (10-13 слов)

ПРИМЕЧАНИЕ: База знаний пуста. Напиши общий информативный сценарий по теме.
АБСОЛЮТНО КРИТИЧНО: НЕ превышай {target_words} слов! Считай каждое слово!
ЯЗЫК: ТОЛЬКО русский!"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Напиши сценарий на тему: {topic}\n\nПомни: максимум {target_words} слов, ТОЛЬКО на русском языке!"}
            ],
            max_tokens=400
        )
        return response.choices[0].message.content 
    
    async def generate_seo_keywords(self, topic: str) -> dict:
        """Генерирует SEO-ключи и заголовок по теме (РУССКИЙ ЯЗЫК)"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = self._load_knowledge_base()
        
        system = f"""Ты — эксперт по SEO с опытом 10+ лет.

КОНТЕКСТ (база знаний о продукте/компании):
{kb_content[:3000] if kb_content else 'База знаний пуста.'}

Твоя задача — подобрать SEO-ключевые слова по заданной теме.
Учитывай контекст из базы знаний при подборе ключей.

КРИТИЧНО: Отвечай ТОЛЬКО на РУССКОМ языке!

📦 Output в формате JSON:
```json
{{
  "topic": "Название темы (на русском)",
  "keywords": "ключ1, ключ2, ключ3, ключ4, ключ5",
  "seo_title": "Качественный SEO-заголовок (на русском)"
}}
```

Отвечай ТОЛЬКО валидным JSON без дополнительного текста."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Тема: {topic}\n\nОтветь на РУССКОМ языке!"}
            ],
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[^{}]*\}', result_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Не удалось распарсить JSON: {result_text}")
    
    async def generate_seo_outline(self, topic: str, keywords: list[str], seo_title: str = None) -> str:
        """Генерирует структуру SEO-статьи (РУССКИЙ ЯЗЫК)"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = self._load_knowledge_base()
        
        system = f"""Ты — SEO-специалист и копирайтер.

КОНТЕКСТ (база знаний о продукте/компании):
{kb_content[:4000] if kb_content else 'База знаний пуста.'}

ЗАДАЧА: Создай структуру SEO-статьи с H2/H3 заголовками.
- Если тема связана с базой знаний — используй эту информацию
- Если тема общая — создай качественную структуру, но можешь добавить раздел о продукте/услуге из базы знаний (если уместно)

КРИТИЧНО: Пиши ТОЛЬКО на РУССКОМ языке!"""

        kw_str = ", ".join(keywords) if keywords else "не указаны"
        title_str = f"\nSEO-заголовок: {seo_title}" if seo_title else ""
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Тема: {topic}\nКлючи: {kw_str}{title_str}\n\nСоздай структуру статьи на РУССКОМ языке."}
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content
    
    async def generate_seo_article(self, topic: str, keywords: list[str], outline: str, seo_title: str = None) -> str:
        """Генерирует полную SEO-статью (РУССКИЙ ЯЗЫК)"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = self._load_knowledge_base()
        
        system = f"""Ты — профессиональный SEO-копирайтер.

КОНТЕКСТ (база знаний о продукте/компании):
{kb_content[:5000] if kb_content else 'База знаний пуста.'}

ПРАВИЛА:
1. Пиши информативную, структурированную статью с учётом SEO
2. Если тема напрямую связана с базой знаний — используй факты и данные из неё
3. Если тема общая — пиши качественную статью, но можешь органично упомянуть продукт/услугу из базы знаний
4. НЕ ВЫДУМЫВАЙ конкретные факты, цифры, исследования — если их нет в базе знаний
5. Пиши ТОЛЬКО на РУССКОМ языке"""

        kw_str = ", ".join(keywords) if keywords else "не указаны"
        title_instruction = f"\nИспользуй заголовок H1: {seo_title}" if seo_title else ""
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Тема: {topic}\nКлючи: {kw_str}{title_instruction}\nСтруктура:\n{outline}\n\nНапиши полную статью на РУССКОМ языке."}
            ],
            max_tokens=4000
        )
        return response.choices[0].message.content
    
    async def enhance_video_prompt(self, user_prompt: str, platforms: list[str] = None) -> str:
        """
        Улучшает промпт для генерации видео на основе базы знаний и конкурентов
        ИСПРАВЛЕНИЕ: Промпт остаётся на АНГЛИЙСКОМ (для AI-генерации видео)
        
        Args:
            user_prompt: Краткая идея от пользователя (на русском)
            platforms: Платформы для анализа конкурентов (по умолчанию все)
        """
        if not self.client:
            return user_prompt
        
        kb_content = self._load_knowledge_base()
        comp_content = self._load_competitors_content(platforms)
        
        # Анализируем контент конкурентов если есть
        competitors_insights = ""
        if comp_content:
            try:
                analysis = await self.analyze_competitors_content(platforms=platforms)
                insights_parts = []
                
                if analysis.get("content_formats"):
                    insights_parts.append(f"Популярные форматы: {', '.join(analysis['content_formats'][:3])}")
                if analysis.get("successful_hooks"):
                    insights_parts.append(f"Эффективные хуки: {', '.join(analysis['successful_hooks'][:2])}")
                if analysis.get("trending_topics"):
                    insights_parts.append(f"Трендовые темы: {', '.join(analysis['trending_topics'][:3])}")
                
                if insights_parts:
                    competitors_insights = "\n\nИНСАЙТЫ ИЗ АНАЛИЗА КОНКУРЕНТОВ:\n" + "\n".join(f"- {i}" for i in insights_parts)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to analyze competitors: {e}")
        
        system = f"""Ты — эксперт по созданию вирусного видеоконтента для TikTok, Instagram Reels, YouTube Shorts.

ТВОЯ ЗАДАЧА: Преобразовать краткую идею пользователя в детальный промпт для AI-генерации видео.

КОНТЕКСТ О ПРОДУКТЕ/БРЕНДЕ (база знаний):
{kb_content[:2000] if kb_content else 'Не предоставлен.'}

ССЫЛКИ НА КОНКУРЕНТОВ:
{comp_content[:2000] if comp_content else 'Не предоставлены.'}{competitors_insights}

ПРАВИЛА СОЗДАНИЯ ПРОМПТА:
1. Если идея связана с продуктом из базы знаний - ОБЯЗАТЕЛЬНО интегрируй его в видео
2. Используй инсайты конкурентов для создания трендового контента
3. Добавь конкретные детали:
   - Визуальный стиль и атмосферу
   - Движение камеры (pan, zoom, tracking shot, etc.)
   - Освещение (golden hour, dramatic, soft natural light, etc.)
   - Динамику действия
   - Настроение и эмоции
4. Промпт должен быть на АНГЛИЙСКОМ языке (для AI-генерации видео)
5. Длина: 50-150 слов
6. Стиль: детальный, кинематографичный

КРИТИЧЕСКИ ВАЖНО - ЗАПРЕТ НА ТЕКСТ:
- В видео НЕ ДОЛЖНО быть НИКАКОГО текста, надписей, титров, субтитров
- НЕ упоминай в промпте: text, words, letters, captions, subtitles, signs, labels, writing
- Используй ТОЛЬКО визуальные элементы: действия, объекты, движения, эффекты
- Если идея подразумевает текст - замени на визуальную метафору

ВАЖНО: Если в идее НЕ упомянут продукт, но он есть в базе знаний - найди способ органично включить его в сцену.

КРИТИЧНО: Отвечай ТОЛЬКО улучшенным промптом на АНГЛИЙСКОМ языке, без пояснений."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Краткая идея (может быть на русском): {user_prompt}\n\nСоздай детальный промпт на АНГЛИЙСКОМ языке для AI-генерации видео."}
            ],
            max_tokens=600
        )
        return response.choices[0].message.content
    
    async def analyze_competitors_content(self, niche: str = "", platforms: list[str] = None) -> dict:
        """
        Анализирует контент конкурентов для указанных платформ (РУССКИЙ ЯЗЫК)
        
        Args:
            niche: ниша/тематика
            platforms: список платформ для анализа
        """
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        comp_content = self._load_competitors_content(platforms)
        
        if not comp_content.strip():
            return {
                "patterns": [],
                "successful_hooks": [],
                "trending_topics": [],
                "content_formats": [],
                "engagement_insights": "Контент конкурентов не добавлен",
                "recommendations": []
            }
        
        system = """Ты — эксперт по вирусному контенту и SMM-аналитик.
Проанализируй предоставленные ссылки на контент конкурентов и выяви:

1. Общие паттерны успешного контента (на основе URL и названий каналов)
2. Типы контента которые публикуются
3. Популярные темы (можно предположить по именам каналов/профилей)
4. Рекомендации для создания контента

КРИТИЧНО: Весь анализ должен быть на РУССКОМ языке!

Ответь в формате JSON:
{
    "patterns": ["паттерн1", "паттерн2"],
    "successful_hooks": ["хук1", "хук2"],
    "trending_topics": ["тема1", "тема2"],
    "content_formats": ["формат1", "формат2"],
    "engagement_insights": "краткий вывод",
    "recommendations": ["рекомендация1", "рекомендация2"]
}"""

        niche_context = f"\nНиша/тематика: {niche}" if niche else ""
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Ссылки на конкурентов:{niche_context}\n\n{comp_content[:8000]}\n\nОтветь на РУССКОМ языке!"}
            ],
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)

openai_service = OpenAIService()