import os
import uuid
import json
import requests
import replicate
from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
from openai import OpenAI
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Cloud Run Stateless Dependencies
try:
    from google.cloud import firestore
    from google.cloud import storage
    CLOUD_MODE = True
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "captainhandy-comics-storage")
    
    # By default, GCP looks for `(default)`. The user named it `default`.
    FIRESTORE_DB_ID = os.environ.get("FIRESTORE_DB_ID", "default")
    db_client = firestore.Client(database=FIRESTORE_DB_ID)
    
    storage_client = storage.Client()
    print("☁️ RUNNING IN GOOGLE CLOUD MODE: Firestore and GCS enabled.")
except Exception as e:
    CLOUD_MODE = False
    print(f"💾 RUNNING IN LOCAL MODE (Cloud credentials missing or unconfigured): {e}")

load_dotenv()

app = Flask(__name__)
# Configurations
app.config['STATIC_FOLDER'] = 'static'
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "captainhandy-super-secret-key-12345")
os.makedirs('static/comics', exist_ok=True)

@app.before_request
def require_login():
    allowed_endpoints = ['login', 'static', 'send_static']
    if request.endpoint not in allowed_endpoints and not session.get('logged_in'):
        return redirect(url_for('login'))

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
REPLICATE_KEY = os.environ.get("REPLICATE_API_TOKEN")

if not OPENAI_KEY or not REPLICATE_KEY:
    print("Error: OPENAI_API_KEY or REPLICATE_API_TOKEN missing in .env")
    exit(1)

client = OpenAI(api_key=OPENAI_KEY)

MODEL_OWNER = "djratlif"
MODEL_NAME = "captainhandy-comic"

# Persistent JSON store for generated panels
DB_PATH = os.path.join('app_data', 'database.json')

def load_db():
    if CLOUD_MODE:
        try:
            docs = db_client.collection('comics').stream()
            db = {}
            for doc in docs:
                db[doc.id] = doc.to_dict()
            return db
        except Exception as e:
            print(f"Error loading from Firestore: {e}")
            return {}
            
    # Local fallback
    if os.path.exists(DB_PATH):
        with open(DB_PATH, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return {}

def save_comic(comic_id, comic_data):
    if CLOUD_MODE:
        try:
            db_client.collection('comics').document(comic_id).set(comic_data)
        except Exception as e:
            print(f"Error saving to Firestore: {e}")
        return
        
    # Local fallback
    comics_db[comic_id] = comic_data
    os.makedirs('app_data', exist_ok=True)
    with open(DB_PATH, 'w') as f:
        json.dump(comics_db, f, indent=2)

comics_db = load_db()

def get_latest_version():
    """Dynamically fetches the latest model version hash"""
    try:
        model = replicate.models.get(f"{MODEL_OWNER}/{MODEL_NAME}")
        return model.latest_version.id
    except:
        return ""

LATEST_VERSION = get_latest_version()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'levi' and password == 'drscribbles95':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/gallery')
def gallery():
    # If in cloud mode, fetch fresh from DB to prevent stale instances
    current_db = load_db() if CLOUD_MODE else comics_db
    return render_template('gallery.html', comics=current_db)

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/api/brainstorm', methods=['POST'])
def brainstorm():
    data = request.json
    idea = data.get('idea', '').strip()
    
    if not idea:
        print("🎲 No idea provided. Generating a random adventure!")
        idea = "Invent a completely unexpected, witty, wholesome daily situation for a kid superhero named CaptainHandy."

    system_prompt = """
    You are a professional comic book writer. You write funny, wholesome, and highly cohesive 4-panel comic strips about a character named "CaptainHandy", a kid superhero drawing.
    You will be given a rough idea. Your job is to convert it into a seamless 4-panel story arc with a clear setup, escalation, and punchline.
    
    For each panel, provide:
    1. 'caption': The text narration to appear below the panel. Keep it extremely short (1-2 sentences).
    2. 'image_prompt': A literal, physical description of exactly what is happening in the drawing for an image generator AI. Describe ONLY what is visible. Don't write abstract concepts.
    3. 'speech_text': A short quote (1-5 words max) spoken by the character to go inside a speech bubble. EVERY SINGLE PANEL MUST HAVE THIS. Do not leave it empty.
    
    Return pure JSON in exactly this format:
    {
      "panels": [
         {"caption": "text...", "image_prompt": "description...", "speech_text": "text..."}
      ]
    }
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Idea: {idea}"}
            ],
            temperature=0.7
        )
        script_content = response.choices[0].message.content
        panels = json.loads(script_content).get("panels", [])
        
        comic_id = str(uuid.uuid4())
        comic_data = {
            "idea": idea,
            "panels": panels
        }
        
        # Only assign memory if local, otherwise let load_db() fetch
        if not CLOUD_MODE:
            comics_db[comic_id] = comic_data
            
        save_comic(comic_id, comic_data)
        
        return jsonify({"comic_id": comic_id, "panels": panels})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate_panel/<comic_id>/<int:panel_idx>', methods=['POST'])
def generate_panel(comic_id, panel_idx):
    current_db = load_db() if CLOUD_MODE else comics_db
    
    if comic_id not in current_db:
        return jsonify({"error": "Comic ID not found"}), 404
        
    panels = current_db[comic_id]["panels"]
    if panel_idx < 0 or panel_idx >= len(panels):
        return jsonify({"error": "Invalid panel index"}), 400
        
    panel = panels[panel_idx]
    image_prompt = panel.get("image_prompt")
    speech_text = panel.get("speech_text", "")
    
    full_prompt = f"A simple minimalist black and white line drawing, uncolored, sketch style. CaptainHandy is {image_prompt}. Clean black lines on white background."
    if speech_text:
        full_prompt += f' A white comic speech bubble with the text "{speech_text}".'

    try:
        if not LATEST_VERSION:
            model_target = f"{MODEL_OWNER}/{MODEL_NAME}"
        else:
            model_target = f"{MODEL_OWNER}/{MODEL_NAME}:{LATEST_VERSION}"
            
        output = replicate.run(
            model_target,
            input={
                "prompt": full_prompt,
                "num_outputs": 1,
                "output_quality": 90,
                "aspect_ratio": "1:1",
                "go_fast": True
            }
        )
        
        if isinstance(output, list) and len(output) > 0:
            image_url = output[0]
            resp = requests.get(image_url)
            filename = f"{comic_id}_{panel_idx}.png"
            
            if CLOUD_MODE:
                try:
                    bucket = storage_client.bucket(GCS_BUCKET_NAME)
                    blob = bucket.blob(filename)
                    blob.upload_from_string(resp.content, content_type='image/png')
                    blob.make_public()
                    final_image_url = blob.public_url
                except Exception as e:
                    print(f"GCS Upload Error: {e}, falling back to local storage")
                    filepath = os.path.join("static", "comics", filename)
                    with open(filepath, 'wb') as f:
                        f.write(resp.content)
                    final_image_url = f"/{filepath}"
            else:
                filepath = os.path.join("static", "comics", filename)
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                final_image_url = f"/{filepath}"
                
            panel["image_url"] = final_image_url
            save_comic(comic_id, current_db[comic_id])
            return jsonify({"success": True, "image_url": final_image_url})
        else:
            return jsonify({"error": "Invalid output from Replicate"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=3000)
