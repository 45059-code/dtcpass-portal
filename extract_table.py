import re
import os

onedrive_path = r"C:\Users\45059\OneDrive\Documents\dtcpass.delhi.gov.in\viewEBPass.html"
output_path = r"d:\dtcpass.delhi.gov.in\extracted_table.html"

try:
    if not os.path.exists(onedrive_path):
        print(f"Error: Original file not found at {onedrive_path}")
    else:
        with open(onedrive_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        # Extract the table starting with <table class="table table-bordered" style="width:100%;border:10px;" background="images/Dtc.jpeg">
        # up to the closing </table>
        pattern = r'<table class="table table-bordered".*?</table>'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            table_html = match.group(0)
            with open(output_path, "w", encoding="utf-8") as f_out:
                f_out.write(table_html)
            print(f"Successfully extracted table HTML to {output_path}")
            print(f"Total length of extracted HTML: {len(table_html)} characters.")
        else:
            print("Could not find the target table in the OneDrive file.")
except Exception as e:
    import traceback
    traceback.print_exc()
