import os
import json
import logging
import time  # Imported time
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
        self.last_config_refresh = 0
        
        # Student Cache
        self.student_cache = {} # {matric_str: [row_data]}
        self.last_student_refresh = 0
        self.CACHE_TTL = 600 # 10 Minutes
        
        # User Log Cache (to avoid repeated writes)
        self.logged_users_cache = set()
        
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
            scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            
            if not self.google_json:
                # Fallback to local file if env var is missing
                if os.path.exists("service_account.json"):
                    with open("service_account.json") as f:
                        creds_dict = json.load(f)
                else:
                    logger.error("❌ CRITICAL: GOOGLE_CREDENTIALS missing!")
                    return None
            else:
                try:
                    creds_dict = json.loads(self.google_json)
                except json.JSONDecodeError:
                     # Fallback to local file on decode error
                    if os.path.exists("service_account.json"):
                        with open("service_account.json") as f:
                            creds_dict = json.load(f)
                    else:
                        logger.error("❌ JSON Decode Error in Env")
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

    def refresh_system_config(self, force=False):
        """Reloads admins and config from sheet. Cached for 5 minutes."""
        if not force and (time.time() - self.last_config_refresh < 300):
            return

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
            
            self.last_config_refresh = time.time()
            logger.info("System Config Refreshed (from Sheet)")
                        
        except Exception as e:
            logger.error(f"System Config Load Fail: {e}")

    def is_superadmin(self, user_id):
        return user_id in self.superadmin_ids

    def is_admin(self, user_id):
        # Superadmins + Env Admins + Sheet Admins
        return (user_id in self.superadmin_ids or 
                user_id in self.admin_ids or 
                user_id in self.cached_sheet_admins)

    def get_all_admin_ids(self):
        """Returns a set of ALL admin IDs (Super + Env + Sheet)."""
        return set(self.superadmin_ids) | set(self.admin_ids) | set(self.cached_sheet_admins)

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
            self.refresh_system_config(force=True)
            return True
        except Exception as e:
            logger.error(f"Add Admin Error: {e}")
            return False

    def remove_admin(self, user_id):
        try:
            ws = self.get_sheet("system_admins")
            cell = ws.find(str(user_id))
            ws.delete_rows(cell.row)
            self.refresh_system_config(force=True)
            return True
        except Exception as e:
            logger.error(f"Del Admin Error: {e}")
            return False

    def refresh_student_cache(self, force=False):
        """Loads all students into memory. 0 API calls for subsequent reads."""
        if not force and (time.time() - self.last_student_refresh < self.CACHE_TTL):
            return

        try:
            ws = self.get_sheet("Registrations")
            if not ws: return
            
            # Fetch ALL values in one go (1 API Call)
            all_rows = ws.get_all_values()
            
            # Headers are row 0
            # Data starts row 1
            cache = {}
            for i, row in enumerate(all_rows[1:], start=2): # Start=2 matches Sheet Row Number
                # New Mapping:
                # A(0)=Time, B=Email, C=Name, D(3)=Matric, E=Courses, ... J(9)=IC, ... Q(16)=Receipt, R(17)=Status
                
                # Normalize matric (Col 3)
                if len(row) > 3:
                    mat = str(row[3]).strip().upper()
                    if mat:
                        cache[mat] = (row, i) # Store (Data, RowIndex)
            
            self.student_cache = cache
            self.last_student_refresh = time.time()
            logger.info(f"Student Cache Refreshed: {len(cache)} records.")
            
        except Exception as e:
            logger.error(f"Cache Refresh Error: {e}")

    def find_member(self, matric):
        # 1. Try Cache First (0 API Calls)
        self.refresh_student_cache() # Checks TTL internaly
        
        if matric in self.student_cache:
            # Return tuple (row_data, row_index)
            return self.student_cache[matric]
            
        # 2. Fallback to API (Slow) if not in cache? 
        # For High Concurrency mode, we TRUST the cache. 
        # If user just registered, it might not be there yet. 
        # But for "Check Membership", better to fail fast or tell them to wait?
        # Let's fallback ONLY if cache is empty (startup).
        # Actually, let's just return None if not in cache. 
        # If we enable "Hybrid", we could mistakenly rate limit. 
        # Safe bet: Return None. User can try again in 10 mins or Admin refreshes.
        return None, None

    def get_stats(self):
        """Returns stats: Total, Verified, Pending."""
        self.refresh_student_cache()
        
        total = 0
        verified = 0
        pending = 0
        
        for row, _ in self.student_cache.values():
            total += 1
            # Status is at index 17 (Col R).
            status = row[17].strip().title() if len(row) > 17 else ""
            
            if status == "Approved":
                verified += 1
            elif not status or status == "Pending":
                pending += 1
                
        return {
            "total": total,
            "verified": verified,
            "pending": pending
        }

    def add_member(self, name, matric, ic, prog):
        sheet = self.get_sheet("Registrations")
        if sheet:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # New 18-col structure
            # A=Time, B=Email, C=Name, D=Matric, E=Courses, F-I, J=IC, K-Q, R=Status
            row = [""] * 18
            row[0] = timestamp
            row[1] = "bot_add"
            row[2] = name
            row[3] = matric
            row[4] = prog # Courses
            row[9] = ic   # IC Number
            row[17] = "Approved" # Status
            
            sheet.append_row(row)
            # Invalidate cache to force reload next time (simplest way to get correct row index)
            self.last_student_refresh = 0
            return True
        return False

    def get_members(self, limit=50):
        self.refresh_student_cache()
        # Convert cache dict values to list of ROWS only
        # cache values are (row, index)
        all_values = [row for row, idx in self.student_cache.values()]
        # Cache isn't ordered by time necessarily (dict is insertion ordered in Py3.7+ but depends on load)
        # Actually sheet load order is preserved.
        # Reverse
        return all_values[::-1][:limit]

    def search_members(self, query):
        self.refresh_student_cache()
        query = query.lower()
        matches = []
        for row, _ in self.student_cache.values():
            if len(row) > 9:
                name = row[2].lower()
                matric = row[3].lower()
                ic = str(row[9]).lower() # J is index 9
                
                if query in name or query in matric or query in ic:
                    matches.append(row)
        return matches

    def delete_member(self, matric):
        sheet = self.get_sheet("Registrations")
        if sheet:
            # Matric is Col D (4)
            cell = sheet.find(matric, in_column=4)
            if cell:
                sheet.delete_rows(cell.row)
                
                # Update Cache Immediately
                if matric in self.student_cache:
                    del self.student_cache[matric]
                
                # Force full refresh next time to handle duplicates/consistency
                self.last_student_refresh = 0
                    
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
        """Logs user to sheet if not already logged this session. Blocking I/O."""
        if user_id in self.logged_users_cache:
            return # Already logged this run
            
        try:
            self.logged_users_cache.add(user_id) # Mark as logged immediately
            
            sheet = self.get_users_sheet()
            if not sheet: return

            # Check if ID exists in sheet (to be safe across restarts)
            # Optimization: We just append and rely on "Unique" later or just allow dupe rows for stats.
            # Checking sheet.find every time is expensive (1 API call).
            # Let's just append. It's a log.
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([str(user_id), name, timestamp])
            
        except Exception as e:
            logger.error(f"Log User Error: {e}")

    def get_all_users(self):
        """Returns unique list of all user IDs from the log sheet."""
        sheet = self.get_users_sheet()
        if not sheet: return []
        
        try:
            # Col 1 is ID
            ids = sheet.col_values(1)
            # Row 1 is header "User ID"
            if len(ids) > 1:
                return list(set(ids[1:])) # Deduplicate
            return []
        except Exception as e:
            logger.error(f"Get Users Error: {e}")
            return []
        try:
            # Return list of user_ids (Col 1), skip header
            vals = sheet.col_values(1)[1:] 
            return [int(x) for x in vals if x.isdigit()]
        except Exception as e:
            logger.error(f"Get Users Error: {e}")
            return []



    # --- ACTION LOGGING (FILE BASED) ---
    def log_action(self, name, action, details, role="ADMIN"):
        """Logs actions to a local file for daily reporting."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {role}: {name} | ACTION: {action} | {details}\n"
        
        try:
            with open("admin_actions.log", "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"Failed to write to log: {e}")

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
                # We need Col Q (index 16) for Receipt.
                if len(row) <= 16: continue 
                
                receipt = row[16].strip()
                # Status is Col R (index 17).
                status = row[17].strip() if len(row) > 17 else ""
                
                if receipt and not status:
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
            # Skip header (row 1)
            for i, row in enumerate(rows[1:], start=2):
                # Ensure row has enough columns (Col R is index 17)
                status = row[17].strip().title() if len(row) > 17 else "Approved"
                # Normalize "Approved"
                if status not in ["Pending", "Rejected", "Approve", "Reject"]: status = "Approved"
                
                if status == status_filter:
                    filtered.append({
                        'row': i,
                        'name': row[2] if len(row) > 2 else "Unknown",
                        'matric': row[3] if len(row) > 3 else "Unknown",
                        'ic': row[9] if len(row) > 9 else "Unknown", # J=9
                        'prog': row[4] if len(row) > 4 else "Unknown", # E=4
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
            # Update Cell (Row, Col 18 (R))
            sheet.update_cell(row_index, 18, status)
            return True
        except Exception as e:
            logger.error(f"Update Status Error: {e}")
            return False

# Singleton instance
db = Database()
