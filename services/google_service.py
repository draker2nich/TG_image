import os
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass
import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from config import config

SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets'
]

@dataclass
class UploadResult:
    success: bool
    file_id: Optional[str] = None
    file_url: Optional[str] = None
    error: Optional[str] = None

@dataclass
class SheetRow:
    date: str
    content_type: str
    title: str
    status: str
    file_url: str = ""
    platform: str = ""
    notes: str = ""

class GoogleService:
    def __init__(self):
        self.spreadsheet_id = config.GOOGLE_SPREADSHEET_ID
        self.drive_folder_id = config.GOOGLE_DRIVE_FOLDER_ID
        self.service_account_file = config.GOOGLE_SERVICE_ACCOUNT_FILE
        
        self.creds = None
        self.drive_service = None
        self.sheets_service = None
        self._initialized = False
    
    def is_configured(self) -> bool:
        return bool(
            self.service_account_file and 
            os.path.exists(self.service_account_file)
        )
    
    async def initialize(self) -> bool:
        """Инициализирует сервисы Google API через Service Account"""
        if self._initialized:
            return True
        
        if not self.is_configured():
            return False
        
        try:
            loop = asyncio.get_event_loop()
            
            self.creds = await loop.run_in_executor(
                None,
                lambda: service_account.Credentials.from_service_account_file(
                    self.service_account_file, scopes=SCOPES
                )
            )
            
            self.drive_service = await loop.run_in_executor(
                None, lambda: build('drive', 'v3', credentials=self.creds)
            )
            self.sheets_service = await loop.run_in_executor(
                None, lambda: build('sheets', 'v4', credentials=self.creds)
            )
            
            self._initialized = True
            return True
        except Exception as e:
            print(f"Google init error: {e}")
            return False
    
    async def upload_file_to_drive(
        self,
        file_content: bytes,
        file_name: str,
        mime_type: str = "application/octet-stream",
        folder_id: Optional[str] = None
    ) -> UploadResult:
        """Загружает файл на Google Drive"""
        if not await self.initialize():
            return UploadResult(success=False, error="Google API not initialized")
        
        folder = folder_id or self.drive_folder_id
        
        try:
            file_metadata = {'name': file_name}
            if folder:
                file_metadata['parents'] = [folder]
            
            media = MediaIoBaseUpload(
                io.BytesIO(file_content),
                mimetype=mime_type,
                resumable=True
            )
            
            loop = asyncio.get_event_loop()
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
        mime_type: str = "video/mp4"
    ) -> UploadResult:
        """Скачивает файл по URL и загружает на Drive"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status != 200:
                        return UploadResult(success=False, error=f"Download failed: {resp.status}")
                    content = await resp.read()
            
            return await self.upload_file_to_drive(content, file_name, mime_type)
        except Exception as e:
            return UploadResult(success=False, error=str(e))
    
    async def add_row_to_sheet(self, row: SheetRow) -> bool:
        """Добавляет строку в Google Sheets"""
        if not await self.initialize():
            return False
        
        if not self.spreadsheet_id:
            return False
        
        try:
            values = [[
                row.date, row.content_type, row.title,
                row.status, row.file_url, row.platform, row.notes
            ]]
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range='A:G',
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body={'values': values}
                ).execute()
            )
            return True
        except Exception as e:
            print(f"Sheet error: {e}")
            return False
    
    async def init_sheet_headers(self) -> bool:
        """Инициализирует заголовки"""
        if not await self.initialize():
            return False
        
        if not self.spreadsheet_id:
            return False
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range='A1:G1'
                ).execute()
            )
            
            if result.get('values'):
                return True
            
            headers = [['Дата', 'Тип контента', 'Название', 'Статус', 'Ссылка', 'Платформа', 'Примечания']]
            
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
            print(f"Headers error: {e}")
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

google_service = GoogleService()