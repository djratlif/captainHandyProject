import os
import zipfile
import replicate
import sys
import requests

# Constants
TRAIN_DIR = "trainImgs"
ZIP_FILE = "trainImgs.zip"
TRIGGER_WORD = "CaptainHandy"
MODEL_NAME = "captainhandy-comic"

def create_zip():
    print(f"Creating zip file from {TRAIN_DIR}...")
    if not os.path.exists(TRAIN_DIR):
        print(f"Error: Directory '{TRAIN_DIR}' not found.")
        sys.exit(1)
        
    with zipfile.ZipFile(ZIP_FILE, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(TRAIN_DIR):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, arcname=file)
    print(f"Created {ZIP_FILE} successfully.")

def get_replicate_username(token):
    headers = {"Authorization": f"Token {token}"}
    r = requests.get("https://api.replicate.com/v1/account", headers=headers)
    if r.status_code == 200:
        return r.json().get("username")
    else:
        print("Failed to get account details:", r.text)
        sys.exit(1)

def ensure_model_exists(token, username):
    print(f"Ensuring model {username}/{MODEL_NAME} exists...")
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    data = {
        "owner": username,
        "name": MODEL_NAME,
        "visibility": "private",
        "hardware": "gpu-t4"
    }
    r = requests.post("https://api.replicate.com/v1/models", headers=headers, json=data)
    if r.status_code == 201:
        print("Model created successfully.")
    elif r.status_code == 409 or (r.status_code == 422 and "already exists" in r.text.lower()):
        print("Model already exists.")
    else:
        print(f"Warning/Error creating model: {r.status_code} - {r.text}")

def train_lora(username):
    try:
        print("Uploading and initiating training on Replicate...")
        print(f"Using trigger word: {TRIGGER_WORD}")
        
        training = replicate.trainings.create(
            model="ostris/flux-dev-lora-trainer",
            version="26dce37af90b9d997eeb970d92e47de3064d46c300504ae376c75bef6a9022d2",
            input={
                "input_images": open(ZIP_FILE, "rb"),
                "trigger_word": TRIGGER_WORD,
                "steps": 600,  # 600 is good for 25 images
                "learning_rate": 4e-4,
                "batch_size": 1,
                "resolution": "512,768,1024"
            },
            destination=f"{username}/{MODEL_NAME}"
        )
        
        print(f"\nTraining started successfully! Training ID: {training.id}")
        print(f"You can monitor the status on your Replicate dashboard or at: {training.urls['get']}")
        
    except replicate.exceptions.ReplicateError as e:
        print(f"\nReplicate API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    token = os.environ.get("REPLICATE_API_TOKEN")
    if not token:
        print("Please set your REPLICATE_API_TOKEN environment variable first.")
        sys.exit(1)
        
    create_zip()
    username = get_replicate_username(token)
    print(f"Authenticated as: {username}")
    ensure_model_exists(token, username)
    train_lora(username)
