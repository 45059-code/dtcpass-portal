import re
import base64
import os

onedrive_path = r"C:\Users\45059\OneDrive\Documents\dtcpass.delhi.gov.in\viewEBPass.html"
output_sig_path = r"d:\dtcpass.delhi.gov.in\images\signature_extracted.png"
output_qr_path = r"d:\dtcpass.delhi.gov.in\images\qr_extracted.png"

if not os.path.exists(onedrive_path):
    print(f"Error: Original file not found at {onedrive_path}")
else:
    with open(onedrive_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    
    # Let's find the base64 strings in the file.
    # We can scan the file line-by-line.
    for idx, line in enumerate(lines):
        line_num = idx + 1
        if "data:image/" in line:
            print(f"Line {line_num} contains data:image/")
            match = re.search(r'data:image/([^;]+);base64,([a-zA-Z0-9+/=\s\r\n]+)', line)
            if match:
                img_ext = match.group(1)
                base64_data = re.sub(r'\s+', '', match.group(2))
                print(f"  Extension: {img_ext}, Length: {len(base64_data)}")
                
                # Check line numbers to know which is which:
                # Line 4503 is Pawan's photo
                # Line 4531 is the signature
                # Line 4534 is the QR code
                if line_num == 4531 or (line_num > 4520 and line_num < 4533):
                    img_bytes = base64.b64decode(base64_data)
                    with open(output_sig_path, "wb") as f_sig:
                        f_sig.write(img_bytes)
                    print(f"  Saved signature to {output_sig_path}")
                elif line_num == 4534 or (line_num >= 4533 and line_num < 4540):
                    img_bytes = base64.b64decode(base64_data)
                    with open(output_qr_path, "wb") as f_qr:
                        f_qr.write(img_bytes)
                    print(f"  Saved QR code to {output_qr_path}")
