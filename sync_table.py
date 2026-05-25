import re
import os

onedrive_path = r"C:\Users\45059\OneDrive\Documents\dtcpass.delhi.gov.in\viewEBPass.html"
destination_files = [
    r"d:\dtcpass.delhi.gov.in\viewEBPass.html",
    r"d:\dtcpass.delhi.gov.in\viewEPass.html",
    r"d:\dtcpass.delhi.gov.in\viewEPass"
]

try:
    if not os.path.exists(onedrive_path):
        print(f"Error: Original file not found at {onedrive_path}")
        exit(1)
        
    print(f"Reading original table from {onedrive_path}...")
    with open(onedrive_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    pattern = r'<table class="table table-bordered".*?</table>'
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if not match:
        print("Error: Could not locate table block in original file.")
        exit(1)
        
    table_html = match.group(0)
    print(f"Original table length: {len(table_html)} characters.")
    
    # ── Modify table to add IDs for dynamic updating ─────────────────────
    
    # 1. Add id="passPhoto" to the first img tag (Pawan's photo)
    # The original is: <img src="data:image/jpeg;base64,..." height="250px" width="250px" style="opacity: 65%;"/>
    modified_table = re.sub(
        r'<img src="data:image/jpeg;base64,([^"]+)" height="250px" width="250px" style="opacity: 65%;"/>',
        r'<img id="passPhoto" src="data:image/jpeg;base64,\1" height="250px" width="250px" style="opacity: 65%;"/>',
        table_html
    )
    
    # 2. Add id="passName" to the b tag containing "PAWAN KUMAR "
    modified_table = re.sub(
        r'<b>PAWAN KUMAR </b>',
        r'<b id="passName">PAWAN KUMAR </b>',
        modified_table
    )
    
    # 3. Add id="passCategory" to the b tag containing "Student All route AC/Non AC"
    modified_table = re.sub(
        r'<b>Student All route AC/Non AC</b>',
        r'<b id="passCategory">Student All route AC/Non AC</b>',
        modified_table
    )
    
    # 4. Add id="passValidity" to the b tag containing "Valid from 19/05/2026 to 18/10/2026"
    modified_table = re.sub(
        r'<b>Valid from 19/05/2026 to 18/10/2026</b>',
        r'<b id="passValidity">Valid from 19/05/2026 to 18/10/2026</b>',
        modified_table
    )
    
    # 5. Replace static QR code img tag with a dynamic div container with id="passQrCode"
    # Tag 3: <img src="data:image/jpg;base64,iVBORw0KGgoAAAANSUhEUgAAASwAAAEsCAYAA..." height="80px" width="80px"/>
    modified_table = re.sub(
        r'<img src="data:image/jpg;base64,iVBORw0KGgoAAAANSUhEUgAAASwAAAEsCAYAA[^"]+" height="80px" width="80px"/>',
        r'<div id="passQrCode" style="width: 80px; height: 80px; display: inline-block; background-color: #fff; vertical-align: middle;"></div>',
        modified_table
    )
    
    print(f"Modified table length: {len(modified_table)} characters.")
    
    # ── Update destination files ──────────────────────────────────────────
    import stat
    for dest in destination_files:
        if not os.path.exists(dest):
            print(f"Warning: Destination file {dest} not found, skipping.")
            continue
            
        print(f"Syncing table to destination: {dest}...")
        with open(dest, "r", encoding="utf-8") as f_dest:
            dest_content = f_dest.read()
            
        # Replace the table block in the destination file
        # In destination, it starts either with <table id="image"... or <table class="table...
        dest_pattern = r'<table (?:id="image"|class="table table-bordered").*?</table>'
        dest_modified, count = re.subn(dest_pattern, modified_table, dest_content, flags=re.DOTALL | re.IGNORECASE)
        
        if count == 0:
            print(f"Warning: Could not find any table to replace in {dest}.")
        else:
            # Clear read-only attribute if set
            os.chmod(dest, stat.S_IWRITE)
            with open(dest, "w", encoding="utf-8") as f_out:
                f_out.write(dest_modified)
            print(f"Successfully updated {dest}")
            
except Exception as e:
    import traceback
    traceback.print_exc()
