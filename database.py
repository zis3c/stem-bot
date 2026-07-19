import os
import json
import logging
import re
import time  # Imported time
import threading
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from security_utils import sanitize_sensitive_text

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACTIVITY_LOG_PATH = os.path.join(BASE_DIR, "activity.log")
LAST_MAINT_PATH = os.path.join(BASE_DIR, "last_maint.txt")
KL_TZ = ZoneInfo("Asia/Kuala_Lumpur")


def _redact_log_text(value):
    if value is None:
        return ""
    text = str(value)
    text = re.sub(
        r'([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})',
        r'\1***@\2',
        text,
    )
    text = re.sub(r"\b\d{6,}\b", "***REDACTED***", text)
    return text

class Database:
    def __init__(self):
        self.sheet_id = os.getenv("SHEET_ID")
        self.google_json = os.getenv("GOOGLE_CREDENTIALS")
        self.registrations_sheet_name = os.getenv("REGISTRATIONS_SHEET_NAME", "STEM DB").strip() or "STEM DB"
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
        
        self._init_maint_file()
        # Avoid blocking process startup on network I/O.
        threading.Thread(
            target=self.refresh_system_config,
            kwargs={"force": True},
            daemon=True
        ).start()

    def _init_maint_file(self):
        """Initializes the local maintenance tracking file if missing."""
        if not os.path.exists(LAST_MAINT_PATH):
            with open(LAST_MAINT_PATH, "w") as f:
                f.write("2000-01-01") # Old date

    def get_last_maintenance(self):
        """Returns the last maintenance date from local file."""
        try:
            if os.path.exists(LAST_MAINT_PATH):
                with open(LAST_MAINT_PATH, "r") as f:
                    return f.read().strip()
        except: pass
        return "2000-01-01"

    def update_last_maintenance(self, date_value=None):
        """Updates the last maintenance/report date."""
        try:
            value = date_value or datetime.now(KL_TZ).strftime("%Y-%m-%d")
            with open(LAST_MAINT_PATH, "w") as f:
                f.write(value)
            return True
        except Exception as e:
            logger.error(f"Failed to update {LAST_MAINT_PATH}: {e}")
            return False

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

            if not self.sheet_id:
                logger.error("❌ CRITICAL: SHEET_ID missing!")
                return None
            
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
            
            # Main registrations tab is name-based, with legacy fallback to sheet1.
            if sheet_name == "Registrations":
                try:
                    return sh.worksheet(self.registrations_sheet_name)
                except gspread.WorksheetNotFound:
                    if self.registrations_sheet_name != "Registrations":
                        try:
                            return sh.worksheet("Registrations")
                        except gspread.WorksheetNotFound:
                            pass

                    try:
                        if sh.worksheets():
                            legacy_sheet = sh.sheet1
                            logger.warning(
                                "Registrations sheet '%s' not found, falling back to first tab '%s'.",
                                self.registrations_sheet_name,
                                legacy_sheet.title,
                            )
                            return legacy_sheet
                    except Exception:
                        pass

                    logger.error(
                        "Registrations sheet missing. Expected tab '%s' in spreadsheet %s.",
                        self.registrations_sheet_name,
                        self.sheet_id,
                    )
                    return None
                 
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

    def _parse_sheet_date(self, raw_value):
        """Parse common sheet date/time formats into datetime."""
        if raw_value is None:
            return None

        text = str(raw_value).strip()
        if not text or text == "-":
            return None

        try:
            iso_value = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_value)
            return dt.replace(tzinfo=None)
        except Exception:
            pass

        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y",
        )
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _extract_birth_year(self, raw_value):
        """Extract birth year from sheet birthday value."""
        dt = self._parse_sheet_date(raw_value)
        now_year = datetime.now().year
        if dt and 1900 <= dt.year <= now_year:
            return str(dt.year)

        text = str(raw_value or "").strip()
        if not text or text == "-":
            return "Unknown"

        # Prefer explicit 4-digit year.
        m = re.search(r"(19\d{2}|20\d{2})", text)
        if m:
            return m.group(1)

        return "Unknown"

    def _normalize_status(self, status_raw):
        """Normalize raw sheet status into approved/rejected/expired/pending."""
        status = str(status_raw or "").strip().lower()
        if status in ("expired", "expire", "tamat", "luput"):
            return "expired"
        if status in ("approved", "verified", "accept", "accepted"):
            return "approved"
        if status in ("rejected", "reject"):
            return "rejected"
        return "pending"

    def get_stats(self):
        """Returns secretary-focused monthly stats + expiry counters."""
        self.refresh_student_cache()

        now = datetime.now()
        window_start = now - timedelta(days=30)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            next_month_start = month_start.replace(year=now.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=now.month + 1)

        total_last_30 = 0
        approved_last_30 = 0
        rejected_last_30 = 0
        pending_current = 0
        expiring_next_30 = 0
        expired_this_month = 0
        registered_current_month_names = []
        registered_all_names = []
        course_counts = {}
        birth_year_counts = {}
        demographic_total = 0

        for row, _ in self.student_cache.values():
            status = self._normalize_status(row[17] if len(row) > 17 else "")

            if status == "pending":
                pending_current += 1

            applied_at = self._parse_sheet_date(row[0] if len(row) > 0 else "")
            if applied_at and applied_at >= window_start:
                total_last_30 += 1
                if status == "approved":
                    approved_last_30 += 1
                elif status == "rejected":
                    rejected_last_30 += 1

            if (
                status == "approved"
                and applied_at
                and month_start <= applied_at < next_month_start
            ):
                name = str(row[2]).strip() if len(row) > 2 else ""
                if name:
                    registered_current_month_names.append(name)

            # Whole-DB demographic mix across all registered records.
            name_all = str(row[2]).strip() if len(row) > 2 else ""
            if name_all:
                registered_all_names.append(name_all)
            demographic_total += 1
            course = str(row[4]).strip() if len(row) > 4 and str(row[4]).strip() else "Unknown"
            birth_year = self._extract_birth_year(row[10] if len(row) > 10 else "")
            course_counts[course] = course_counts.get(course, 0) + 1
            birth_year_counts[birth_year] = birth_year_counts.get(birth_year, 0) + 1

            if status == "approved":
                entry_date = self._parse_sheet_date(row[13] if len(row) > 13 else "")
                if not entry_date:
                    continue

                expiry_date = entry_date + timedelta(days=365)
                if now <= expiry_date <= (now + timedelta(days=30)):
                    expiring_next_30 += 1
                if month_start <= expiry_date < next_month_start and expiry_date < now:
                    expired_this_month += 1

        decisions_last_30 = approved_last_30 + rejected_last_30
        approval_rate = (approved_last_30 / decisions_last_30 * 100.0) if decisions_last_30 else 0.0
        safe_total = max(demographic_total, 1)

        course_distribution = [
            {
                "label": course,
                "count": count,
                "pct": round((count / safe_total) * 100.0, 1),
            }
            for course, count in sorted(course_counts.items(), key=lambda item: item[1], reverse=True)
        ]
        birth_year_distribution = [
            {
                "label": year,
                "count": count,
                "pct": round((count / safe_total) * 100.0, 1),
            }
            for year, count in sorted(
                birth_year_counts.items(),
                key=lambda item: (item[0] == "Unknown", -item[1], item[0]),
            )
        ]

        return {
            "total_last_30": total_last_30,
            "approved_last_30": approved_last_30,
            "rejected_last_30": rejected_last_30,
            "pending_current": pending_current,
            "approval_rate": round(approval_rate, 1),
            "expiring_next_30": expiring_next_30,
            "expired_this_month": expired_this_month,
            "registered_current_month_count": len(registered_current_month_names),
            "registered_current_month_names": registered_current_month_names,
            "registered_all_count": len(registered_all_names),
            "registered_all_names": registered_all_names,
            "demographic_total": demographic_total,
            "course_distribution": course_distribution,
            "birth_year_distribution": birth_year_distribution,
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
        """Returns a unique list of all numeric user IDs from the log sheet."""
        sheet = self.get_users_sheet()
        if not sheet:
            return []

        try:
            # Col 1 is ID, row 1 is header "User ID".
            raw_ids = sheet.col_values(1)[1:]
            unique_ids = []
            seen = set()

            for raw_id in raw_ids:
                if not raw_id.isdigit():
                    continue

                user_id = int(raw_id)
                if user_id in seen:
                    continue

                seen.add(user_id)
                unique_ids.append(user_id)

            return unique_ids
        except Exception as e:
            logger.error(f"Get Users Error: {e}")
            return []



    # --- ACTION LOGGING (FILE BASED) ---
    def log_action(self, name, action, details, role="ADMIN"):
        """Logs actions to a local file for daily reporting."""
        timestamp = datetime.now(KL_TZ).strftime("%Y-%m-%d %H:%M:%S")
        safe_name = _redact_log_text(name)
        safe_details = _redact_log_text(details)
        log_entry = f"[{timestamp}] {role}: {safe_name} | ACTION: {action} | {safe_details}\n"
        
        try:
            with open(ACTIVITY_LOG_PATH, "a", encoding="utf-8") as f:
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
                status_norm = status.lower()

                # Treat fresh queue statuses as pending candidates.
                if receipt and (not status or status_norm == "pending admin approval" or status_norm == "pending"):
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
                # Skip non-member / malformed rows.
                if len(row) <= 3:
                    continue
                name = str(row[2]).strip() if len(row) > 2 else ""
                matric = str(row[3]).strip() if len(row) > 3 else ""
                if not matric:
                    continue

                raw_status = row[17].strip().lower() if len(row) > 17 else ""

                if raw_status in ("expired", "expire", "tamat", "luput"):
                    status = "Expired"
                elif raw_status in ("approved", "verified", "✓", "âœ“"):
                    status = "Approved"
                elif raw_status in ("rejected", "reject"):
                    status = "Rejected"
                else:
                    status = "Pending"
                
                if status == status_filter:
                    filtered.append({
                        'row': i,
                        'name': name if name else "Unknown",
                        'matric': matric,
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
    def update_status_by_row_or_matric(self, row_index, matric, status):
        """Safely updates status by row, with matric fallback if row shifted."""
        sheet = self.get_sheet("Registrations")
        if not sheet:
            return False
        target_row = row_index
        safe_matric = str(matric).strip().upper()
        try:
            row_values = sheet.row_values(target_row)
            row_matric = row_values[3].strip().upper() if len(row_values) > 3 else ""
            if row_matric != safe_matric:
                cell = sheet.find(safe_matric, in_column=4)
                if not cell:
                    return False
                target_row = cell.row

            sheet.update_cell(target_row, 18, status)
            self.last_student_refresh = 0
            return True
        except Exception as e:
            logger.error(f"Update Status Safe Error: {e}")
            return False

    def renew_membership_by_row_or_matric(self, row_index, matric):
        """Renew membership by extending expiry from max(current expiry, today) by 1 year."""
        sheet = self.get_sheet("Registrations")
        if not sheet:
            return {"ok": False, "error": "sheet_unavailable"}

        target_row = row_index
        safe_matric = str(matric).strip().upper()
        try:
            row_values = sheet.row_values(target_row)
            row_matric = row_values[3].strip().upper() if len(row_values) > 3 else ""
            if row_matric != safe_matric:
                cell = sheet.find(safe_matric, in_column=4)
                if not cell:
                    return {"ok": False, "error": "matric_not_found"}
                target_row = cell.row
                row_values = sheet.row_values(target_row)

            entry_raw = row_values[13] if len(row_values) > 13 else ""
            timestamp_raw = row_values[0] if len(row_values) > 0 else ""

            entry_dt = self._parse_sheet_date(entry_raw) or self._parse_sheet_date(timestamp_raw) or datetime.now()
            old_expiry_dt = entry_dt + timedelta(days=365)
            now_dt = datetime.now()
            renewal_anchor = old_expiry_dt if old_expiry_dt > now_dt else now_dt
            new_expiry_dt = renewal_anchor + timedelta(days=365)

            # Keep one active record: advance entry/start date and ensure approved status.
            sheet.update_cell(target_row, 14, renewal_anchor.strftime("%d/%m/%y"))  # N
            sheet.update_cell(target_row, 18, "Approved")  # R

            self.last_student_refresh = 0
            return {
                "ok": True,
                "row": target_row,
                "old_expiry": old_expiry_dt.strftime("%d/%m/%y"),
                "new_expiry": new_expiry_dt.strftime("%d/%m/%y"),
                "renewed_entry": renewal_anchor.strftime("%d/%m/%y"),
            }
        except Exception as e:
            logger.error("Renew Membership Safe Error: %s", sanitize_sensitive_text(e))
            return {"ok": False, "error": str(e)}

    def get_member_by_row_or_matric(self, row_index, matric):
        """Fetch a member row safely by row, fallback to matric search if row shifted."""
        sheet = self.get_sheet("Registrations")
        if not sheet:
            return None, None
        target_row = row_index
        safe_matric = str(matric).strip().upper()
        try:
            row_values = sheet.row_values(target_row)
            row_matric = row_values[3].strip().upper() if len(row_values) > 3 else ""
            if row_matric != safe_matric:
                cell = sheet.find(safe_matric, in_column=4)
                if not cell:
                    return None, None
                target_row = cell.row
                row_values = sheet.row_values(target_row)

            return row_values, target_row
        except Exception as e:
            logger.error(f"Get Member Safe Error: {e}")
            return None, None

    def delete_registration_by_row_or_matric(self, row_index, matric):
        """Safely deletes a registration by row, with matric fallback if row shifted."""
        sheet = self.get_sheet("Registrations")
        if not sheet:
            return False
        target_row = row_index
        safe_matric = str(matric).strip().upper()
        try:
            row_values = sheet.row_values(target_row)
            row_matric = row_values[3].strip().upper() if len(row_values) > 3 else ""
            if row_matric != safe_matric:
                cell = sheet.find(safe_matric, in_column=4)
                if not cell:
                    return False
                target_row = cell.row

            sheet.delete_rows(target_row)
            self.last_student_refresh = 0
            return True
        except Exception as e:
            logger.error(f"Delete Registration Safe Error: {e}")
            return False

# Singleton instance
db = Database()

