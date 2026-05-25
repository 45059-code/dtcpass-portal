import json
import re
import base64
import os

transcript_path = r"C:\Users\45059\.gemini\antigravity-ide\brain\a4287472-c72a-4f10-962d-a41c26cf4495\.system_generated\logs\transcript.jsonl"
output_image_path = r"d:\dtcpass.delhi.gov.in\images\pawan.jpg"

try:
    if not os.path.exists(transcript_path):
        print(f"Error: Transcript file not found at {transcript_path}")
    else:
        print(f"Reading transcript: {transcript_path}...")
        # Since it can be a large file, read it line by line
        found = False
        with open(transcript_path, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if 'data:image/jpeg;base64' in line:
                    print(f"Found base64 image string on line {i+1} of transcript!")
                    # Try to parse the JSON line
                    try:
                        data = json.loads(line)
                        content = data.get('content', '')
                    except Exception:
                        content = line
                    
                    # Search for the base64 string
                    match = re.search(r'data:image/(jpeg|jpg|png);base64,([a-zA-Z0-9+/=\s\r\n]+)', content)
                    if match:
                        img_type = match.group(1)
                        # Remove any whitespace/newlines from the base64 string
                        base64_data = re.sub(r'\s+', '', match.group(2))
                        print(f"Found image of type: {img_type}")
                        print(f"Base64 data length: {len(base64_data)}")
                        
                        # Decode and save
                        img_bytes = base64.b64decode(base64_data)
                        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
                        with open(output_image_path, 'wb') as f_out:
                            f_out.write(img_bytes)
                        print(f"Successfully saved Pawan's photo to: {output_image_path}")
                        found = True
                        break
        if not found:
            print("Could not locate any base64 image string in the transcript.")
except Exception as e:
    import traceback
    traceback.print_exc()
