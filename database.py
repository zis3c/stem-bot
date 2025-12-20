import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.sheet_id = os.getenv("SHEET_ID")
        self.google_json = os.getenv("GOOGLE_CREDENTIALS")
        self.admin_ids = self._parse_admin_ids()
        
    def _parse_admin_ids(self):
        raw = os.getenv("ADMIN_IDS", "")
        ids = set()
        if raw:
            try:
                ids = {int(x.strip()) for x in raw.split(",") if x.strip()}
            except ValueError:
                logger.error("⚠️ Error parsing ADMIN_IDS")
        return ids

    def get_sheet(self):
        try:
            if not self.google_json:
                logger.error("❌ CRITICAL: GOOGLE_CREDENTIALS missing!")
                return None
                
            scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            try:
                creds_dict = json.loads(self.google_json)
            except json.JSONDecodeError as je:
                 logger.error(f"❌ JSON Decode Error: {je}")
                 return None
                 
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            return client.open_by_key(self.sheet_id).sheet1
        except Exception as e:
            logger.error(f"DB Connection Error: {e}")
            logger.error(traceback.format_exc())
            return None

    def find_member(self, matric):
        sheet = self.get_sheet()
        if not sheet: return None, None
        
        # Search Col D (Matric)
        cell = sheet.find(matric, in_column=4)
        if cell:
            return sheet.row_values(cell.row), cell.row
        return None, None

    def get_stats(self):
        sheet = self.get_sheet()
        if sheet:
            # Assumes 1 header row
            return len(sheet.get_all_values()) - 1
        return 0

    def add_member(self, name, matric, ic, prog):
        sheet = self.get_sheet()
        if sheet:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Columns: Timestamp, Email, Name, Matric, IC, Program
            row = [timestamp, "bot_add", name, matric, ic, prog]
            sheet.append_row(row)
            return True
        return False

    def delete_member(self, matric):
        sheet = self.get_sheet()
        if sheet:
            cell = sheet.find(matric, in_column=4)
            if cell:
                sheet.delete_rows(cell.row)
                return True, cell.row
            return False, None
        return None, None

    def is_admin(self, user_id):
        return user_id in self.admin_ids

# Singleton instance
db = Database()
