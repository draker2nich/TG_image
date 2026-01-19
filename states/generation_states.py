from aiogram.fsm.state import State, StatesGroup

class AvatarVideoStates(StatesGroup):
    """Состояния для генерации видео с аватаром HeyGen"""
    waiting_topic = State()
    waiting_script_confirm = State()
    waiting_script_edit = State()
    selecting_avatar = State()
    selecting_voice = State()
    confirming_generation = State()
    generating = State()

class SEOArticleStates(StatesGroup):
    """Состояния для генерации SEO-статей"""
    waiting_topic = State()
    waiting_keywords = State()
    waiting_outline_confirm = State()
    waiting_article_confirm = State()
    waiting_edit = State()

class ShortVideoStates(StatesGroup):
    """Состояния для генерации коротких видео Sora2/Veo3"""
    selecting_model = State()
    selecting_mode = State()
    waiting_prompt = State()
    waiting_image = State()
    selecting_aspect = State()
    confirming_generation = State()
    generating = State()

class KnowledgeBaseStates(StatesGroup):
    """Состояния для управления базой знаний"""
    waiting_file = State()
    confirming_delete = State()

class ViralParserStates(StatesGroup):
    """Состояния для парсинга вирусного контента"""
    selecting_platform = State()
    entering_handle = State()
    selecting_sort = State()
    viewing_results = State()
    viewing_transcript = State()

class ContentPlanStates(StatesGroup):
    """Состояния для генерации контент-плана"""
    entering_niche = State()
    selecting_period = State()
    selecting_platforms = State()
    selecting_frequency = State()
    generating = State()
    viewing_plan = State()
    selecting_idea = State()