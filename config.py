import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ALLOWED_USER_IDS: list[int] = None  # Будет инициализирован в __post_init__
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    # Kie.ai (Sora2, Veo3, Kling, Nano Banana)
    KIEAI_API_KEY: str = os.getenv("KIEAI_API_KEY", "")
    KIEAI_BASE_URL: str = "https://api.kie.ai"
    
    # Google OAuth (вместо Service Account)
    GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    GOOGLE_TOKEN_FILE: str = os.getenv("GOOGLE_TOKEN_FILE", "token.pickle")
    GOOGLE_SPREADSHEET_ID: str = os.getenv("GOOGLE_SPREADSHEET_ID", "")
    GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    
    # Пути
    KNOWLEDGE_BASE_DIR: str = os.getenv("KNOWLEDGE_BASE_DIR", "knowledge_base")
    COMPETITORS_DIR: str = os.getenv("COMPETITORS_DIR", "knowledge_base/competitors")
    
    def __post_init__(self):
        """Парсинг списка разрешённых пользователей"""
        allowed_ids_str = os.getenv("ALLOWED_USER_IDS", "")
        if allowed_ids_str:
            try:
                self.ALLOWED_USER_IDS = [
                    int(uid.strip()) 
                    for uid in allowed_ids_str.split(",") 
                    if uid.strip().isdigit()
                ]
            except ValueError:
                self.ALLOWED_USER_IDS = []
        else:
            self.ALLOWED_USER_IDS = []
    
    def is_user_allowed(self, user_id: int) -> bool:
        """Проверяет, разрешён ли доступ пользователю"""
        if not self.ALLOWED_USER_IDS:
            return True  # Если список пуст, доступ для всех
        return user_id in self.ALLOWED_USER_IDS
    
    def validate(self) -> dict[str, bool]:
        """Проверка наличия API ключей"""
        return {
            "telegram": bool(self.BOT_TOKEN),
            "openai": bool(self.OPENAI_API_KEY),
            "kieai": bool(self.KIEAI_API_KEY),
            "google": bool(self.GOOGLE_CREDENTIALS_FILE and os.path.exists(self.GOOGLE_CREDENTIALS_FILE)),
        }
    
    def get_missing_keys(self) -> list[str]:
        """Возвращает список отсутствующих ключей"""
        validation = self.validate()
        return [k for k, v in validation.items() if not v]

config = Config()
# Вызываем __post_init__ для инициализации ALLOWED_USER_IDS
config.__post_init__()