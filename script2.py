import os
import re

template_dir = r'C:\Users\hp\.gemini\antigravity-ide\scratch\ethiopian_school_saas\templates'

changes = {}
table_pattern = re.compile(r'<table[^>]*>')
overflow_pattern = re.compile(r'<div[^>]*class="[^"]*overflow-x-auto[^"]*"[^>]*>\s*<table', re.IGNORECASE)

for root, _, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all <table...
            # But we don't know if they are wrapped. Let's just count tables.
            tables = table_pattern.findall(content)
            if tables:
                # Count overflow wrappers
                overflows = overflow_pattern.findall(content)
                if len(tables) > len(overflows):
                    changes[filepath] = len(tables) - len(overflows)

print(f"Files potentially needing table overflow wrappers: {len(changes)}")
for k, v in changes.items():
    print(f"- {os.path.basename(k)}: {v} tables")
