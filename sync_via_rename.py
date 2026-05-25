import os
import shutil

modified_path = r"d:\dtcpass.delhi.gov.in\modified_table.html"
dest_file = r"d:\dtcpass.delhi.gov.in\viewEBPass.html"
temp_dest = r"d:\dtcpass.delhi.gov.in\viewEBPass.html.tmp"

try:
    with open(modified_path, "r", encoding="utf-8") as f_mod:
        modified_table = f_mod.read()
        
    with open(dest_file, "r", encoding="utf-8") as f_dest:
        dest_content = f_dest.read()
        
    # Replace the table block
    import re
    dest_pattern = r'<table (?:id="image"|class="table table-bordered").*?</table>'
    dest_modified, count = re.subn(dest_pattern, modified_table, dest_content, flags=re.DOTALL | re.IGNORECASE)
    
    if count == 0:
        print("Error: Table not found in destination.")
    else:
        # Write to a temp file first
        with open(temp_dest, "w", encoding="utf-8") as f_tmp:
            f_tmp.write(dest_modified)
        
        # Now, try to rename/replace
        print("Attempting to replace viewEBPass.html via rename...")
        os.replace(temp_dest, dest_file)
        print("Successfully updated viewEBPass.html!")
        
except Exception as e:
    import traceback
    traceback.print_exc()
    if os.path.exists(temp_dest):
        os.remove(temp_dest)
