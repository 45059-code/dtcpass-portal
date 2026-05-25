import os
from PIL import Image

output_sig_path = r"d:\dtcpass.delhi.gov.in\images\signature_extracted.png"
output_qr_path = r"d:\dtcpass.delhi.gov.in\images\qr_extracted.png"

try:
    if os.path.exists(output_sig_path):
        with Image.open(output_sig_path) as img:
            print(f"Signature image: format={img.format}, size={img.size}, mode={img.mode}")
    else:
        print("Signature image not found.")
        
    if os.path.exists(output_qr_path):
        with Image.open(output_qr_path) as img:
            print(f"QR code image: format={img.format}, size={img.size}, mode={img.mode}")
    else:
        print("QR code image not found.")
except Exception as e:
    import traceback
    traceback.print_exc()
