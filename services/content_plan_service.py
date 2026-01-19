import json
from typing import Optional
from dataclasses import dataclass, asdict
from services.openai_service import openai_service
from services.viral_parser import ViralVideo

@dataclass
class ContentIdea:
    """Идея для контента"""
    title: str
    hook: str
    format: str  # video, reel, article, carousel
    platform: str  # tiktok, instagram, youtube, blog
    description: str
    key_points: list[str]
    hashtags: list[str]
    estimated_duration: str
    inspiration_source: str = ""

@dataclass
class ContentPlan:
    """Контент-план"""
    topic: str
    period: str  # week, month
    ideas: list[ContentIdea]
    created_at: str = ""

class ContentPlanService:
    def __init__(self):
        pass
    
    async def analyze_viral_content(
        self,
        videos: list[ViralVideo],
        niche: str = ""
    ) -> dict:
        """Анализирует вирусный контент и выявляет паттерны"""
        if not openai_service.is_available():
            raise RuntimeError("OpenAI API недоступен")
        
        # Формируем данные для анализа
        content_data = []
        for v in videos[:20]:  # Максимум 20 видео
            content_data.append({
                "platform": v.platform,
                "title": v.title[:200],
                "description": v.description[:500],
                "views": v.views,
                "likes": v.likes,
                "engagement_rate": round(v.likes / v.views * 100, 2) if v.views > 0 else 0,
                "duration": v.duration,
                "transcript": v.transcript[:1000] if v.transcript else ""
            })
        
        system = """Ты — эксперт по вирусному контенту и SMM-аналитик.
Проанализируй предоставленные данные о популярном контенте и выяви:

1. Общие паттерны успешного контента
2. Типы хуков и заголовков, которые работают
3. Оптимальную длительность
4. Темы и форматы с высоким вовлечением
5. Тренды и повторяющиеся элементы

Ответь в формате JSON:
{
    "patterns": ["паттерн1", "паттерн2"],
    "successful_hooks": ["хук1", "хук2"],
    "optimal_duration": "X-Y секунд",
    "trending_topics": ["тема1", "тема2"],
    "content_formats": ["формат1", "формат2"],
    "engagement_insights": "краткий вывод",
    "recommendations": ["рекомендация1", "рекомендация2"]
}"""

        niche_context = f"\nНиша/тематика: {niche}" if niche else ""
        
        response = await openai_service.client.chat.completions.create(
            model=openai_service.model,
            messages=[
                {"role": "developer", "content": system},
                {"role": "user", "content": f"Данные контента:{niche_context}\n\n{json.dumps(content_data, ensure_ascii=False)}"}
            ],
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
    
    async def generate_content_ideas(
        self,
        analysis: dict,
        niche: str,
        count: int = 10,
        platforms: list[str] = None
    ) -> list[ContentIdea]:
        """Генерирует идеи контента на основе анализа"""
        if not openai_service.is_available():
            raise RuntimeError("OpenAI API недоступен")
        
        platforms = platforms or ["tiktok", "instagram", "youtube"]
        kb_content = openai_service._load_knowledge_base()
        
        system = f"""Ты — креативный SMM-специалист и контент-мейкер.
На основе анализа вирусного контента сгенерируй уникальные идеи.

Используй информацию из базы знаний если она релевантна:
{kb_content[:3000] if kb_content else 'База знаний пуста.'}

Для каждой идеи укажи:
- Цепляющий заголовок
- Хук (первые 3 секунды)
- Формат (video/reel/carousel/article)
- Платформу
- Описание концепции
- Ключевые точки сценария
- Хештеги
- Примерную длительность

Ответь JSON массивом:
[{{
    "title": "Заголовок",
    "hook": "Хук первых секунд",
    "format": "video",
    "platform": "tiktok",
    "description": "Описание",
    "key_points": ["пункт1", "пункт2"],
    "hashtags": ["#хештег1"],
    "estimated_duration": "30-60 сек"
}}]"""

        response = await openai_service.client.chat.completions.create(
            model=openai_service.model,
            messages=[
                {"role": "developer", "content": system},
                {"role": "user", "content": (
                    f"Ниша: {niche}\n"
                    f"Платформы: {', '.join(platforms)}\n"
                    f"Количество идей: {count}\n\n"
                    f"Анализ вирусного контента:\n{json.dumps(analysis, ensure_ascii=False)}"
                )}
            ],
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        ideas_data = result if isinstance(result, list) else result.get("ideas", [])
        
        ideas = []
        for item in ideas_data[:count]:
            ideas.append(ContentIdea(
                title=item.get("title", ""),
                hook=item.get("hook", ""),
                format=item.get("format", "video"),
                platform=item.get("platform", "tiktok"),
                description=item.get("description", ""),
                key_points=item.get("key_points", []),
                hashtags=item.get("hashtags", []),
                estimated_duration=item.get("estimated_duration", "")
            ))
        
        return ideas
    
    async def generate_content_plan(
        self,
        niche: str,
        period: str = "week",  # week или month
        viral_videos: list[ViralVideo] = None,
        platforms: list[str] = None,
        posts_per_day: int = 1
    ) -> ContentPlan:
        """Генерирует полный контент-план"""
        if not openai_service.is_available():
            raise RuntimeError("OpenAI API недоступен")
        
        platforms = platforms or ["tiktok", "instagram"]
        
        # Анализируем вирусный контент если есть
        analysis = {}
        if viral_videos:
            analysis = await self.analyze_viral_content(viral_videos, niche)
        
        # Рассчитываем количество идей
        days = 7 if period == "week" else 30
        total_posts = days * posts_per_day * len(platforms)
        
        kb_content = openai_service._load_knowledge_base()
        
        system = f"""Ты — стратег контент-маркетинга.
Создай детальный контент-план с учётом:
- Разнообразия форматов
- Оптимального времени публикации
- Трендов и сезонности
- Вовлечения аудитории

База знаний:
{kb_content[:2000] if kb_content else 'Пуста.'}

Анализ вирусного контента:
{json.dumps(analysis, ensure_ascii=False) if analysis else 'Не предоставлен.'}

Создай план в формате JSON:
{{
    "ideas": [
        {{
            "title": "Заголовок",
            "hook": "Хук",
            "format": "video/reel/carousel",
            "platform": "tiktok/instagram/youtube",
            "description": "Описание",
            "key_points": ["пункт1", "пункт2", "пункт3"],
            "hashtags": ["#tag1", "#tag2"],
            "estimated_duration": "30 сек",
            "suggested_day": "Понедельник" или номер дня,
            "inspiration_source": "Источник вдохновения если есть"
        }}
    ]
}}"""

        response = await openai_service.client.chat.completions.create(
            model=openai_service.model,
            messages=[
                {"role": "developer", "content": system},
                {"role": "user", "content": (
                    f"Ниша: {niche}\n"
                    f"Период: {period} ({days} дней)\n"
                    f"Платформы: {', '.join(platforms)}\n"
                    f"Постов в день на платформу: {posts_per_day}\n"
                    f"Всего нужно идей: {total_posts}"
                )}
            ],
            max_tokens=6000,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        ideas_data = result.get("ideas", []) if isinstance(result, dict) else result
        
        ideas = []
        for item in ideas_data:
            ideas.append(ContentIdea(
                title=item.get("title", ""),
                hook=item.get("hook", ""),
                format=item.get("format", "video"),
                platform=item.get("platform", ""),
                description=item.get("description", ""),
                key_points=item.get("key_points", []),
                hashtags=item.get("hashtags", []),
                estimated_duration=item.get("estimated_duration", ""),
                inspiration_source=item.get("inspiration_source", "")
            ))
        
        from datetime import datetime
        return ContentPlan(
            topic=niche,
            period=period,
            ideas=ideas,
            created_at=datetime.now().isoformat()
        )
    
    async def generate_script_from_idea(self, idea: ContentIdea) -> str:
        """Генерирует сценарий по идее"""
        if not openai_service.is_available():
            raise RuntimeError("OpenAI API недоступен")
        
        kb_content = openai_service._load_knowledge_base()
        
        system = f"""Ты — профессиональный сценарист для коротких видео.
Напиши готовый сценарий для съёмки/озвучки.

База знаний:
{kb_content[:2000] if kb_content else 'Пуста.'}

Формат сценария:
1. ХУКИ (первые 3 сек) - цепляющее начало
2. ОСНОВНАЯ ЧАСТЬ - раскрытие темы
3. ПРИЗЫВ К ДЕЙСТВИЮ - что делать зрителю

Пиши естественным разговорным языком.
Добавь тайм-коды если видео длиннее 30 сек."""

        response = await openai_service.client.chat.completions.create(
            model=openai_service.model,
            messages=[
                {"role": "developer", "content": system},
                {"role": "user", "content": (
                    f"Идея: {idea.title}\n"
                    f"Хук: {idea.hook}\n"
                    f"Формат: {idea.format}\n"
                    f"Платформа: {idea.platform}\n"
                    f"Описание: {idea.description}\n"
                    f"Ключевые точки: {', '.join(idea.key_points)}\n"
                    f"Длительность: {idea.estimated_duration}"
                )}
            ],
            max_tokens=2000
        )
        
        return response.choices[0].message.content

content_plan_service = ContentPlanService()
