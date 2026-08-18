import os
import re

template_dir = r'C:\Users\hp\.gemini\antigravity-ide\scratch\ethiopian_school_saas\templates'

header_patterns = [
    (re.compile(r'<div class="mb-6 flex items-center justify-between">'), r'<div class="mb-6 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">'),
    (re.compile(r'<div class="mb-8 flex justify-between items-center">'), r'<div class="mb-8 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">'),
    (re.compile(r'<div class="flex items-center justify-between mb-4">'), r'<div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-4">'),
    (re.compile(r'<div class="flex items-center justify-between mb-6">'), r'<div class="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-6">'),
]

files_modified = 0

for root, _, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Apply all header patterns
            for pattern, replacement in header_patterns:
                content = pattern.sub(replacement, content)
            
            if content != original_content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Fixed headers in {file}")
                files_modified += 1

print(f"\nSuccessfully modified {files_modified} templates to fix header responsiveness!")

