from aiogram.fsm.state import State, StatesGroup

class AvatarVideoStates(StatesGroup):
    """Состояния для видео с аватаром Kling"""
    waiting_topic = State()
    waiting_script_confirm = State()
    waiting_script_edit = State()
    waiting_video = State()  # Ожидание аудио
    selecting_avatar_source = State()
    selecting_avatar_style = State()
    waiting_avatar_description = State()
    waiting_avatar_image = State()
    confirming_avatar = State()
    selecting_subtitles = State()  # НОВОЕ: выбор стиля субтитров
    generating = State()

class SEOArticleStates(StatesGroup):
    """Состояния для SEO-статей (упрощённые)"""
    waiting_topic = State()

class ShortVideoStates(StatesGroup):
    """Состояния для Sora2/Veo3"""
    selecting_model = State()
    selecting_mode = State()
    waiting_prompt = State()
    waiting_image = State()
    selecting_aspect = State()
    generating = State()

class KnowledgeBaseStates(StatesGroup):
    """Состояния для базы знаний"""
    waiting_file = State()
    confirming_delete = State()

class ContentPlanStates(StatesGroup):
    """Состояния для контент-плана"""
    entering_niche = State()
    selecting_period = State()
    selecting_platforms = State()
    selecting_frequency = State()
    generating = State()
    viewing_plan = State()
    selecting_idea = State()

class CarouselStates(StatesGroup):
    """Состояния для каруселей"""
    entering_topic = State()
    selecting_slides_count = State()
    selecting_style = State()
    selecting_color = State()
    reviewing_content = State()
    editing_slide = State()
    generating = State()
    viewing_result = State()