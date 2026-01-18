from aiogram.fsm.state import State, StatesGroup

class AvatarVideoStates(StatesGroup):
    """Состояния для генерации видео с аватаром HeyGen"""
    waiting_topic = State()           # Ожидание темы/описания
    waiting_script_confirm = State()  # Подтверждение/редактирование сценария
    waiting_script_edit = State()     # Ввод отредактированного сценария
    selecting_avatar = State()        # Выбор аватара
    selecting_voice = State()         # Выбор голоса
    confirming_generation = State()   # Финальное подтверждение
    generating = State()              # Процесс генерации

class SEOArticleStates(StatesGroup):
    """Состояния для генерации SEO-статей"""
    waiting_topic = State()           # Ожидание темы статьи
    waiting_keywords = State()        # Ожидание ключевых слов
    waiting_outline_confirm = State() # Подтверждение структуры
    waiting_article_confirm = State() # Подтверждение статьи
    waiting_edit = State()            # Редактирование

class ShortVideoStates(StatesGroup):
    """Состояния для генерации коротких видео Sora2/Veo3"""
    selecting_model = State()         # Выбор модели
    selecting_mode = State()          # Text-to-Video или Image-to-Video
    waiting_prompt = State()          # Ожидание промпта
    waiting_image = State()           # Ожидание изображения (для I2V)
    selecting_aspect = State()        # Выбор соотношения сторон
    confirming_generation = State()   # Подтверждение
    generating = State()              # Процесс генерации

class KnowledgeBaseStates(StatesGroup):
    """Состояния для управления базой знаний"""
    waiting_file = State()            # Ожидание файла
    confirming_delete = State()       # Подтверждение удаления
