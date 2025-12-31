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
var SHEET_NAME = "STEM DB"; // Updated to match user's actual sheet name

// Column Indices (1-based for getRange, but 0-based for array access usually)
// A=1, B=2, ...
// A=1, B=2, ...
var COL_TIMESTAMP = 1;      // A
var COL_PERSONAL_EMAIL = 2; // B (User's Personal Email)
var COL_MATRIC = 4;         // D
var COL_USAS_EMAIL = 9;     // I
var COL_DATE_ENTRY = 14;    // N
var COL_MEMBERSHIP = 16;    // P
var COL_RECEIPT_URL = 19;   // S (Payment Receipt)
var COL_INVOICE_NO = 20;    // T (Invoice No)

var FEE_AMOUNT = "RM10.00"; // Fixed Fee
var RECEIPT_FOLDER_ID = "1FmcTnwaVBS7wEvTGy75UCiIc3wYYOzkb"; // Confirmed User Folder ID
var LOGO_FILE_ID = "1a-7seaR1SGQ_xfC_PtmCsHGukcE_qjbD"; // Confirmed User Logo ID

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
 * SIMPLE EMAIL TEST
 * Run this function to test email sending to a specific address with dummy data.
 */
function testSimpleEmail() {
    var email = "r.zradzizamri@gmail.com"; // User's test email
    var name = "Test User";
    var matric = "TEST123456";
    var memberId = "STEM(24/25)9999";
    var date = "31/12/25";
    var invoiceNo = "INV-TEST999";

    Logger.log("🧪 Running Simple Email Test...");
    sendReceiptEmail(email, name, matric, memberId, date, invoiceNo);
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
 * Main Logic to populate columns and Send Email
 */
function processRow(sheet, rowIdx) {
    var dataRange = sheet.getRange(rowIdx, 1, 1, 21); // Read cols A to U (Index 21)
    var values = dataRange.getValues()[0];

    // 1. Get Timestamp (Col A) - Index 0
    var timestamp = values[0];
    if (!timestamp) return; // Empty row?

    var dateObj = new Date(timestamp);

    // 2. Automate Date of Entry (Col N) - Index 13
    var dateEntry = Utilities.formatDate(dateObj, Session.getScriptTimeZone(), "dd/MM/yy");

    // 3. Automate USAS Email (Col I) - Index 8
    var matricRaw = String(values[3]).trim();
    var matric = matricRaw.toUpperCase();
    var usasEmail = "";
    if (matric) {
        usasEmail = matric + "@student.usas.edu.my";
    }

    // 3b. Name (Col C) - Index 2
    var nameRaw = String(values[2]).trim();
    var name = nameRaw.toUpperCase();

    // 3c. Personal Email (Col B) - Index 1
    var personalEmail = String(values[COL_PERSONAL_EMAIL - 1]).trim(); // Index 1

    // 4. Automate Membership Number (Col P) - Index 15
    var memberId = generateMembershipId(sheet, dateObj, rowIdx);

    // 5. Automate Invoice Number (Col U) - Index 20
    var invoiceNo = values[COL_INVOICE_NO - 1];
    if (!invoiceNo || invoiceNo === "") {
        invoiceNo = "INV-" + Math.floor(100000 + Math.random() * 900000); // Generate new
    }

    // --- WRITE UPDATES ---
    // Update Name (3), Matric (4), Email (9), Date (14), MemID (16), Invoice (21)

    // Capitalize Name & Matric in place if needed
    if (name !== nameRaw) sheet.getRange(rowIdx, 3).setValue(name);
    if (matric !== matricRaw) sheet.getRange(rowIdx, COL_MATRIC).setValue(matric);

    sheet.getRange(rowIdx, COL_USAS_EMAIL).setValue(usasEmail);
    sheet.getRange(rowIdx, COL_DATE_ENTRY).setValue(dateEntry);
    sheet.getRange(rowIdx, COL_INVOICE_NO).setValue(invoiceNo); // Save Invoice

    // Only write ID if it doesn't exist (prevent overwriting if re-run)
    var currentId = values[15]; // Index 15 is Col P

    // Force write if it's empty
    if (!currentId || currentId === "") {
        sheet.getRange(rowIdx, COL_MEMBERSHIP).setValue(memberId);

        // --- SEND RECEIPT EMAIL (Only if ID was just generated/new processing) ---
        // This prevents double emailing if you run the script again on existing rows
        if (personalEmail && personalEmail.includes("@")) {
            var receiptUrl = sendReceiptEmail(personalEmail, name, matric, memberId, dateEntry, invoiceNo);

            // Save Receipt URL to Col T (Index 20)
            if (receiptUrl) {
                sheet.getRange(rowIdx, COL_RECEIPT_URL).setValue(receiptUrl);
            }
        } else {
            Logger.log("⚠️ No valid email found for receipt: " + personalEmail);
        }
    } else {
        // If ID exists, we assume processed. 
        // Uncomment below to FORCE email even if ID exists (Testing only)
        // var receiptUrl = sendReceiptEmail(personalEmail, name, matric, currentId, dateEntry, invoiceNo);
        // if(receiptUrl) sheet.getRange(rowIdx, COL_RECEIPT_URL).setValue(receiptUrl);
    }
}

/**
 * Generates and Sends the HTML Receipt Email with PDF Attachment + Download Link
 * Returns the download URL
 */
function sendReceiptEmail(email, name, matric, memberId, date, invoiceNo) {
    try {
        var receiptNo = memberId; // Use MemberID for easy tracking
        var fileName = "STEM_Receipt_" + memberId + ".pdf";

        // 0. Fetch Logo (if configured)
        var logoBase64 = getEncodedLogo(LOGO_FILE_ID);

        // 1. Generate HTML for PDF Attachment (Table/Formal Style)
        var pdfHtml = createPdfHtml(name, matric, memberId, date, invoiceNo, receiptNo, logoBase64);
        var pdfBlob = Utilities.newBlob(pdfHtml, "text/html", "Receipt-" + memberId + ".html").getAs("application/pdf");
        pdfBlob.setName(fileName);

        // 2. Save PDF to Google Drive & Get Download Link
        var file;
        try {
            if (RECEIPT_FOLDER_ID && RECEIPT_FOLDER_ID !== "PASTE_YOUR_FOLDER_ID_HERE") {
                var folder = DriveApp.getFolderById(RECEIPT_FOLDER_ID);
                file = folder.createFile(pdfBlob);
                Logger.log("📂 Saved to Folder: " + folder.getName());
            } else {
                throw new Error("Folder ID not set.");
            }
        } catch (e) {
            Logger.log("⚠️ Saving to Root (Folder ID missing/invalid).");
            file = DriveApp.createFile(pdfBlob);
        }

        // Make it viewable by anyone with link so the button works
        file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

        // Get the direct download-like URL (View URL commonly used as download)
        // var downloadUrl = file.getUrl(); // OLD: Opens Viewer
        var downloadUrl = "https://drive.google.com/uc?export=download&id=" + file.getId(); // NEW: Auto Download

        // 3. Generate HTML for Email Body (Card Style) - With working button!
        var emailHtml = createEmailHtml(name, matric, memberId, date, invoiceNo, receiptNo, downloadUrl);

        MailApp.sendEmail({
            to: email,
            subject: "Payment Receipt - STEM Membership",
            htmlBody: emailHtml
            // attachments: [pdfBlob] // Removed as per user request (Drive Link Only)
        });

        // Optional: Clean up file from Drive if you don't want to save a copy
        // file.setTrashed(true); // Uncomment to delete after sending

        Logger.log("✅ Receipt sent to: " + email);
        return downloadUrl; // Return URL to save to Sheet
    } catch (e) {
        Logger.log("❌ Failed to send email: " + e.toString());
        return null;
    }
}

/**
 * Helper: Fetch Image from Drive and convert to Base64 for embedding
 */
function getEncodedLogo(fileId) {
    if (!fileId || fileId === "PASTE_YOUR_LOGO_ID_HERE") return null;
    try {
        var file = DriveApp.getFileById(fileId);
        var blob = file.getBlob();
        var b64 = Utilities.base64Encode(blob.getBytes());
        return "data:" + blob.getContentType() + ";base64," + b64;
    } catch (e) {
        Logger.log("⚠️ Could not fetch logo: " + e.toString());
        return null;
    }
}

/**
 * EMAIL BODY HTML (Card Style)
 */
/**
 * EMAIL BODY HTML (Card Style)
 */
function createEmailHtml(name, matric, memberId, date, invoiceNo, receiptNo, downloadUrl) {
    var bgBody = "#f5f5f7";
    var bgCard = "#ffffff";
    var textHeader = "#1d1d1f";
    var textLabel = "#86868b";
    var textValue = "#1d1d1f";
    var accentColor = "#012951";
    var highlightColor = "#f7c525";

    return `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
             @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            body { margin: 0; padding: 0; background-color: ${bgBody}; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            .container { max-width: 600px; margin: 40px auto; background: ${bgCard}; border-radius: 18px; overflow: hidden; }
            .content { padding: 40px; }
            .header { text-align: center; margin-bottom: 30px; }
            .logo { font-size: 24px; font-weight: 700; color: ${textHeader}; }
            .logo span { color: ${highlightColor}; }
            .btn-download { display: inline-block; margin-top: 20px; padding: 12px 24px; background-color: ${accentColor}; color: white !important; text-decoration: none; border-radius: 980px; font-size: 14px; font-weight: 600; }
            
            /* Mobile Responsiveness */
            @media only screen and (max-width: 480px) {
                .container { margin: 0 auto; border-radius: 0; width: 100% !important; }
                .content { padding: 24px !important; }
                .logo { font-size: 20px !important; }
                .amount-large { font-size: 32px !important; }
                .detail-text { font-size: 13px !important; }
            }
        </style>
    </head>
    <body>
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: ${bgBody};">
            <tr>
                <td align="center" style="padding: 20px;">
                    <div class="container">
                        <div class="content">
                            <div class="header">
                                <div class="logo">STEM <span>USAS</span></div>
                                <div style="font-size: 14px; color: ${textLabel}; margin-top: 5px;">Payment Received</div>
                            </div>

                            <div style="text-align: center; color: ${textHeader}; margin-bottom: 30px;">
                                Hi <b>${name}</b>,<br>
                                <span style="font-size: 14px; color: ${textLabel};">Thank you regarding your membership payment.</span>
                            </div>

                            <div style="text-align: center; margin-bottom: 30px;">
                                <div class="amount-large" style="font-size: 42px; font-weight: 700; color: ${textHeader};">${FEE_AMOUNT}</div>
                                <div style="font-size: 13px; color: ${textLabel};">Paid on ${date}</div>
                            </div>

                            <!-- Key Details for Email -->
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; color: ${textLabel}; font-size: 14px;">Date</td>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; text-align: right; font-weight: 600; color: ${textValue}; font-size: 14px;">${date}</td>
                                </tr>
                                <tr>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; color: ${textLabel}; font-size: 14px;">Membership ID</td>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; text-align: right; font-weight: 600; color: ${textValue}; font-size: 14px;">${receiptNo}</td>
                                </tr>
                                <tr>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; color: ${textLabel}; font-size: 14px;">Invoice ID</td>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; text-align: right; font-weight: 600; color: ${textValue}; font-size: 14px;">${invoiceNo}</td>
                                </tr>
                                <tr>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; color: ${textLabel}; font-size: 14px;">Matric No</td>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; text-align: right; font-weight: 600; color: ${textValue}; font-size: 14px;">${matric}</td>
                                </tr>
                                <tr>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; color: ${textLabel}; font-size: 14px;">Item</td>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; text-align: right; font-weight: 600; color: ${textValue}; font-size: 14px; word-break: break-word; max-width: 150px;">STEM Membership</td>
                                </tr>
                                <tr>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; color: ${textLabel}; font-size: 14px;">Status</td>
                                    <td class="detail-text" style="padding: 12px 0; border-bottom: 1px solid #eeeeee; text-align: right; font-weight: 600; color: #34c759; font-size: 14px;">Paid</td>
                                </tr>
                            </table>

                             <!-- Re-Added Working Download Button -->
                             <div style="text-align: center; margin-top: 30px;">
                                <a href="${downloadUrl}" class="btn-download" target="_blank">Download PDF Receipt</a>
                            </div>
                        </div>
                         <div style="background-color: #fafafa; padding: 20px; text-align: center; font-size: 12px; color: ${textLabel};">
                            STEM USAS
                        </div>
                    </div>
                </td>
            </tr>
        </table>
    </body>
    </html>
    `;
}

/**
 * PDF HTML (Table Style)
 * Formal, Invoice-like structure with the grid table.
 */
function createPdfHtml(name, matric, memberId, date, invoiceNo, receiptNo, logoBase64) {
    var bgBody = "#ffffff"; // White background for PDF
    var textHeader = "#1d1d1f";
    var textLabel = "#86868b";
    var textValue = "#1d1d1f";
    var accentColor = "#012951";
    var highlightColor = "#1d1d1f";

    // Logo Logic
    var logoHtml = logoBase64
        ? `<img src="${logoBase64}" style="height: 80px; width: auto; vertical-align: middle;">`
        : `<span class="logo">STEM <span>USAS</span></span>`;

    return `
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            body { margin: 0; padding: 40px; background-color: ${bgBody}; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            .header { margin-bottom: 40px; border-bottom: 2px solid ${accentColor}; padding-bottom: 20px; }
            .logo { font-size: 28px; font-weight: 700; color: ${textHeader}; }
            .logo span { color: ${highlightColor}; }
            .title { font-size: 16px; font-weight: 600; color: ${textLabel}; text-transform: uppercase; float: right; margin-top: 10px; }
            
            .meta-table { width: 100%; margin-bottom: 40px; }
            .meta-table td { padding: 5px 0; vertical-align: top; }
            .meta-label { font-size: 12px; color: ${textLabel}; font-weight: 600; text-transform: uppercase; }
            .meta-value { font-size: 14px; color: ${textValue}; font-weight: 500; }

            .bill-to { margin-bottom: 30px; }
            .bill-label { font-size: 12px; color: ${textLabel}; font-weight: 600; text-transform: uppercase; margin-bottom: 5px; }
            .bill-name { font-size: 18px; font-weight: 700; color: ${textHeader}; }
            
            /* The Grid Table */
            .main-table { width: 100%; border-collapse: separate; border-spacing: 0; border: 1px solid #e5e5e5; border-radius: 8px; overflow: hidden; }
            .main-table th { text-align: left; padding: 12px 16px; background-color: #fafafa; color: ${textLabel}; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #e5e5e5; }
            .main-table td { padding: 16px; border-bottom: 1px solid #e5e5e5; font-size: 14px; color: ${textValue}; }
            .main-table tr:last-child td { border-bottom: none; }
            .total-row td { font-weight: 700; background-color: #fbfffe; }
            .total-val { color: ${accentColor}; }

            .footer { margin-top: 50px; text-align: center; font-size: 12px; color: ${textLabel}; }
        </style>
    </head>
    <body>
        <div class="header">
            ${logoHtml}
            <span class="title">Official Receipt</span>
        </div>

        <table width="100%">
            <tr>
                <td width="60%">
                    <div class="bill-to">
                        <div class="bill-label">Billed To</div>
                        <div class="bill-name">${name}</div>
                        <div class="meta-value">${matric}</div>
                    </div>
                </td>
                <td width="40%" align="right">
                    <table class="meta-table" style="text-align: right;">
                        <tr>
                            <td class="meta-label">Date</td>
                        </tr>
                        <tr>
                             <td class="meta-value" style="padding-bottom: 10px;">${date}</td>
                        </tr>
                        <tr>
                            <td class="meta-label">Membership ID</td>
                        </tr>
                        <tr>
                             <td class="meta-value" style="padding-bottom: 10px;">${receiptNo}</td>
                        </tr>
                        <tr>
                            <td class="meta-label">Invoice</td>
                        </tr>
                         <tr>
                             <td class="meta-value">${invoiceNo}</td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>

        <!-- Tablet Itemization -->
        <table class="main-table">
            <thead>
                <tr>
                    <th width="70%">Description</th>
                    <th width="30%" style="text-align: right;">Amount</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>
                        <b>STEM Membership Registration</b><br>
                        <span style="font-size: 12px; color: #888;">One-time registration fee for STEM Societies USAS</span>
                    </td>
                    <td style="text-align: right; font-weight: 600;">${FEE_AMOUNT}</td>
                </tr>
                <tr class="total-row">
                    <td style="text-align: right;">TOTAL</td>
                    <td style="text-align: right;" class="total-val">${FEE_AMOUNT}</td>
                </tr>
            </tbody>
        </table>

        <div class="footer">
            Computer Generated Receipt • STEM USAS • zis3c
            <div style="margin-top: 20px; font-size: 10px; color: #999; line-height: 1.5; border-top: 1px solid #eee; padding-top: 10px;">
                <b>Disclaimer:</b> Please retain this receipt for your records. Contact STEM Association for any disputes.<br><br>
                <b>Zero Tolerance Policy:</b> Falsifying payment proof or this receipt is a serious offense. Any attempts at fraud will lead to immediate disqualification and a formal report to the Student Affairs Department (HEP) for unethical behavior.
            </div>
        </div>
    </body>
    </html>
    `;
}

/**
 * Generates the Membership ID
 */
function generateMembershipId(sheet, dateObj, currentRowIdx) {
    // 1. Calculate Session
    var year = dateObj.getFullYear();
    var month = dateObj.getMonth(); // 0-11
    var startYear, endYear;

    if (month >= 8) { // September onwards
        startYear = year;
        endYear = year + 1;
    } else {
        startYear = year - 1;
        endYear = year;
    }

    var yyStart = String(startYear).slice(-2);
    var yyEnd = String(endYear).slice(-2);
    var prefix = "STEM(" + yyStart + "/" + yyEnd + ")";

    // 2. Find Max ID with this prefix
    var lastRow = sheet.getLastRow();
    var maxSeq = 0;

    if (lastRow > 1) {
        var ids = sheet.getRange(2, COL_MEMBERSHIP, lastRow - 1, 1).getValues(); // Get all IDs
        for (var i = 0; i < ids.length; i++) {
            if ((i + 2) == currentRowIdx) continue;

            var val = String(ids[i][0]);
            if (val.startsWith(prefix)) {
                var remainder = val.replace(prefix, "");
                var seq = parseInt(remainder, 10);
                if (!isNaN(seq) && seq > maxSeq) maxSeq = seq;
            }
        }
    }

    // 3. Increment
    var newSeq = maxSeq + 1;
    return prefix + String(newSeq).padStart(4, '0');
}

/**
 * FORCE AUTHORIZATION
 * Run this function ONCE to force Google to ask for Email permissions.
 * Click 'Run' > 'forceAuth'
 */
function forceAuth() {
    Logger.log("Checking quota: " + MailApp.getRemainingDailyQuota());
    Logger.log("Checking User: " + Session.getEffectiveUser().getEmail());

    // Just by calling DriveApp here, we force Google to ask for Drive permissions too
    try {
        var root = DriveApp.getRootFolder();
        Logger.log("Drive Access Confirmed: " + root.getName());
    } catch (e) {
        Logger.log("Drive Access Needed");
    }

    setupTrigger(); // Re-run setup to be sure
}

/**
 * TRIGGER SETUP
 * Run this function ONCE manually.
 */
function setupTrigger() {
    var triggers = ScriptApp.getProjectTriggers();
    for (var i = 0; i < triggers.length; i++) {
        if (triggers[i].getHandlerFunction() === "onFormSubmit") {
            ScriptApp.deleteTrigger(triggers[i]);
        }
    }
    ScriptApp.newTrigger("onFormSubmit")
        .forSpreadsheet(SpreadsheetApp.getActive())
        .onFormSubmit()
        .create();

    Logger.log("Trigger set up successfully!");
}

/**
 * MONTHLY STATS GENERATOR
 */
function generateMonthlyStats() {
    var sheet = getTargetSheet();
    if (!sheet) return;

    var today = new Date();
    var firstDayThisMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    var lastMonthDate = new Date(firstDayThisMonth.getTime() - 3600000);

    var monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    var prevMonthName = monthNames[lastMonthDate.getMonth()];
    var prevYear = lastMonthDate.getFullYear();
    var statLabel = "--- STATISTIK " + prevMonthName.toUpperCase() + " " + prevYear + " ---";

    var lastRow = sheet.getLastRow();
    var count = 0;

    if (lastRow > 1) {
        var timestamps = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
        for (var i = 0; i < timestamps.length; i++) {
            var ts = new Date(timestamps[i][0]);
            if (!isNaN(ts.getTime()) && ts.getMonth() === lastMonthDate.getMonth() && ts.getFullYear() === prevYear) {
                count++;
            }
        }
    }

    var rowData = new Array(21).fill("");
    rowData[2] = statLabel; // Col C
    rowData[20] = "Total: " + count; // Col U (Statistic)

    sheet.appendRow(rowData);
    var newRowIdx = sheet.getLastRow();
    sheet.getRange(newRowIdx, 1, 1, 21).setBackground("#eeeeee").setFontWeight("bold");
    Logger.log("Generated Stats for " + prevMonthName + ": " + count);
}
