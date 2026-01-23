import os
import json
from openai import AsyncOpenAI
from config import config

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
            if not os.path.isfile(filepath):
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
    
    def _load_competitors_content(self) -> str:
        """Загружает контент конкурентов"""
        files = self._load_files_from_dir(config.COMPETITORS_DIR)
        
        if not files:
            return ""
        
        content_parts = []
        for filename, content in files:
            content_parts.append(f"=== Конкурент: {filename} ===\n{content}")
        
        return "\n\n".join(content_parts)
    
    async def generate_avatar_script(self, topic: str, duration_seconds: int = 60) -> str:
        """Генерирует сценарий для видео с аватаром"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = self._load_knowledge_base()
        
        # Формируем системный промпт в зависимости от наличия базы знаний
        if kb_content.strip():
            system = f"""Ты — профессиональный копирайтер для видеосценариев.

ТВОЯ ЗАДАЧА: Написать сценарий для короткого видео на заданную тему.

КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (информация о продукте/компании/бренде):
{kb_content}

ПРАВИЛА:
1. Пиши сценарий на ЛЮБУЮ тему, которую запросит пользователь
2. Если тема связана с продуктом/услугой из базы знаний — активно используй эту информацию
3. Если тема НЕ связана напрямую с базой знаний — всё равно пиши качественный сценарий, но можешь:
   - Упомянуть продукт/бренд в контексте темы (если уместно)
   - Использовать tone of voice из базы знаний
   - Добавить CTA (призыв к действию) связанный с продуктом в конце
4. Пиши естественным разговорным языком для озвучки
5. Сценарий должен быть на ~{duration_seconds} секунд (примерно 150-200 слов)

СТРУКТУРА СЦЕНАРИЯ:
- Хук (первые 3-5 секунд) — зацепи внимание
- Основная часть — раскрой тему
- Завершение — вывод или призыв к действию"""
        else:
            system = f"""Ты — профессиональный копирайтер для видеосценариев.

ТВОЯ ЗАДАЧА: Написать сценарий для короткого видео на заданную тему.

ПРАВИЛА:
1. Пиши качественный, вовлекающий сценарий
2. Пиши естественным разговорным языком для озвучки
3. Сценарий должен быть на ~{duration_seconds} секунд (примерно 150-200 слов)

СТРУКТУРА СЦЕНАРИЯ:
- Хук (первые 3-5 секунд) — зацепи внимание
- Основная часть — раскрой тему
- Завершение — вывод или призыв к действию

ПРИМЕЧАНИЕ: База знаний пуста. Напиши общий информативный сценарий по теме."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Напиши сценарий на тему: {topic}"}
            ],
            max_tokens=2000
        )
        return response.choices[0].message.content
    
    async def generate_seo_keywords(self, topic: str) -> dict:
        """Генерирует SEO-ключи и заголовок по теме"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = self._load_knowledge_base()
        
        system = f"""Ты — эксперт по SEO с опытом 10+ лет.

КОНТЕКСТ (база знаний о продукте/компании):
{kb_content[:3000] if kb_content else 'База знаний пуста.'}

Твоя задача — подобрать SEO-ключевые слова по заданной теме.
Учитывай контекст из базы знаний при подборе ключей.

📦 Output в формате JSON:
```json
{{
  "topic": "Название темы",
  "keywords": "ключ1, ключ2, ключ3, ключ4, ключ5",
  "seo_title": "Качественный SEO-заголовок"
}}
```

Отвечай ТОЛЬКО валидным JSON без дополнительного текста."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Тема: {topic}"}
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
        """Генерирует структуру SEO-статьи"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = self._load_knowledge_base()
        
        system = f"""Ты — SEO-специалист и копирайтер.

КОНТЕКСТ (база знаний о продукте/компании):
{kb_content[:4000] if kb_content else 'База знаний пуста.'}

ЗАДАЧА: Создай структуру SEO-статьи с H2/H3 заголовками.
- Если тема связана с базой знаний — используй эту информацию
- Если тема общая — создай качественную структуру, но можешь добавить раздел о продукте/услуге из базы знаний (если уместно)"""

        kw_str = ", ".join(keywords) if keywords else "не указаны"
        title_str = f"\nSEO-заголовок: {seo_title}" if seo_title else ""
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Тема: {topic}\nКлючи: {kw_str}{title_str}\n\nСоздай структуру статьи."}
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content
    
    async def generate_seo_article(self, topic: str, keywords: list[str], outline: str, seo_title: str = None) -> str:
        """Генерирует полную SEO-статью"""
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
5. Пиши на русском языке"""

        kw_str = ", ".join(keywords) if keywords else "не указаны"
        title_instruction = f"\nИспользуй заголовок H1: {seo_title}" if seo_title else ""
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Тема: {topic}\nКлючи: {kw_str}{title_instruction}\nСтруктура:\n{outline}\n\nНапиши полную статью."}
            ],
            max_tokens=4000
        )
        return response.choices[0].message.content
    
    async def enhance_video_prompt(self, user_prompt: str) -> str:
        """Улучшает промпт для генерации видео"""
        if not self.client:
            return user_prompt
        
        kb_content = self._load_knowledge_base()
        system = f"""Улучши промпт для AI-генерации видео.
Сделай его детальным, добавь описание движения, освещения, стиля.
Используй информацию из базы знаний если релевантно.
Отвечай ТОЛЬКО улучшенным промптом на английском.

КОНТЕКСТ (база знаний):
{kb_content[:2000] if kb_content else 'Нет данных.'}"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=500
        )
        return response.choices[0].message.content
    
    async def analyze_competitors_content(self, niche: str = "") -> dict:
        """Анализирует контент конкурентов из загруженных файлов"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        comp_content = self._load_competitors_content()
        
        if not comp_content.strip():
            return {
                "patterns": [],
                "successful_hooks": [],
                "trending_topics": [],
                "content_formats": [],
                "engagement_insights": "Контент конкурентов не загружен",
                "recommendations": []
            }
        
        system = """Ты — эксперт по вирусному контенту и SMM-аналитик.
Проанализируй предоставленные данные о контенте конкурентов и выяви:

1. Общие паттерны успешного контента
2. Типы хуков и заголовков, которые работают
3. Популярные темы
4. Форматы контента
5. Рекомендации для создания контента

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
                {"role": "user", "content": f"Контент конкурентов:{niche_context}\n\n{comp_content[:8000]}"}
            ],
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)

openai_service = OpenAIService()