// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: brown; icon-glyph: magic;

// Knowledge Capture - Scriptable Script
// Save shared images/files to iCloud Drive/Knowledge Capture folder
// Add this to Scriptable app and enable "Show in Share Sheet"

const fm = FileManager.iCloud();
const folderName = "Knowledge Capture";

// Get iCloud Drive path (Scriptable's iCloud container maps to iCloud Drive)
const basePath = fm.documentsDirectory();
let folderPath = fm.joinPath(basePath, folderName);

// Create folder if it doesn't exist
if (!fm.fileExists(folderPath)) {
    fm.createDirectory(folderPath, true);
}

// Get shared input from share sheet
let filename = null;
let saved = false;

// Check for images first (most common case)
if (args.images && args.images.length > 0) {
    const image = args.images[0];
    if (image instanceof Image) {
        // Generate timestamp
        const now = new Date();
        const timestamp = now.getFullYear().toString() +
            String(now.getMonth() + 1).padStart(2, '0') +
            String(now.getDate()).padStart(2, '0') + '_' +
            String(now.getHours()).padStart(2, '0') +
            String(now.getMinutes()).padStart(2, '0') +
            String(now.getSeconds()).padStart(2, '0');
        filename = `${timestamp}_screenshot.png`;
        
        // Save image directly using Scriptable's writeImage method
        const filePath = fm.joinPath(folderPath, filename);
        try {
            fm.writeImage(filePath, image);
            saved = true;
        } catch (e) {
            QuickLook.present(`❌ Error saving image: ${e.message || e}`);
            Script.complete();
        }
    }
}
// Check for file URLs (PDFs, documents, etc.)
else if (args.fileURLs && args.fileURLs.length > 0) {
    const fileURL = args.fileURLs[0];
    try {
        // Read the file data
        const fileData = Data.fromURL(fileURL);
        
        // Extract filename from URL or generate one
        const urlString = fileURL.toString();
        const urlParts = urlString.split('/');
        let originalName = urlParts[urlParts.length - 1];
        
        // Generate timestamp
        const now = new Date();
        const timestamp = now.getFullYear().toString() +
            String(now.getMonth() + 1).padStart(2, '0') +
            String(now.getDate()).padStart(2, '0') + '_' +
            String(now.getHours()).padStart(2, '0') +
            String(now.getMinutes()).padStart(2, '0') +
            String(now.getSeconds()).padStart(2, '0');
        
        // Use original name with timestamp, or generate one
        if (originalName && originalName.length > 0) {
            filename = `${timestamp}_${originalName}`;
        } else {
            // Try to get extension from URL or default
            const ext = urlString.includes('.') ? urlString.substring(urlString.lastIndexOf('.')) : '';
            filename = `${timestamp}_file${ext}`;
        }
        
        // Save file
        const filePath = fm.joinPath(folderPath, filename);
        fm.write(filePath, fileData);
        saved = true;
        
    } catch (e) {
        QuickLook.present(`❌ Error reading file: ${e.message || e}`);
        Script.complete();
    }
}

// Validate we saved something
if (!saved || !filename) {
    QuickLook.present("No file or image provided.\n\nMake sure:\n1. You enabled 'Images' in Share Sheet Inputs\n2. You're sharing from Photos or Files app");
    Script.complete();
}

// Show success notification
try {
    const notification = new Notification();
    notification.title = "✅ Saved to Knowledge Capture";
    notification.body = filename;
    notification.sound = "default";
    notification.schedule();
    
    // Brief visual confirmation
    QuickLook.present(`✅ Saved: ${filename}\n\nSyncing to iCloud Drive...`);
} catch (e) {
    QuickLook.present(`✅ Saved: ${filename}`);
}

Script.complete();

