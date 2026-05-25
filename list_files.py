import os
print("Current working directory:", os.getcwd())
paths = [
    r"C:\Users\45059\OneDrive\Documents",
    r"C:\Users\45059\OneDrive\Documents\dtcpass.delhi.gov.in",
    r"d:\dtcpass.delhi.gov.in"
]
for p in paths:
    print(f"\nListing path: {p}")
    try:
        if os.path.exists(p):
            print(f"Exists! Directory contents: {os.listdir(p)[:10]}")
        else:
            print("Does not exist!")
    except Exception as e:
        print("Error:", e)
