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
        
        if not kb_content.strip():
            raise RuntimeError(
                "База знаний пуста! Загрузите файлы с информацией через меню '📚 База знаний'."
            )
        
        system = f"""Ты — копирайтер для видеосценариев. 
Используй ТОЛЬКО информацию из предоставленной базы знаний.
НЕ ИСПОЛЬЗУЙ информацию из интернета или своих общих знаний.
НЕ ВЫДУМЫВАЙ факты, которых нет в базе знаний.
Пиши естественным разговорным языком для озвучки.

ВАЖНО: Если информации по теме нет в базе знаний, честно скажи об этом.

БАЗА ЗНАНИЙ:
{kb_content}"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "developer", "content": system},
                {"role": "user", "content": f"Напиши сценарий на ~{duration_seconds} секунд по теме: {topic}"}
            ],
            max_tokens=2000
        )
        return response.choices[0].message.content
    
    async def generate_seo_keywords(self, topic: str) -> dict:
        """Генерирует SEO-ключи и заголовок по теме"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        system = """=Act (Действуй):
Действуй как **эксперт по SEO с опытом 10+ лет**, который специализируется на глубоком и продуманном подборе SEO-ключей.

Context (Контекст):
Твоя задача — подобрать SEO-ключевые слова по заданной теме.
Отбирай **ТОЛЬКО самые высокочастотные ключевые фразы**.

📦 **Output в формате JSON:**
```json
{
  "topic": "Название темы",
  "keywords": "ключ1, ключ2, ключ3, ключ4, ключ5",
  "seo_title": "Качественный SEO-заголовок"
}
```

Отвечай ТОЛЬКО валидным JSON без дополнительного текста."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "developer", "content": system},
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
        
        if not kb_content.strip():
            raise RuntimeError("База знаний пуста! Загрузите файлы.")
        
        system = f"""Ты — SEO-специалист и копирайтер.
Используй ТОЛЬКО информацию из базы знаний.
НЕ ИСПОЛЬЗУЙ информацию из интернета.
Создай структуру статьи с H2/H3 заголовками.

БАЗА ЗНАНИЙ:
{kb_content}"""

        kw_str = ", ".join(keywords) if keywords else "не указаны"
        title_str = f"\nSEO-заголовок: {seo_title}" if seo_title else ""
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "developer", "content": system},
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
        
        if not kb_content.strip():
            raise RuntimeError("База знаний пуста! Загрузите файлы.")
        
        system = f"""Ты — профессиональный SEO-копирайтер.
Используй ТОЛЬКО информацию из базы знаний.
НЕ ИСПОЛЬЗУЙ информацию из интернета или свои общие знания.
НЕ ВЫДУМЫВАЙ факты, которых нет в базе знаний.
Пиши информативно, структурированно, с учётом SEO.

БАЗА ЗНАНИЙ:
{kb_content}"""

        kw_str = ", ".join(keywords) if keywords else "не указаны"
        title_instruction = f"\nИспользуй заголовок H1: {seo_title}" if seo_title else ""
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "developer", "content": system},
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

БАЗА ЗНАНИЙ:
{kb_content if kb_content else 'Нет данных.'}"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "developer", "content": system},
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
                {"role": "developer", "content": system},
                {"role": "user", "content": f"Контент конкурентов:{niche_context}\n\n{comp_content[:8000]}"}
            ],
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)

openai_service = OpenAIService()