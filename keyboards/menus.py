from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_kb() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎭 Видео с аватаром", callback_data="menu:avatar"),
        InlineKeyboardButton(text="🎬 Короткое видео", callback_data="menu:short_video")
    )
    builder.row(
        InlineKeyboardButton(text="🖼 Карусель", callback_data="menu:carousel"),
        InlineKeyboardButton(text="📝 SEO-статья", callback_data="menu:seo")
    )
    builder.row(
        InlineKeyboardButton(text="📅 Контент-план", callback_data="menu:content_plan")
    )
    builder.row(
        InlineKeyboardButton(text="📚 База знаний", callback_data="menu:knowledge")
    )
    return builder.as_markup()

def knowledge_base_kb(has_files: bool = False) -> InlineKeyboardMarkup:
    """Меню базы знаний с разделом конкурентов"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📤 Загрузить файл", callback_data="kb:upload"))
    if has_files:
        builder.row(InlineKeyboardButton(text="🗑 Удалить файл", callback_data="kb:delete"))
    builder.row(InlineKeyboardButton(text="🎯 База конкурентов", callback_data="kb:competitors"))
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
    return builder.as_markup()

def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main")]
    ])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def cancel_and_back_kb(back_callback: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопками Назад и Отмена"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def confirm_edit_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
        InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit")
    )
    builder.row(InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="regenerate"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def video_model_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎥 Sora 2", callback_data="model:sora2"))
    builder.row(
        InlineKeyboardButton(text="⚡ Veo 3.1 Fast", callback_data="model:veo3_fast"),
        InlineKeyboardButton(text="💎 Veo 3.1 Quality", callback_data="model:veo3")
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def video_mode_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📝 Текст → Видео", callback_data="mode:t2v"),
        InlineKeyboardButton(text="🖼 Изображение → Видео", callback_data="mode:i2v")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back:model"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def aspect_ratio_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📺 16:9 (горизонтальное)", callback_data="aspect:16:9"),
        InlineKeyboardButton(text="📱 9:16 (вертикальное)", callback_data="aspect:9:16")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back:mode"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()