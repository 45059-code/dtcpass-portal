import re
import base64
import os
import sys

backup_file = r"C:\Users\45059\OneDrive\Documents\dtcpass.delhi.gov.in\viewEBPass.html"
output_file = r"d:\dtcpass.delhi.gov.in\images\pawan.jpg"

print(f"Python version: {sys.version}")
print(f"Attempting to open: {backup_file}")

try:
    with open(backup_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read(1000) # just read a tiny bit first to test access
        print("Success! Read first 1000 bytes.")
        
    # If successful, read the whole file and extract
    with open(backup_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    print("Searching for base64 image...")
    match = re.search(r'data:image/(jpeg|jpg|png);base64,([a-zA-Z0-9+/=\s\r\n]+)', content)
    if match:
        img_type = match.group(1)
        base64_data = re.sub(r'\s+', '', match.group(2))
        print(f"Found image of type: {img_type}")
        print(f"Base64 data length: {len(base64_data)}")
        
        img_bytes = base64.b64decode(base64_data)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "wb") as f_out:
            f_out.write(img_bytes)
        print(f"Successfully wrote image to {output_file}")
    else:
        print("Could not find base64 image in file.")
except Exception as e:
    print(f"Exception type: {type(e)}")
    print(f"Exception message: {e}")
    import traceback
    traceback.print_exc()
