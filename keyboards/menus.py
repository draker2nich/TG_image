from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎭 Видео с аватаром", callback_data="menu:avatar"),
        InlineKeyboardButton(text="📝 SEO-статья", callback_data="menu:seo")
    )
    builder.row(
        InlineKeyboardButton(text="🎬 Короткое видео", callback_data="menu:short_video"),
        InlineKeyboardButton(text="🖼 Карусель", callback_data="menu:carousel")
    )
    builder.row(
        InlineKeyboardButton(text="🔥 Вирусный контент", callback_data="menu:viral"),
        InlineKeyboardButton(text="📅 Контент-план", callback_data="menu:content_plan")
    )
    builder.row(
        InlineKeyboardButton(text="📚 База знаний", callback_data="menu:knowledge")
    )
    return builder.as_markup()

def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def confirm_edit_kb() -> InlineKeyboardMarkup:
    """Подтвердить или редактировать"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
        InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit")
    )
    builder.row(InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="regenerate"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def video_model_kb() -> InlineKeyboardMarkup:
    """Выбор модели для короткого видео"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎥 Sora 2", callback_data="model:sora2")
    )
    builder.row(
        InlineKeyboardButton(text="⚡ Veo 3.1 Fast", callback_data="model:veo3_fast"),
        InlineKeyboardButton(text="💎 Veo 3.1 Quality", callback_data="model:veo3")
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def video_mode_kb() -> InlineKeyboardMarkup:
    """Выбор режима генерации видео"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📝 Текст → Видео", callback_data="mode:t2v"),
        InlineKeyboardButton(text="🖼 Изображение → Видео", callback_data="mode:i2v")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back:model"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def aspect_ratio_kb() -> InlineKeyboardMarkup:
    """Выбор соотношения сторон"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📺 16:9 (горизонтальное)", callback_data="aspect:16:9"),
        InlineKeyboardButton(text="📱 9:16 (вертикальное)", callback_data="aspect:9:16")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back:mode"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def knowledge_base_kb(files: list[str]) -> InlineKeyboardMarkup:
    """Меню управления базой знаний"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📤 Загрузить файл", callback_data="kb:upload"))
    if files:
        builder.row(InlineKeyboardButton(text="📋 Список файлов", callback_data="kb:list"))
        builder.row(InlineKeyboardButton(text="🗑 Удалить файл", callback_data="kb:delete"))
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
    return builder.as_markup()

def back_to_menu_kb() -> InlineKeyboardMarkup:
    """Возврат в главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main")]
    ])