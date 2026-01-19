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
    
    # HeyGen
    HEYGEN_API_KEY: str = os.getenv("HEYGEN_API_KEY", "")
    HEYGEN_BASE_URL: str = "https://api.heygen.com"
    
    # Kie.ai (Sora2, Veo3)
    KIEAI_API_KEY: str = os.getenv("KIEAI_API_KEY", "")
    KIEAI_BASE_URL: str = "https://api.kie.ai"
    
    # ScrapeCreators (TikTok, Instagram, YouTube parsing)
    SCRAPECREATORS_API_KEY: str = os.getenv("SCRAPECREATORS_API_KEY", "")
    
    # Callback URL для вебхуков (опционально)
    CALLBACK_BASE_URL: Optional[str] = os.getenv("CALLBACK_BASE_URL")
    
    # Пути
    KNOWLEDGE_BASE_DIR: str = os.getenv("KNOWLEDGE_BASE_DIR", "knowledge_base")
    
    def validate(self) -> dict[str, bool]:
        """Проверка наличия API ключей"""
        return {
            "telegram": bool(self.BOT_TOKEN),
            "openai": bool(self.OPENAI_API_KEY),
            "heygen": bool(self.HEYGEN_API_KEY),
            "kieai": bool(self.KIEAI_API_KEY),
            "scrapecreators": bool(self.SCRAPECREATORS_API_KEY),
        }
    
    def get_missing_keys(self) -> list[str]:
        """Возвращает список отсутствующих ключей"""
        validation = self.validate()
        return [k for k, v in validation.items() if not v]

config = Config()