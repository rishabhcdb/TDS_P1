from flask import Flask, request, jsonify
import os
import requests
import json
import base64
from datetime import datetime

app = Flask(__name__)

# Load environment variables
MY_SECRET = os.environ.get('MY_SECRET')
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_USERNAME = os.environ.get('GITHUB_USERNAME')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') 


# OpenRouter API endpoint
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
print(f"🔑 Secret: {'✅' if MY_SECRET else '❌'}")
print(f"🔑 OpenRouter: {'✅' if OPENROUTER_API_KEY else '❌'}")
print(f"🔑 GitHub Token: {'✅' if GITHUB_TOKEN else '❌'}")
print(f"🔑 GitHub User: {GITHUB_USERNAME}")
print(f"🔑 Gemini: {'✅' if GEMINI_API_KEY else '❌'}")  # ← Add this

@app.route('/', methods=['GET'])
def home():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "message": "LLM App Builder API is live!",
        "endpoints": ["/build-app"]
    })


@app.route('/build-app', methods=['POST'])
def build_app():
    """
    Main endpoint that receives build requests from instructors.
    This handles both Round 1 (initial build) and Round 2 (revisions).
    """
    try:
        # Get JSON data from request
        data = request.json
        
        # STEP 1: Verify secret
        if data.get('secret') != MY_SECRET:
            return jsonify({"error": "Invalid secret"}), 401
        
        print(f"✅ Secret verified for task: {data.get('task')}")
        
        # STEP 2: Extract request data
        email = data.get('email')
        task = data.get('task')
        round_num = data.get('round', 1)
        nonce = data.get('nonce')
        brief = data.get('brief')
        checks = data.get('checks', [])
        evaluation_url = data.get('evaluation_url')
        attachments = data.get('attachments', [])
        
        print(f"📝 Building app for: {task} (Round {round_num})")
        
        # STEP 3: Generate code using LLM
        print("🤖 Calling LLM to generate code...")
        generated_code = generate_code_with_llm(brief, attachments, checks, task)
        
        
        if not generated_code:
            return jsonify({"error": "Failed to generate code"}), 500
        
        # STEP 4: Create GitHub repository
        print("📦 Creating GitHub repository...")
        repo_url, commit_sha = create_github_repo(task, generated_code, brief, round_num)
        
        if not repo_url:
            return jsonify({"error": "Failed to create GitHub repo"}), 500
        
        # STEP 5: Enable GitHub Pages
        print("🌐 Enabling GitHub Pages...")
        pages_url = enable_github_pages(task)


        # # Replace placeholders in README
        # if generated_code and "readme" in generated_code:
        #     generated_code["readme"] = (
        #         generated_code["readme"]
        #         .replace("[REPO_URL]", repo_url)
        #         .replace("[LIVE_DEMO_URL]", pages_url)
        #     )
        
        if not pages_url:
            return jsonify({"error": "Failed to enable GitHub Pages"}), 500
        
        # STEP 6: Notify evaluation URL
        print("📤 Notifying evaluation URL...")
        notification_success = notify_evaluation_url(
            evaluation_url, email, task, round_num, nonce, 
            repo_url, commit_sha, pages_url
        )
        
        if not notification_success:
            print("⚠️ Warning: Failed to notify evaluation URL (will retry)")
        
        print(f"✅ Successfully completed task: {task}")
        
        # Return success response
        return jsonify({
            "message": "App built and deployed successfully",
            "task": task,
            "round": round_num,
            "repo_url": repo_url,
            "pages_url": pages_url,
            "commit_sha": commit_sha
        }), 200
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


