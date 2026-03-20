import os
import re

client_dir = r"d:\HelpOn\client"

# Patterns to remove
sw_pattern = re.compile(r'<script>\s*if \("serviceWorker"\s+in\s+navigator\).*?<\/script>', re.DOTALL)
toast_pattern = re.compile(r'\s*// Toast notification function\s+function showToast\(.*?(?=\n\s*(//|\w+\.addEventListener|function |\})|(?=<\/script>))', re.DOTALL)

for filename in os.listdir(client_dir):
    if not filename.endswith('.html'):
        continue
    
    filepath = os.path.join(client_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    original = content
    
    # Inject utils.js after config.js
    if '<script src="js/utils.js"></script>' not in content and '<script src="config.js"></script>' in content:
        content = content.replace('<script src="config.js"></script>', '<script src="config.js"></script>\n    <script src="js/utils.js"></script>')
        
    # Remove service worker blocks
    content = sw_pattern.sub('', content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filename}")
