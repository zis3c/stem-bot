/**
 * Google Apps Script for STEM Bot Automation
 * 
 * INSTRUCTIONS:
 * 1. Open your Google Sheet.
 * 2. Go to Extensions > Apps Script.
 * 3. Delete any existing code and paste this entire script.
 * 4. Save the project (Cmd+S or Ctrl+S).
 * 5. Run the 'setupTrigger' function once to authorize and set up the automation.
 *    - Click 'Run' > 'setupTrigger'.
 *    - Grant permissions if asked.
 */

// --- CONFIGURATION ---
var SHEET_NAME = "Registrations"; // Change if your sheet name is different

// Column Indices (1-based for getRange, but 0-based for array access usually)
// A=1, B=2, ...
var COL_TIMESTAMP = 1;      // A
var COL_MATRIC = 4;         // D
var COL_USAS_EMAIL = 9;     // I
var COL_DATE_ENTRY = 14;    // N
var COL_MEMBERSHIP = 16;    // P

/**
 * Triggered automatically on form submit.
 * Uses the event object (e) to get the row efficiently.
 */
function onFormSubmit(e) {
    if (!e) {
        Logger.log("⚠️ You are running this manually. 'e' is undefined. Running testLastRow() instead.");
        testLastRow();
        return;
    }

    // Valid event. Use the sheet where the submission happened.
    var sheet = e.range.getSheet();
    var row = e.range.getRow();

    Logger.log("Form Submitted on Sheet: " + sheet.getName() + ", Row: " + row);
    processRow(sheet, row);
}

/**
 * Manual testing function. Processes the last row.
 */
function testLastRow() {
    var sheet = getTargetSheet();
    if (!sheet) {
        Logger.log("❌ CRITICAL: Could not find any sheet.");
        return;
    }

    var lastRow = sheet.getLastRow();
    Logger.log("Testing Last Row: " + lastRow + " on sheet '" + sheet.getName() + "'");
    processRow(sheet, lastRow);
}

/**
 * Helper to get the correct sheet safely
 */
function getTargetSheet() {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(SHEET_NAME);
    if (!sheet) {
        // Fallback: Get the first sheet (usually 'Form Responses 1')
        sheet = ss.getSheets()[0];
        Logger.log("⚠️ Sheet '" + SHEET_NAME + "' not found. Fallback to first sheet: '" + sheet.getName() + "'");
    }
    return sheet;
}

/**
 * Main Logic to populate columns
 */
function processRow(sheet, rowIdx) {
    var dataRange = sheet.getRange(rowIdx, 1, 1, 18); // Read cols A to R
    var values = dataRange.getValues()[0];

    // 1. Get Timestamp (Col A) - Index 0
    var timestamp = values[0];
    if (!timestamp) return; // Empty row?

    var dateObj = new Date(timestamp);

    // 2. Automate Date of Entry (Col N) - Index 13
    // Format: MM/DD/YYYY or DD/MM/YYYY based on locale? 
    // User req: '12/19/2025' (MM/DD/YYYY usually or DD/MM/YYYY depending on region)
    // Let's stick to generic YYYY-MM-DD or standard Date object which Sheets handles well.
    // Actually user example '12/19/2025' is MM/DD/YYYY.
    var dateEntry = Utilities.formatDate(dateObj, Session.getScriptTimeZone(), "MM/dd/yyyy");

    // 3. Automate USAS Email (Col I) - Index 8
    // Source: Matric (Col D) - Index 3
    var matricRaw = String(valueqs[3]).trim();
    var matric = matricRaw.toUpperCase();
    var usasEmail = "";
    if (matric) {
        usasEmail = matric + "@student.usas.edu.my";
    }

    // 3b. Name (Col C) - Index 2
    var nameRaw = String(values[2]).trim();
    var name = nameRaw.toUpperCase();

    // 4. Automate Membership Number (Col P) - Index 15
    // Format: STEM(YY/YY+1)XXXX
    var memberId = generateMembershipId(sheet, dateObj, rowIdx);

    // --- WRITE UPDATES ---
    // Update Name (3), Matric (4), Email (9), Date (14), MemID (16)

    // Capitalize Name & Matric in place if needed
    if (name !== nameRaw) sheet.getRange(rowIdx, 3).setValue(name);
    if (matric !== matricRaw) sheet.getRange(rowIdx, COL_MATRIC).setValue(matric);

    sheet.getRange(rowIdx, COL_USAS_EMAIL).setValue(usasEmail);
    sheet.getRange(rowIdx, COL_DATE_ENTRY).setValue(dateEntry);
    // Only write ID if it doesn't exist (prevent overwriting if re-run)
    var currentId = values[15];
    if (!currentId || currentId === "") {
        sheet.getRange(rowIdx, COL_MEMBERSHIP).setValue(memberId);
    }
}

/**
 * Generates the Membership ID
 */
function generateMembershipId(sheet, dateObj, currentRowIdx) {
    // 1. Calculate Session
    // If Month >= 8 (September - 0-indexed is 8), then Session is Current/Next.
    // User said "STEM(25/26)0001".
    var year = dateObj.getFullYear();
    var month = dateObj.getMonth(); // 0-11. September is 8.

    var startYear, endYear;

    if (month >= 8) { // September onwards
        startYear = year;
        endYear = year + 1;
    } else {
        // Before September, belongs to previous session start
        startYear = year - 1;
        endYear = year;
    }

    var yyStart = String(startYear).slice(-2);
    var yyEnd = String(endYear).slice(-2);
    var prefix = "STEM(" + yyStart + "/" + yyEnd + ")";

    // 2. Find Max ID with this prefix
    // Read all of Column P up to the previous row
    // Optimization: If rows are huge, this might be slow, but for <50k rows it's fine.
    // We scan ALL rows to be safe, excluding current one if needed.

    var lastRow = sheet.getLastRow();
    // If we are at row 2, there are no previous rows.
    var maxSeq = 0;

    if (lastRow > 1) {
        var ids = sheet.getRange(2, COL_MEMBERSHIP, lastRow - 1, 1).getValues(); // Get all IDs

        for (var i = 0; i < ids.length; i++) {
            // Don't check the current row being processed (if we are re-processing)
            // Row index in sheet is i + 2.
            if ((i + 2) == currentRowIdx) continue;

            var val = String(ids[i][0]);
            if (val.startsWith(prefix)) {
                // Extract last 4 digits
                var remainder = val.replace(prefix, "");
                var seq = parseInt(remainder, 10);
                if (!isNaN(seq)) {
                    if (seq > maxSeq) maxSeq = seq;
                }
            }
        }
    }

    // 3. Increment
    var newSeq = maxSeq + 1;
    var paddedSeq = String(newSeq).padStart(4, '0');

    return prefix + paddedSeq;
}

/**
 * TRIGGER SETUP
 * Run this function ONCE manually.
 */
function setupTrigger() {
    var triggers = ScriptApp.getProjectTriggers();

    // Clear existing to avoid dupes
    for (var i = 0; i < triggers.length; i++) {
        if (triggers[i].getHandlerFunction() === "onFormSubmit") {
            ScriptApp.deleteTrigger(triggers[i]);
        }
    }

    // Create new
    ScriptApp.newTrigger("onFormSubmit")
        .forSpreadsheet(SpreadsheetApp.getActive())
        .onFormSubmit()
        .create();

    Logger.log("Trigger set up successfully!");
}
