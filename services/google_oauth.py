"""
Google OAuth 2.0 авторизация для Telegram бота
"""
import os
import asyncio
import pickle
from typing import Optional
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Scopes для доступа к Google Drive и Sheets
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets'
]

class GoogleOAuth:
    def __init__(self, credentials_file: str, token_file: str = "token.pickle"):
        """
        Args:
            credentials_file: Путь к credentials.json (OAuth 2.0 Client ID)
            token_file: Путь для сохранения токена авторизации
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.creds: Optional[Credentials] = None
    
    def is_configured(self) -> bool:
        """Проверяет наличие credentials.json"""
        return os.path.exists(self.credentials_file)
    
    def is_authorized(self) -> bool:
        """Проверяет наличие валидного токена"""
        if not os.path.exists(self.token_file):
            return False
        
        try:
            with open(self.token_file, 'rb') as token:
                self.creds = pickle.load(token)
            return self.creds and self.creds.valid
        except:
            return False
    
    async def refresh_token(self) -> bool:
        """Обновляет токен если он истёк"""
        if not self.creds:
            return False
        
        if self.creds.valid:
            return True
        
        if self.creds.expired and self.creds.refresh_token:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, self.creds.refresh, Request()
                )
                self._save_token()
                return True
            except Exception as e:
                print(f"Token refresh error: {e}")
                return False
        
        return False
    
    def get_auth_url(self) -> str:
        """
        Генерирует URL для авторизации пользователя
        
        Returns:
            URL для авторизации
        """
        flow = Flow.from_client_secrets_file(
            self.credentials_file,
            scopes=SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'  # Для desktop приложений
        )
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        return auth_url
    
    def exchange_code_for_token(self, auth_code: str) -> bool:
        """
        Обменивает код авторизации на токен
        
        Args:
            auth_code: Код авторизации из OAuth flow
        
        Returns:
            True если успешно
        """
        try:
            flow = Flow.from_client_secrets_file(
                self.credentials_file,
                scopes=SCOPES,
                redirect_uri='urn:ietf:wg:oauth:2.0:oob'
            )
            
            flow.fetch_token(code=auth_code)
            self.creds = flow.credentials
            self._save_token()
            return True
        except Exception as e:
            print(f"Token exchange error: {e}")
            return False
    
    def _save_token(self):
        """Сохраняет токен в файл"""
        with open(self.token_file, 'wb') as token:
            pickle.dump(self.creds, token)
    
    def get_credentials(self) -> Optional[Credentials]:
        """Возвращает credentials для использования в API"""
        return self.creds
    
    def revoke_authorization(self) -> bool:
        """Отзывает авторизацию и удаляет токен"""
        try:
            if self.creds:
                self.creds.revoke(Request())
            
            if os.path.exists(self.token_file):
                os.remove(self.token_file)
            
            self.creds = None
            return True
        except Exception as e:
            print(f"Revoke error: {e}")
            return False

google_oauth = GoogleOAuth(
    credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
    token_file=os.getenv("GOOGLE_TOKEN_FILE", "token.pickle")
)