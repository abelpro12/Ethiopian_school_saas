import os
import re

template_dir = r'C:\Users\hp\.gemini\antigravity-ide\scratch\ethiopian_school_saas\templates'

changes = {}

for root, _, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Simple non-responsive grid replacements
            content = re.sub(r'(?<!sm:)grid-cols-2(?! sm:)', 'grid-cols-1 sm:grid-cols-2', content)
            content = re.sub(r'(?<!sm:|md:|lg:)grid-cols-3(?! sm:| md:| lg:)', 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3', content)
            content = re.sub(r'(?<!sm:|md:|lg:)grid-cols-4(?! sm:| md:| lg:)', 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4', content)
            
            if content != original_content:
                changes[filepath] = True

print(f"Files needing grid updates: {len(changes)}")
