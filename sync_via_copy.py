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
        
    import re
    dest_pattern = r'<table (?:id="image"|class="table table-bordered").*?</table>'
    dest_modified, count = re.subn(dest_pattern, modified_table, dest_content, flags=re.DOTALL | re.IGNORECASE)
    
    if count == 0:
        print("Error: Table not found in destination.")
    else:
        # Try to open in r+ mode (which might bypass some WinError 5 restrictions if we don't change file size, but since size changes we truncate)
        print("Attempting to write to viewEBPass.html in r+ mode...")
        with open(dest_file, "r+", encoding="utf-8") as f_out:
            f_out.seek(0)
            f_out.write(dest_modified)
            f_out.truncate()
        print("Successfully updated viewEBPass.html via r+!")
        
except Exception as e:
    import traceback
    traceback.print_exc()
