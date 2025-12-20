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

    def get_members(self, limit=50):
        sheet = self.get_sheet()
        if not sheet: return []
        try:
            # Get all values (skip header)
            all_values = sheet.get_all_values()[1:] 
            # Reverse to show newest first, take top 'limit'
            return all_values[::-1][:limit]
        except Exception as e:
            logger.error(f"Get Members Error: {e}")
            return []

    def search_members(self, query):
        sheet = self.get_sheet()
        if not sheet: return []
        try:
            all_values = sheet.get_all_values()[1:]
            query = query.lower()
            matches = []
            for row in all_values:
                # Row Structure: [Timestamp, Email, Name, Matric, IC, Program]
                # Check Name(2), Matric(3), IC(4) - adjust indices if needed based on previous code
                # In find_member, Matric is col 4 (index 3). Name is col 3 (index 2). IC is col 5 (index 4).
                if len(row) > 4:
                    name = row[2].lower()
                    matric = row[3].lower()
                    ic = str(row[4]).lower()
                    
                    if query in name or query in matric or query in ic:
                        matches.append(row)
            return matches
        except Exception as e:
            logger.error(f"Search Error: {e}")
            return []

    def delete_member(self, matric):
        sheet = self.get_sheet()
        if sheet:
            cell = sheet.find(matric, in_column=4)
            if cell:
                sheet.delete_rows(cell.row)
                return True, cell.row
            return False, None
        return None, None

    # --- USER TRACKING FOR BROADCAST ---
    def get_users_sheet(self):
        try:
             client = self.get_sheet().client # Hack to get client from the main sheet object
             try:
                 return client.open_by_key(self.sheet_id).worksheet("Users")
             except gspread.WorksheetNotFound:
                 # Create if missing
                 sheet = client.open_by_key(self.sheet_id).add_worksheet(title="Users", rows=1000, cols=3)
                 sheet.append_row(["User ID", "Name", "Joined Date"])
                 return sheet
        except Exception as e:
            logger.error(f"Users Sheet Error: {e}")
            return None

    def log_user(self, user_id, name):
        # Optimized: In real app, cache this. For now, check if exists to avoid dupes.
        sheet = self.get_users_sheet()
        if not sheet: return
        try:
            # Check if ID exists (Col 1)
            cell = sheet.find(str(user_id), in_column=1)
            if not cell:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet.append_row([str(user_id), name, timestamp])
        except Exception as e:
            logger.error(f"Log User Error: {e}")

    def get_all_users(self):
        sheet = self.get_users_sheet()
        if not sheet: return []
        try:
            # Return list of user_ids (Col 1), skip header
            vals = sheet.col_values(1)[1:] 
            return [int(x) for x in vals if x.isdigit()]
        except Exception as e:
            logger.error(f"Get Users Error: {e}")
            return []

    def is_admin(self, user_id):
        return user_id in self.admin_ids

# Singleton instance
db = Database()
