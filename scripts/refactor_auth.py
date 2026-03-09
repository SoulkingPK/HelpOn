import os
import re

client_dir = r"d:\HelpOn\client"

for filename in os.listdir(client_dir):
    if not filename.endswith('.html'):
        continue
        
    filepath = os.path.join(client_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    original = content
    
    # Check if the file is index.html or register.html, we skip heavy refactoring for fetch calls 
    # because we just did it manually.
    is_auth_file = filename in ['index.html', 'register.html']
    
    # 1. Replace auth checks based on localStorage
    content = re.sub(r"if\s*\(\s*!localStorage\.getItem\('helpon_token'\)\s*&&\s*!localStorage\.getItem\('helpon_refresh_token'\)\s*\)", "if (!isUserLoggedIn())", content)
    content = re.sub(r"if\s*\(\s*!localStorage\.getItem\('helpon_token'\)\s*\)", "if (!isUserLoggedIn())", content)
    
    # 2. Remove token fetching
    content = re.sub(r"^[ \t]*const\s+token\s*=\s*localStorage\.getItem\('helpon_token'\);\r?\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^[ \t]*let\s+token\s*=\s*localStorage\.getItem\('helpon_token'\);\r?\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^[ \t]*const\s+accessToken\s*=\s*localStorage\.getItem\('helpon_token'\);\r?\n", "", content, flags=re.MULTILINE)
    
    # 3. Remove Authorization header
    content = re.sub(r"^[ \t]*['\"]Authorization['\"]\s*:\s*`Bearer \$\{.*?token.*?\}`\,?\r?\n", "", content, flags=re.MULTILINE)
    
    # 4. Remove local fetchWithAuth definitions since it is in config.js now
    fetch_with_auth_def = re.compile(r"^[ \t]*async function fetchWithAuth\(url, options = \{\}\) \{.*?\n[ \t]*\}\r?\n", re.MULTILINE | re.DOTALL)
    # Be careful, finding the end of the block is hard with regex. We'll do a string replacement for the exact blocks we know if needed, or just let it be (it will override config.js locally, which is bad). Let's use string manipulation if it's there.
    
    # Actually, we can just replace the definition with nothing, by finding the matching braces.
    def remove_local_fetch(text):
        idx = text.find("async function fetchWithAuth(url, options = {}) {")
        if idx == -1:
            return text
        # find matching bracket
        depth = 0
        in_match = False
        end_idx = idx
        for i in range(idx, len(text)):
            if text[i] == '{':
                depth += 1
                in_match = True
            elif text[i] == '}':
                depth -= 1
                if in_match and depth == 0:
                    end_idx = i + 1
                    break
        return text[:idx] + text[end_idx:]
    
    content = remove_local_fetch(content)
    
    # 5. Transform `fetch(` to `fetchWithAuth(` for apiBase calls.
    # Exclude index.html and register.html
    if not is_auth_file:
        content = re.sub(r"fetch\(\s*`\$\{apiBase\}/", "fetchWithAuth(`${apiBase}/", content)
        
    # 6. Transform `const { res, authError } = await fetchWithAuth` to `const res = await fetchWithAuth`
    content = re.sub(r"const\s+\{\s*res,\s*authError\s*\}\s*=\s*await\s+fetchWithAuth", "const res = await fetchWithAuth", content)
    
    # 7. Remove `if (authError) { ... }` simple checks
    # Usually it looks like:
    # if (authError) {
    #     this.showToast('Session expired. Please log in again.', 'warning');
    #     handleAuthFailure();
    #     return;
    # }
    content = re.sub(r"^[ \t]*if\s*\(\s*authError\s*\)\s*\{.*?\r?\n[ \t]*\}\r?\n", "", content, flags=re.MULTILINE | re.DOTALL)

    # Note: `this.showToast` above is multiple lines. The regex might not catch it perfectly if it contains other braces.
    # Let's write a better brace matching remover for `if (authError)`
    def remove_auth_error_checks(text):
        import re
        while True:
            match = re.search(r"if\s*\(\s*authError\s*\)\s*\{", text)
            if not match:
                break
            idx = match.start()
            depth = 0
            in_match = False
            end_idx = idx
            for i in range(idx, len(text)):
                if text[i] == '{':
                    depth += 1
                    in_match = True
                elif text[i] == '}':
                    depth -= 1
                    if in_match and depth == 0:
                        end_idx = i + 1
                        break
            text = text[:idx] + text[end_idx:]
        return text
    
    content = remove_auth_error_checks(content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Refactored {filename}")

print("Done")
