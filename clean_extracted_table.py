import re

input_path = r"d:\dtcpass.delhi.gov.in\extracted_table.html"
output_path = r"d:\dtcpass.delhi.gov.in\cleaned_extracted_table.html"

with open(input_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace any base64 data in src attributes with [BASE64_IMAGE_DATA_TRUNCATED]
# Pattern matches src="data:image/...base64,...."
cleaned = re.sub(r'src="data:image/[^;]+;base64,[a-zA-Z0-9+/=\s\r\n]+"', 'src="[BASE64_IMAGE_DATA]"', content)

with open(output_path, "w", encoding="utf-8") as f_out:
    f_out.write(cleaned)

print("Successfully cleaned the extracted table and wrote to cleaned_extracted_table.html")
print(f"Cleaned table length: {len(cleaned)} characters.")
