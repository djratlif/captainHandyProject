import os
import sys
import json
import requests
import replicate
from openai import OpenAI
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import time

# Load environment variables
load_dotenv()

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
REPLICATE_KEY = os.environ.get("REPLICATE_API_TOKEN")

if not OPENAI_KEY or not REPLICATE_KEY:
    print("Error: OPENAI_API_KEY or REPLICATE_API_TOKEN missing in .env")
    sys.exit(1)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_KEY)

# Replicate Model Constants
MODEL_OWNER = "djratlif"
MODEL_NAME = "captainhandy-comic"

def generate_story(idea: str):
    """Uses OpenAI to create a 4-panel comic script based on a generic idea."""
    print("✍️  Brainstorming comic script with ChatGPT...")
    
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
         {"caption": "text...", "image_prompt": "description...", "speech_text": "text..."},
         {"caption": "text...", "image_prompt": "description...", "speech_text": "text..."}
      ]
    }
    """
    
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
    try:
        data = json.loads(script_content)
        return data.get("panels", [])
    except Exception as e:
        print("Error parsing OpenAI response:", e)
        return []

def generate_panel_image(prompt: str, filename: str, speech_text: str = ""):
    """Uses Replicate custom LoRA to generate the B&W line art panel."""
    print(f"🎨 Generating image: '{prompt}'")
    
    full_prompt = f"A simple minimalist black and white line drawing, uncolored, sketch style. CaptainHandy is {prompt}. Clean black lines on white background."
    if speech_text:
        full_prompt += f' A white comic speech bubble with the text "{speech_text}".'
    
    try:
        # Fetch the trained model version explicitly to avoid 404 errors
        model = replicate.models.get(f"{MODEL_OWNER}/{MODEL_NAME}")
        version = model.latest_version.id

        output = replicate.run(
            f"{MODEL_OWNER}/{MODEL_NAME}:{version}",
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
            with open(filename, 'wb') as f:
                f.write(resp.content)
            return True
        else:
            print(f"Unexpected output from Replicate: {output}")
            return False
            
    except Exception as e:
        print(f"Error generating image via Replicate: {e}")
        return False

def wrap_text(draw, text, font, max_width):
    """Helper to wrap text to fit inside the panel width."""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        # get length of test line
        length = draw.textlength(test_line, font=font)
        if length <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def assemble_comic(panels_data, image_files, output_filename="daily_comic.png"):
    """Assembles the 4 images into a 2x2 grid and writes the captions beneath each."""
    print("📖 Assembling final comic...")
    
    # Constants
    CANVAS_WIDTH = 2000
    CANVAS_HEIGHT = 2200
    MARGIN = 50
    PANEL_SIZE = 900
    TEXT_AREA_HEIGHT = 150
    
    # Load default font (or Arial if available)
    try:
         font = ImageFont.truetype("Arial", 40)
    except IOError:
         font = ImageFont.load_default()
         
    canvas = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), 'white')
    draw = ImageDraw.Draw(canvas)
    
    # Title
    draw.text((MARGIN, MARGIN), "The Adventures of CaptainHandy", fill="black", font=font)
    
    # 2x2 Grid setup
    positions = [
        (MARGIN, MARGIN + 100), # Top Left
        (MARGIN * 2 + PANEL_SIZE, MARGIN + 100), # Top Right
        (MARGIN, MARGIN * 3 + PANEL_SIZE + TEXT_AREA_HEIGHT + 100), # Bottom Left
        (MARGIN * 2 + PANEL_SIZE, MARGIN * 3 + PANEL_SIZE + TEXT_AREA_HEIGHT + 100) # Bottom Right
    ]
    
    for idx, (img_file, pos) in enumerate(zip(image_files, positions)):
        # Load and resize image
        img = Image.open(img_file)
        img = img.resize((PANEL_SIZE, PANEL_SIZE), Image.Resampling.LANCZOS)
        
        # Paste Image
        canvas.paste(img, pos)
        
        # Draw Border
        draw.rectangle([pos[0], pos[1], pos[0]+PANEL_SIZE, pos[1]+PANEL_SIZE], outline="black", width=5)
        
        # Draw Caption Text below image
        caption = panels_data[idx].get("caption", "")
        text_y_start = pos[1] + PANEL_SIZE + 20
        wrapped_lines = wrap_text(draw, caption, font, PANEL_SIZE)
        
        for i, line in enumerate(wrapped_lines):
            draw.text((pos[0], text_y_start + (i * 45)), line, fill="black", font=font)
            
    canvas.save(output_filename)
    print(f"🎉 Comic successfully completed and saved as {output_filename}!")

def main():
    print("Welcome to the CaptainHandy Daily Comic Generator!")
    idea = input("Enter a rough idea for today's comic: ")
    if not idea.strip():
        print("Idea cannot be empty. Exiting.")
        sys.exit(1)
        
    # 1. Generate Story
    panels = generate_story(idea)
    if not panels or len(panels) != 4:
        print("Failed to generate exactly 4 panels.")
        sys.exit(1)
        
    print(f"\nCreated Script:")
    for i, p in enumerate(panels):
        print(f"Panel {i+1}: {p['caption']}")
        print(f" Prompt: {p['image_prompt']}\n")
        
    # 2. Generate Images
    image_files = []
    for i, panel in enumerate(panels):
        filename = f"panel_{i+1}.png"
        success = generate_panel_image(panel['image_prompt'], filename, panel.get('speech_text', ''))
        if success:
            image_files.append(filename)
            print("⏳ Sleeping 10 seconds to respect Replicate rate limits...")
            time.sleep(10)
        else:
            print("Failed to generate an image. Aborting.")
            sys.exit(1)
            
    # 3. Assemble Comic
    assemble_comic(panels, image_files)
    
if __name__ == "__main__":
    main()
