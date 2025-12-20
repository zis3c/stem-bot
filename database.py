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
        self.superadmin_ids = self._parse_ids("SUPERADMIN_IDS")
        self.admin_ids = self._parse_ids("ADMIN_IDS")
        
        # System Caches
        self.cached_sheet_admins = [] 
        self.maintenance_mode = False
        self.refresh_system_config()

    def _parse_ids(self, env_key):
        raw = os.getenv(env_key, "")
        ids = set()
        if raw:
            try:
                ids = {int(x.strip()) for x in raw.split(",") if x.strip()}
            except ValueError:
                logger.error(f"⚠️ Error parsing {env_key}")
        return ids

    def get_sheet(self, sheet_name="Registrations"):
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
            
            # Open Sheet
            sh = client.open_by_key(self.sheet_id)
            
            # Handle specific tabs vs default sheet1
            if sheet_name == "Registrations":
                 return sh.sheet1
                 
            try:
                return sh.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                # Create if missing (Auto-Healing)
                ws = sh.add_worksheet(title=sheet_name, rows=100, cols=10)
                if sheet_name == "system_admins":
                    ws.append_row(["User ID", "Name", "Added By"])
                elif sheet_name == "system_config":
                    ws.append_row(["Key", "Value"])
                    ws.append_row(["maintenance_mode", "False"])
                return ws
                
        except Exception as e:
            logger.error(f"DB Connection Error ({sheet_name}): {e}")
            logger.error(traceback.format_exc())
            return None

    def refresh_system_config(self):
        """Reloads admins and config from sheet."""
        try:
            # 1. Load Admins
            ws_admins = self.get_sheet("system_admins")
            if ws_admins:
                records = ws_admins.get_all_records()
                self.cached_sheet_admins = [int(r['User ID']) for r in records if str(r['User ID']).isdigit()]
            
            # 2. Load Config
            ws_config = self.get_sheet("system_config")
            if ws_config:
                records = ws_config.get_all_records()
                for r in records:
                    if r['Key'] == 'maintenance_mode':
                        self.maintenance_mode = str(r['Value']).lower() == 'true'
                        
        except Exception as e:
            logger.error(f"System Config Load Fail: {e}")

    def is_superadmin(self, user_id):
        return user_id in self.superadmin_ids

    def is_admin(self, user_id):
        # Superadmins + Env Admins + Sheet Admins
        return (user_id in self.superadmin_ids or 
                user_id in self.admin_ids or 
                user_id in self.cached_sheet_admins)

    def set_maintenance(self, enabled: bool):
        try:
            ws = self.get_sheet("system_config")
            cell = ws.find("maintenance_mode")
            ws.update_cell(cell.row, cell.col + 1, str(enabled))
            self.maintenance_mode = enabled
            return True
        except Exception as e:
            logger.error(f"Set Maint Error: {e}")
            return False

    def add_admin(self, user_id, name, added_by):
        try:
            ws = self.get_sheet("system_admins")
            ws.append_row([str(user_id), name, added_by])
            self.refresh_system_config()
            return True
        except Exception as e:
            logger.error(f"Add Admin Error: {e}")
            return False

    def remove_admin(self, user_id):
        try:
            ws = self.get_sheet("system_admins")
            cell = ws.find(str(user_id))
            ws.delete_rows(cell.row)
            self.refresh_system_config()
            return True
        except Exception as e:
            logger.error(f"Del Admin Error: {e}")
            return False

    def find_member(self, matric):
        sheet = self.get_sheet("Registrations")
        if not sheet: return None, None
        
        # Search Col D (Matric)
        try:
            cell = sheet.find(matric, in_column=4)
            if cell:
                return sheet.row_values(cell.row), cell.row
            return None, None
        except Exception:
            return None, None


    def get_stats(self):
        sheet = self.get_sheet("Registrations")
        if sheet:
            # Assumes 1 header row
            return len(sheet.get_all_values()) - 1
        return 0

    def add_member(self, name, matric, ic, prog):
        sheet = self.get_sheet("Registrations")
        if sheet:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Columns: Timestamp, Email, Name, Matric, IC, Program, (Phone/Empty), Resit, Status
            # We pad Col G (6) and Col H (7/Resit) with empty strings, and set Col I (8) to "Approved"
            row = [timestamp, "bot_add", name, matric, ic, prog, "", "", "Approved"]
            sheet.append_row(row)
            return True
        return False

    def get_members(self, limit=50):
        sheet = self.get_sheet("Registrations")
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
        sheet = self.get_sheet("Registrations")
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
        sheet = self.get_sheet("Registrations")
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
             main_sheet = self.get_sheet("Registrations")
             if not main_sheet: return None
             
             spreadsheet = main_sheet.spreadsheet
             try:
                 return spreadsheet.worksheet("Users")
             except gspread.WorksheetNotFound:
                 # Create if missing
                 sheet = spreadsheet.add_worksheet(title="Users", rows=1000, cols=3)
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



    # --- APPROVAL WORKFLOW ---
    def get_unprocessed_registrations(self):
        """Finds rows where Resit (Col 8) is present but Status (Col 9) is Empty."""
        sheet = self.get_sheet("Registrations")
        if not sheet: return []
        try:
            all_values = sheet.get_all_values()
            unprocessed = []
            
            # Start from row 2 (index 1) to skip header
            for i, row in enumerate(all_values[1:], start=2):
                # Ensure row has enough cols. Gspread might cut off empty trailing cols.
                # We need Col H (index 7).
                if len(row) <= 7: continue 
                
                resit = row[7].strip()
                # Status is Col I (index 8). If row doesn't have index 8, it's empty.
                status = row[8].strip() if len(row) > 8 else ""
                
                if resit and not status:
                    # Valid registration needing approval
                    unprocessed.append({
                        'row': i,
                        'data': row
                    })
            return unprocessed
        except Exception as e:
            logger.error(f"Error fetching members: {e}")
            return []

    def get_members_by_filter(self, status_filter):
        """Get members filtered by Status (Col I)."""
        sheet = self.get_sheet("Registrations")
        if not sheet: return []
        
        try:
            rows = sheet.get_all_values()
            filtered = []
            # Skip header (row 1)
            for i, row in enumerate(rows[1:], start=2):
                # Ensure row has enough columns (Col I is index 8)
                status = row[8].strip().title() if len(row) > 8 else "Approved"
                # Normalize "Approved"
                if status not in ["Pending", "Rejected", "Approve", "Reject"]: status = "Approved"
                
                if status == status_filter:
                    filtered.append({
                        'row': i,
                        'name': row[2] if len(row) > 2 else "Unknown",
                        'matric': row[3] if len(row) > 3 else "Unknown",
                        'ic': row[4] if len(row) > 4 else "Unknown",
                        'prog': row[5] if len(row) > 5 else "Unknown",
                        'status': status
                    })
            return filtered
        except Exception as e:
            logger.error(f"Error filtering members: {e}")
            return []

    def update_status(self, row_index, status):
        """Updates Column I (9) with status."""
        sheet = self.get_sheet("Registrations")
        if not sheet: return False
        try:
            # Update Cell (Row, Col 9)
            sheet.update_cell(row_index, 9, status)
            return True
        except Exception as e:
            logger.error(f"Update Status Error: {e}")
            return False

# Singleton instance
db = Database()
