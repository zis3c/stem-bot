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
            for row in all_rows[1:]:
                # Matric is Col 4 (index 3). Row structure: [Time, Email, Name, Matric, IC, Prog, ...]
                # Normalize matric
                if len(row) > 3:
                    mat = str(row[3]).strip().upper()
                    if mat:
                        cache[mat] = row
            
            self.student_cache = cache
            self.last_student_refresh = time.time()
            logger.info(f"Student Cache Refreshed: {len(cache)} records.")
            
        except Exception as e:
            logger.error(f"Cache Refresh Error: {e}")

    def find_member(self, matric):
        # 1. Try Cache First (0 API Calls)
        self.refresh_student_cache() # Checks TTL internaly
        
        if matric in self.student_cache:
            # We return None for row_index because cache doesn't track live row positions perfectly
            # and verify flow doesn't need it.
            return self.student_cache[matric], None
            
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
        # Optimized: Count cache
        if self.student_cache:
            return len(self.student_cache)
        # Fallback
        # Fallback
        self.refresh_student_cache()
        return len(self.student_cache)

    def add_member(self, name, matric, ic, prog):
        sheet = self.get_sheet("Registrations")
        if sheet:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [timestamp, "bot_add", name, matric, ic, prog, "", "", "Approved"]
            sheet.append_row(row)
            # Invalidate cache or add to it?
            # Safest: force refresh on next read? Or just add locally?
            # Adding locally is complex (row format must match).
            # Let's just set timeout to 0 to force refresh next time? No that kills concurrency.
            # Just append to cache manually.
            self.student_cache[matric] = row
            return True
        return False

    def get_members(self, limit=50):
        self.refresh_student_cache()
        # Convert cache dict values to list
        all_values = list(self.student_cache.values())
        # Cache isn't ordered by time necessarily (dict is insertion ordered in Py3.7+ but depends on load)
        # Actually sheet load order is preserved.
        # Reverse
        return all_values[::-1][:limit]

    def search_members(self, query):
        self.refresh_student_cache()
        query = query.lower()
        matches = []
        for row in self.student_cache.values():
            if len(row) > 4:
                name = row[2].lower()
                matric = row[3].lower()
                ic = str(row[4]).lower()
                
                if query in name or query in matric or query in ic:
                    matches.append(row)
        return matches

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
        sheet = self.get_users_sheet()
        if not sheet: return []
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
