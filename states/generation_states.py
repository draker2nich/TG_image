from aiogram.fsm.state import State, StatesGroup

class AvatarVideoStates(StatesGroup):
    """Состояния для генерации видео с аватаром Kling"""
    waiting_topic = State()
    waiting_script_confirm = State()
    waiting_script_edit = State()
    waiting_video = State()  # Ожидание загрузки видео пользователя
    selecting_avatar_source = State()  # Выбор: загрузить фото или сгенерировать
    selecting_avatar_style = State()  # Выбор стиля генерируемого аватара
    waiting_avatar_description = State()  # Описание для генерации аватара
    waiting_avatar_image = State()  # Ожидание загрузки фото аватара
    confirming_avatar = State()  # Подтверждение аватара
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

class ContentPlanStates(StatesGroup):
    """Состояния для генерации контент-плана"""
    entering_niche = State()
    selecting_period = State()
    selecting_platforms = State()
    selecting_frequency = State()
    generating = State()
    viewing_plan = State()
    selecting_idea = State()

class CarouselStates(StatesGroup):
    """Состояния для генерации каруселей"""
    entering_topic = State()
    selecting_slides_count = State()
    selecting_style = State()
    selecting_color = State()
    reviewing_content = State()
    editing_slide = State()
    generating = State()
    viewing_result = State()