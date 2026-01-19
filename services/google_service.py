import os
import json
import asyncio
import aiohttp
import aiofiles
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
import io

from config import config

# Scopes для доступа к Drive и Sheets
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets'
]

@dataclass
class UploadResult:
    """Результат загрузки файла"""
    success: bool
    file_id: Optional[str] = None
    file_url: Optional[str] = None
    error: Optional[str] = None

@dataclass
class SheetRow:
    """Строка для Google Sheets"""
    date: str
    content_type: str  # video_avatar, seo_article, short_video, carousel
    title: str
    status: str  # generated, uploaded, error
    file_url: str = ""
    platform: str = ""
    notes: str = ""

class GoogleService:
    def __init__(self):
        self.client_id = config.GOOGLE_CLIENT_ID
        self.client_secret = config.GOOGLE_CLIENT_SECRET
        self.spreadsheet_id = config.GOOGLE_SPREADSHEET_ID
        self.drive_folder_id = config.GOOGLE_DRIVE_FOLDER_ID
        
        self.creds: Optional[Credentials] = None
        self.drive_service = None
        self.sheets_service = None
        
        self._token_path = "google_token.json"
        self._credentials_path = "google_credentials.json"
    
    def is_configured(self) -> bool:
        """Проверяет наличие конфигурации"""
        return bool(self.client_id and self.client_secret)
    
    def is_authorized(self) -> bool:
        """Проверяет наличие валидной авторизации"""
        return self.creds is not None and self.creds.valid
    
    async def setup_credentials_file(self):
        """Создаёт файл credentials.json из переменных окружения"""
        if not self.is_configured():
            return False
        
        credentials_data = {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8080/"]
            }
        }
        
        async with aiofiles.open(self._credentials_path, 'w') as f:
            await f.write(json.dumps(credentials_data, indent=2))
        
        return True
    
    async def load_token(self) -> bool:
        """Загружает сохранённый токен"""
        if not os.path.exists(self._token_path):
            return False
        
        try:
            async with aiofiles.open(self._token_path, 'r') as f:
                token_data = json.loads(await f.read())
            
            self.creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            
            # Обновляем токен если истёк
            if self.creds and self.creds.expired and self.creds.refresh_token:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: self.creds.refresh(Request()))
                await self._save_token()
            
            if self.creds and self.creds.valid:
                await self._init_services()
                return True
            
            return False
        except Exception as e:
            print(f"Error loading token: {e}")
            return False
    
    async def _save_token(self):
        """Сохраняет токен в файл"""
        if self.creds:
            async with aiofiles.open(self._token_path, 'w') as f:
                await f.write(self.creds.to_json())
    
    async def _init_services(self):
        """Инициализирует сервисы Google API"""
        if not self.creds:
            return
        
        loop = asyncio.get_event_loop()
        self.drive_service = await loop.run_in_executor(
            None, lambda: build('drive', 'v3', credentials=self.creds)
        )
        self.sheets_service = await loop.run_in_executor(
            None, lambda: build('sheets', 'v4', credentials=self.creds)
        )
    
    def get_auth_url(self) -> Optional[str]:
        """Получает URL для авторизации"""
        if not os.path.exists(self._credentials_path):
            return None
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self._credentials_path, SCOPES
            )
            flow.redirect_uri = "http://localhost:8080/"
            
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            return auth_url
        except Exception as e:
            print(f"Error getting auth URL: {e}")
            return None
    
    async def authorize_with_code(self, code: str) -> bool:
        """Завершает авторизацию с кодом"""
        if not os.path.exists(self._credentials_path):
            return False
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self._credentials_path, SCOPES
            )
            flow.redirect_uri = "http://localhost:8080/"
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: flow.fetch_token(code=code))
            
            self.creds = flow.credentials
            await self._save_token()
            await self._init_services()
            
            return True
        except Exception as e:
            print(f"Authorization error: {e}")
            return False
    
    async def upload_file_to_drive(
        self,
        file_path: Optional[str] = None,
        file_content: Optional[bytes] = None,
        file_name: str = "file",
        mime_type: str = "application/octet-stream",
        folder_id: Optional[str] = None
    ) -> UploadResult:
        """Загружает файл на Google Drive"""
        if not self.is_authorized() or not self.drive_service:
            return UploadResult(success=False, error="Not authorized")
        
        folder = folder_id or self.drive_folder_id
        
        try:
            file_metadata = {'name': file_name}
            if folder:
                file_metadata['parents'] = [folder]
            
            loop = asyncio.get_event_loop()
            
            if file_path and os.path.exists(file_path):
                media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
            elif file_content:
                media = MediaIoBaseUpload(
                    io.BytesIO(file_content), 
                    mimetype=mime_type, 
                    resumable=True
                )
            else:
                return UploadResult(success=False, error="No file provided")
            
            file = await loop.run_in_executor(
                None,
                lambda: self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, webViewLink'
                ).execute()
            )
            
            return UploadResult(
                success=True,
                file_id=file.get('id'),
                file_url=file.get('webViewLink')
            )
        except Exception as e:
            return UploadResult(success=False, error=str(e))
    
    async def upload_from_url(
        self,
        url: str,
        file_name: str,
        mime_type: str = "video/mp4",
        folder_id: Optional[str] = None
    ) -> UploadResult:
        """Скачивает файл по URL и загружает на Drive"""
        if not self.is_authorized():
            return UploadResult(success=False, error="Not authorized")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status != 200:
                        return UploadResult(success=False, error=f"Download failed: {resp.status}")
                    content = await resp.read()
            
            return await self.upload_file_to_drive(
                file_content=content,
                file_name=file_name,
                mime_type=mime_type,
                folder_id=folder_id
            )
        except Exception as e:
            return UploadResult(success=False, error=str(e))
    
    async def add_row_to_sheet(self, row: SheetRow) -> bool:
        """Добавляет строку в Google Sheets"""
        if not self.is_authorized() or not self.sheets_service:
            return False
        
        if not self.spreadsheet_id:
            return False
        
        try:
            values = [[
                row.date,
                row.content_type,
                row.title,
                row.status,
                row.file_url,
                row.platform,
                row.notes
            ]]
            
            body = {'values': values}
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range='A:G',
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body=body
                ).execute()
            )
            
            return True
        except Exception as e:
            print(f"Error adding row to sheet: {e}")
            return False
    
    async def init_sheet_headers(self) -> bool:
        """Инициализирует заголовки в таблице"""
        if not self.is_authorized() or not self.sheets_service:
            return False
        
        if not self.spreadsheet_id:
            return False
        
        try:
            # Проверяем есть ли уже данные
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range='A1:G1'
                ).execute()
            )
            
            if result.get('values'):
                return True  # Заголовки уже есть
            
            # Добавляем заголовки
            headers = [[
                'Дата', 'Тип контента', 'Название/Тема', 
                'Статус', 'Ссылка на файл', 'Платформа', 'Примечания'
            ]]
            
            await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range='A1:G1',
                    valueInputOption='USER_ENTERED',
                    body={'values': headers}
                ).execute()
            )
            
            return True
        except Exception as e:
            print(f"Error initializing headers: {e}")
            return False
    
    async def log_content(
        self,
        content_type: Literal["video_avatar", "seo_article", "short_video", "carousel"],
        title: str,
        status: str = "generated",
        file_url: str = "",
        platform: str = "",
        notes: str = ""
    ) -> bool:
        """Логирует контент в таблицу"""
        row = SheetRow(
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            content_type=content_type,
            title=title,
            status=status,
            file_url=file_url,
            platform=platform,
            notes=notes
        )
        return await self.add_row_to_sheet(row)
    
    async def create_drive_folder(self, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Создаёт папку на Google Drive"""
        if not self.is_authorized() or not self.drive_service:
            return None
        
        try:
            file_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent_id:
                file_metadata['parents'] = [parent_id]
            
            loop = asyncio.get_event_loop()
            folder = await loop.run_in_executor(
                None,
                lambda: self.drive_service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
            )
            
            return folder.get('id')
        except Exception as e:
            print(f"Error creating folder: {e}")
            return None

google_service = GoogleService()