def generate_code_with_llm(brief, attachments, checks, task):
    """Enhanced version with better CSV handling and streamlined prompt"""
    
    # Decode attachments if present
    attachment_info = ""
    attachment_urls = {}
    
    if attachments:
        attachment_info = "\n\nATTACHMENTS:\n"
        for att in attachments:
            attachment_info += f"- {att['name']}: Use data URL directly in fetch()\n"
            attachment_urls[att['name']] = att['url']
    
    # Special instructions for CSV files
    csv_instructions = ""
    has_csv = any('csv' in att['name'].lower() for att in attachments)
    
    if has_csv:
        csv_instructions = """
CSV HANDLING (CRITICAL):
- Include: <script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>
- Parse: Papa.parse(csvText, {header: true, dynamicTyping: true, skipEmptyLines: true, delimitersToGuess: [',', '\t', '|']})
- NEVER assume column names - use actual headers from parsed data
- Strip whitespace from headers: Object.keys(parsed.data[0]).map(k => k.trim())
- Calculate sums properly: rows.reduce((sum, row) => sum + (parseFloat(row[colName]) || 0), 0)
- Console.log the parsed data to verify
- Handle missing/null values with || 0
"""
    
    try:
        prompt = f"""Create a complete, working single-page HTML application.
TASK: {brief}
{attachment_info}
{csv_instructions}
EVALUATION CHECKS (MUST PASS):
{chr(10).join(f"- {check}" for check in checks)}
TECHNICAL SPECS:
- ONE HTML file with inline CSS/JS
- Bootstrap 5: https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/css/bootstrap.min.css
- For data URLs: fetch('{list(attachment_urls.values())[0] if attachment_urls else ""}').then(r => r.text())
- Match ALL element IDs/classes in checks exactly
- Professional UI, no placeholders
- All functionality must work on first load
CRITICAL: Return ONLY the HTML. Start with <!DOCTYPE html>, end with </html>. No markdown blocks."""

        print("🤖 Calling Gemini API...")
        
        GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.2,  # Even lower for consistency
                "maxOutputTokens": 8000,
            }
        }
        
        response = requests.post(GEMINI_URL, json=payload, timeout=120)
        
        if response.status_code != 200:
            print(f"❌ Gemini Error: {response.text}")
            return None
        
        result = response.json()
        
        # Extract generated code
        if 'candidates' not in result or not result['candidates']:
            print("❌ No candidates in response")
            return None
        
        llm_response = result['candidates'][0]['content']['parts'][0]['text']
        
        print(f"✅ Generated code ({len(llm_response)} chars)")
        
        # Clean markdown artifacts
        html_code = llm_response.strip()
        html_code = html_code.replace("```html", "").replace("```", "")
        
        # Extract HTML if wrapped in other text
        if "<!DOCTYPE" in html_code:
            start = html_code.index("<!DOCTYPE")
            html_code = html_code[start:]
        elif "<html" in html_code:
            start = html_code.index("<html")
            html_code = html_code[start:]
        
        if "</html>" in html_code:
            end = html_code.rindex("</html>") + 7
            html_code = html_code[:end]
        
        html_code = html_code.strip()
        
        # Validate
        if not ("<!DOCTYPE" in html_code or "<html" in html_code):
            print("❌ Invalid HTML generated")
            print(f"Preview: {html_code[:300]}")
            return None
        
        # Generate README
        readme_prompt = f"""Generate a professional README.md for a GitHub project with these details:
**Project Name:** {task}
**Purpose:** {brief}
**Requirements to highlight:**
{chr(10).join(f'- {check}' for check in checks)}
Create a README with these sections:
1. **Title** - Short, descriptive project name
2. **Overview** - 2-3 sentences explaining what it does
3. **Features** - Bullet list of key capabilities based on the requirements
5. **How to Use** - Step-by-step user instructions
6. **Technology Stack** - List all libraries/frameworks used
7. **Project Structure** - Show the file tree
8. **Local Development** - Clone and run using git clone 
9. **License** - Mention MIT License
CRITICAL RULES:
- Use actual URLs, not placeholders like [GitHub Pages URL]
- Be specific about what the app does based on the brief
- Keep it professional - no "auto-generated" footers
- Use markdown formatting properly
- Length: 150-250 words
Return the markdown content directly without wrapping it in triple backticks or code fences."""

        readme_payload = {
            "contents": [{"parts": [{"text": readme_prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
        }
        
        readme_response = requests.post(GEMINI_URL, json=readme_payload, timeout=60)
        readme_result = readme_response.json()
        
        readme_text = readme_result["candidates"][0]["content"]["parts"][0]["text"].strip()
        print("✅ README generated")
        
        return {
            "html": html_code,
            "readme": readme_text
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# ===== ROUND 2: Append Enhancement Section =====

def generate_round2_readme_update(old_readme, brief, checks):
    """Generate prompt for updating README with Round 2 changes"""
    
    prompt = f"""You have an existing README.md. Append a "Round 2 Enhancement" section at the end.
**Existing README:**
```markdown
{old_readme}
```
**New Enhancement Brief:** {brief}
**New Requirements:**
{chr(10).join(f'- {check}' for check in checks)}
Create a new section with:
1. **## Round 2 Enhancement** header
2. **Updated date:** {datetime.now().strftime('%Y-%m-%d')}
3. **### New Feature** - Describe what was added based on the brief (be specific, not generic)
4. **### Implementation Details** - Bullet points explaining:
   - What new elements/IDs were added
   - How it integrates with existing functionality
   - Any new user-facing behavior
CRITICAL RULES:
- Be SPECIFIC about what changed, not vague like "Updated with new functionality"
- Mention actual HTML IDs, functions, or features from the brief
- Keep all Round 1 content unchanged
- Return ONLY the new section to append, not the full README
Return format:
```markdown
---
## Round 2 Enhancement
[your content here]
```
"""
    return prompt

        
    #     print(f"✅ Validation passed ({len(html_code)} chars)")
        
    #     return {
    #         "html": html_code,
    #         "readme": readme
    #     }
        
    # except Exception as e:
    #     print(f"❌ Error: {str(e)}")
    #     import traceback
    #     traceback.print_exc()
    #     return None

def extract_section(text, start_marker, end_marker):
    """Helper function to extract sections from LLM response"""
    try:
        start_idx = text.find(start_marker)
        if start_idx == -1:
            return None
        
        start_idx += len(start_marker)
        
        if end_marker:
            end_idx = text.find(end_marker, start_idx)
            if end_idx == -1:
                return text[start_idx:].strip()
            return text[start_idx:end_idx].strip()
        else:
            return text[start_idx:].strip()
    except:
        return None


def create_github_repo(task_name, generated_code, brief, round_num):
    """
    Creates a GitHub repository and pushes the generated code.
    
    Args:
        task_name: Unique name for the repo (e.g., "calculator-abc123")
        generated_code: Dictionary with 'html' and 'readme'
        brief: Description for the repo
        round_num: Round number (1 or 2)
    
    Returns:
        Tuple of (repo_url, commit_sha)
    """
    try:
        # Sanitize repo name (GitHub doesn't allow certain characters)
        repo_name = task_name.replace(' ', '-').lower()
        
        # Check if repo exists (for Round 2 updates)
        if round_num == 2:
            # For Round 2, we update existing repo
            return update_github_repo(repo_name, generated_code, brief)
        
        # STEP 1: Create the repository
        create_repo_url = "https://api.github.com/user/repos"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        repo_data = {
            "name": repo_name,
            "description": brief[:100],  # Max 100 chars for description
            "private": False,  # Must be public for GitHub Pages
            "auto_init": False
        }
        
        response = requests.post(create_repo_url, headers=headers, json=repo_data)
        
        if response.status_code == 422:
            # Repo already exists, delete and recreate
            print(f"⚠️ Repo {repo_name} exists, deleting...")
            delete_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}"
            requests.delete(delete_url, headers=headers)
            # Wait a bit and try again
            import time
            time.sleep(2)
            response = requests.post(create_repo_url, headers=headers, json=repo_data)
        
        response.raise_for_status()
        repo_info = response.json()
        repo_url = repo_info['html_url']
        
        print(f"✅ Created repo: {repo_url}")
        
        # STEP 2: Create files in the repository
        files_to_create = {
            "index.html": generated_code['html'],
            "README.md": generated_code['readme'],
            "LICENSE": get_mit_license()
        }
        
        commit_sha = None
        
        for filename, content in files_to_create.items():
            file_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{filename}"
            
            file_data = {
                "message": f"Add {filename}",
                "content": base64.b64encode(content.encode()).decode()
            }
            
            response = requests.put(file_url, headers=headers, json=file_data)
            response.raise_for_status()
            
            # Get commit SHA from the last file
            commit_sha = response.json()['commit']['sha']
            
            print(f"✅ Added {filename}")
        
        return repo_url, commit_sha
        
    except Exception as e:
        print(f"❌ GitHub Error: {str(e)}")
        return None, None


def update_github_repo(repo_name, generated_code, brief):
    """Updates existing repo for Round 2"""
    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Get existing README
        get_readme_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/README.md"
        readme_response = requests.get(get_readme_url, headers=headers)
        
        if readme_response.status_code == 200:
            old_readme = base64.b64decode(
                readme_response.json()['content']
            ).decode()
            
            # Append only the brief, not the full generated README
            generated_code['readme'] = old_readme + f"""
---
## Round 2 Enhancement
**Updated:** {datetime.now().strftime('%Y-%m-%d')}
### New Feature
{brief}
### Implementation
- Updated with new functionality
- All Round 1 features remain intact
"""
        
        # Update files
        files_to_update = {
            "index.html": generated_code['html'],
            "README.md": generated_code['readme']
        }
        
        commit_sha = None
        
        for filename, content in files_to_update.items():
            get_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{filename}"
            response = requests.get(get_url, headers=headers)
            
            if response.status_code == 200:
                current_sha = response.json()['sha']
                
                file_data = {
                    "message": f"Round 2: Update {filename}",
                    "content": base64.b64encode(content.encode()).decode(),
                    "sha": current_sha
                }
                
                response = requests.put(get_url, headers=headers, json=file_data)
                response.raise_for_status()
                commit_sha = response.json()['commit']['sha']
                
                print(f"✅ Updated {filename}")
        
        repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
        return repo_url, commit_sha
        
    except Exception as e:
        print(f"❌ Update Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, None


def enable_github_pages(repo_name):
    """
    Enables GitHub Pages for the repository.
    
    Returns:
        The GitHub Pages URL
    """
    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        pages_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/pages"
        
        pages_data = {
            "source": {
                "branch": "main",
                "path": "/"
            }
        }
        
        response = requests.post(pages_url, headers=headers, json=pages_data)
        
        # 201 = created, 409 = already exists (both are OK)
        if response.status_code in [201, 409]:
            pages_site_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
            print(f"✅ GitHub Pages enabled: {pages_site_url}")
            return pages_site_url
        else:
            print(f"⚠️ Pages status: {response.status_code}")
            # Return the expected URL anyway
            return f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
            
    except Exception as e:
        print(f"❌ Pages Error: {str(e)}")
        # Return expected URL even if API call failed
        return f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"


def notify_evaluation_url(evaluation_url, email, task, round_num, nonce, repo_url, commit_sha, pages_url):
    """
    Notifies the instructors' evaluation URL with repo details.
    Implements retry logic with exponential backoff.
    """
    notification_data = {
        "email": email,
        "task": task,
        "round": round_num,
        "nonce": nonce,
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "pages_url": pages_url
    }
    
    max_retries = 5
    delay = 1  # Start with 1 second
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                evaluation_url,
                json=notification_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"✅ Notified evaluation URL successfully")
                return True
            else:
                print(f"⚠️ Evaluation URL returned {response.status_code}, retrying...")
                
        except Exception as e:
            print(f"⚠️ Notification attempt {attempt + 1} failed: {str(e)}")
        
        if attempt < max_retries - 1:
            import time
            time.sleep(delay)
            delay *= 2  # Exponential backoff: 1, 2, 4, 8 seconds
    
    print("❌ Failed to notify evaluation URL after all retries")
    return False



@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "alive"}), 200

def get_mit_license():
    """Returns MIT License text"""
    current_year = datetime.now().year
    return f"""MIT License
Copyright (c) {current_year} {GITHUB_USERNAME}
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


if __name__ == '__main__':
    # Check if required environment variables are set
    if not OPENROUTER_API_KEY:
        print("⚠️ WARNING: OPENROUTER_API_KEY not set!")
    if not GITHUB_TOKEN:
        print("⚠️ WARNING: GITHUB_TOKEN not set!")
    
    print("🚀 Starting Flask app...")
    app.run(host='0.0.0.0', port=7860, debug=True)