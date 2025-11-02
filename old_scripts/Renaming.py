import os
import re

# Change this to your target folder, or use '.' for current directory
folder = "."

pattern = re.compile(r"^(\d+)_")  # matches leading digits followed by underscore

for filename in os.listdir(folder):
    match = pattern.match(filename)
    if match:
        number = match.group(1)
        _, ext = os.path.splitext(filename)
        new_name = f"{number}{ext}"
        old_path = os.path.join(folder, filename)
        new_path = os.path.join(folder, new_name)
        
        # Avoid overwriting existing files
        if not os.path.exists(new_path):
            os.rename(old_path, new_path)
            print(f"Renamed: {filename} -> {new_name}")
        else:
            print(f"Skipped (target exists): {new_name}")