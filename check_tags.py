import re

input_path = r"d:\dtcpass.delhi.gov.in\extracted_table.html"

with open(input_path, "r", encoding="utf-8") as f:
    content = f.read()

# Let's find all img tags and print them but with base64 truncated to 20 chars
img_tags = re.findall(r'<img[^>]+>', content)
for i, tag in enumerate(img_tags):
    # Truncate any base64 data
    truncated_tag = re.sub(r'src="data:image/[^;]+;base64,([a-zA-Z0-9+/=]+)"', lambda m: f'src="data:image/...base64({len(m.group(1))})"', tag)
    print(f"Tag {i+1}: {truncated_tag}")
