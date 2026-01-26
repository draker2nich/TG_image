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
class ContentPlanRow:
    """Строка контент-плана"""
    topic: str
    category: str  # пост, статья, видео с аватаром, видео от сора/вео
    platform: str  # инст, тикток, ютуб
    status: str  # Сгенерировано / Не сгенерировано

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
    
    async def init_sheet_headers(self) -> bool:
        """Инициализирует заголовки для контент-плана"""
        if not await self.initialize():
            return False
        
        if not self.spreadsheet_id:
            return False
        
        try:
            loop = asyncio.get_event_loop()
            
            # Проверяем существующие заголовки
            result = await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range='A1:D1'
                ).execute()
            )
            
            values = result.get('values')
            if values and len(values[0]) >= 4:
                # Заголовки уже есть
                return True
            
            # Создаём новые заголовки
            headers = [['Тема', 'Категория', 'Платформа', 'Статус']]
            
            await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range='A1:D1',
                    valueInputOption='USER_ENTERED',
                    body={'values': headers}
                ).execute()
            )
            
            # Форматируем заголовки (жирный шрифт)
            await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "repeatCell": {
                                    "range": {
                                        "sheetId": 0,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1
                                    },
                                    "cell": {
                                        "userEnteredFormat": {
                                            "textFormat": {"bold": True},
                                            "backgroundColor": {
                                                "red": 0.9,
                                                "green": 0.9,
                                                "blue": 0.9
                                            }
                                        }
                                    },
                                    "fields": "userEnteredFormat(textFormat,backgroundColor)"
                                }
                            }
                        ]
                    }
                ).execute()
            )
            
            return True
        except Exception as e:
            print(f"Headers error: {e}")
            return False
    
    async def add_content_plan_row(self, row: ContentPlanRow) -> bool:
        """Добавляет строку в контент-план"""
        if not await self.initialize():
            return False
        
        if not self.spreadsheet_id:
            return False
        
        try:
            values = [[
                row.topic,
                row.category,
                row.platform,
                row.status
            ]]
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range='A:D',
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body={'values': values}
                ).execute()
            )
            return True
        except Exception as e:
            print(f"Sheet error: {e}")
            return False
    
    async def log_content_plan_idea(
        self,
        topic: str,
        category: Literal["пост", "статья", "видео с аватаром", "видео от сора/вео"],
        platform: Literal["инст", "тикток", "ютуб", "блог"],
        status: Literal["Сгенерировано", "Не сгенерировано"] = "Не сгенерировано"
    ) -> bool:
        """Логирует идею контент-плана в Google Sheets"""
        row = ContentPlanRow(
            topic=topic,
            category=category,
            platform=platform,
            status=status
        )
        return await self.add_content_plan_row(row)
    
    async def update_content_status(
        self,
        topic: str,
        status: Literal["Сгенерировано", "Не сгенерировано"]
    ) -> bool:
        """Обновляет статус контента по теме"""
        if not await self.initialize():
            return False
        
        if not self.spreadsheet_id:
            return False
        
        try:
            loop = asyncio.get_event_loop()
            
            # Получаем все данные
            result = await loop.run_in_executor(
                None,
                lambda: self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range='A:D'
                ).execute()
            )
            
            values = result.get('values', [])
            
            # Ищем строку с нужной темой
            for i, row in enumerate(values):
                if i == 0:  # Пропускаем заголовок
                    continue
                if row and row[0] == topic:
                    # Обновляем статус (столбец D)
                    await loop.run_in_executor(
                        None,
                        lambda: self.sheets_service.spreadsheets().values().update(
                            spreadsheetId=self.spreadsheet_id,
                            range=f'D{i+1}',
                            valueInputOption='USER_ENTERED',
                            body={'values': [[status]]}
                        ).execute()
                    )
                    return True
            
            return False
        except Exception as e:
            print(f"Update status error: {e}")
            return False

google_service = GoogleService()