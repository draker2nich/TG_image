import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    
    # Kie.ai (Sora2, Veo3, Kling, Nano Banana Pro)
    KIEAI_API_KEY: str = os.getenv("KIEAI_API_KEY", "")
    KIEAI_BASE_URL: str = "https://api.kie.ai"
    
    # Google API (OAuth)
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_SPREADSHEET_ID: str = os.getenv("GOOGLE_SPREADSHEET_ID", "")
    GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    
    # Callback URL для вебхуков (опционально)
    CALLBACK_BASE_URL: Optional[str] = os.getenv("CALLBACK_BASE_URL")
    
    # Пути
    KNOWLEDGE_BASE_DIR: str = os.getenv("KNOWLEDGE_BASE_DIR", "knowledge_base")
    COMPETITORS_DIR: str = os.getenv("COMPETITORS_DIR", "knowledge_base/competitors")
    
    def validate(self) -> dict[str, bool]:
        """Проверка наличия API ключей"""
        return {
            "telegram": bool(self.BOT_TOKEN),
            "openai": bool(self.OPENAI_API_KEY),
            "kieai": bool(self.KIEAI_API_KEY),
            "google": bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET),
        }
    
    def get_missing_keys(self) -> list[str]:
        """Возвращает список отсутствующих ключей"""
        validation = self.validate()
        return [k for k, v in validation.items() if not v]

config = Config()