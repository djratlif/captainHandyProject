import os
import sys
import json
import requests
import replicate
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import time
from datetime import datetime

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

def get_random_idea():
    print("🎲 Inventing a random daily adventure...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a creative writer. Output a single short sentence describing a unique, random, funny, and wholesome daily situation for a kid superhero named CaptainHandy."}
        ],
        temperature=0.9
    )
    idea = response.choices[0].message.content.strip()
    print(f"💡 Idea: {idea}")
    return idea

def generate_story(idea: str):
    """Uses OpenAI to create a 4-panel comic script based on the idea."""
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
    
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Idea: {idea}"}
        ],
        temperature=0.7
    )
    
    try:
        data = json.loads(response.choices[0].message.content)
        return data.get("panels", [])
    except Exception as e:
        print("Error parsing OpenAI response:", e)
        return []

def generate_panel_image(prompt: str, filename: str, speech_text: str = ""):
    """Uses Replicate custom LoRA to generate the B&W line art panel with robust retry logic."""
    full_prompt = f"A simple minimalist black and white line drawing, uncolored, sketch style. CaptainHandy is {prompt}. Clean black lines on white background."
    if speech_text:
        full_prompt += f' A white comic speech bubble with the text "{speech_text}".'
        
    for attempt in range(5):
        try:
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
                resp = requests.get(output[0])
                with open(filename, 'wb') as f:
                    f.write(resp.content)
                return True
                
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "throttled" in err_str.lower():
                print(f"   [API rate limit hit. Waiting 15 seconds to retry...]")
                time.sleep(15)
                continue
            else:
                print(f"Error generating image: {e}")
                return False
                
    return False

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current_line = [], []
    for word in words:
        test_line = ' '.join(current_line + [word])
        if draw.textlength(test_line, font=font) <= max_width:
            current_line.append(word)
        else:
            if current_line: lines.append(' '.join(current_line))
            current_line = [word]
    if current_line: lines.append(' '.join(current_line))
    return lines

def assemble_comic(panels_data, image_files, output_filename="daily_auto_comic.png"):
    print("📖 Assembling final comic...")
    CANVAS_WIDTH, CANVAS_HEIGHT, MARGIN, PANEL_SIZE, TEXT_AREA_HEIGHT = 2000, 2200, 50, 900, 150
    try: font = ImageFont.truetype("Arial", 40)
    except IOError: font = ImageFont.load_default()
         
    canvas = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), 'white')
    draw = ImageDraw.Draw(canvas)
    draw.text((MARGIN, MARGIN), f"CaptainHandy Daily - {datetime.now().strftime('%B %d, %Y')}", fill="black", font=font)
    
    positions = [
        (MARGIN, MARGIN + 100), (MARGIN * 2 + PANEL_SIZE, MARGIN + 100),
        (MARGIN, MARGIN * 3 + PANEL_SIZE + TEXT_AREA_HEIGHT + 100),
        (MARGIN * 2 + PANEL_SIZE, MARGIN * 3 + PANEL_SIZE + TEXT_AREA_HEIGHT + 100)
    ]
    
    for idx, (img_file, pos) in enumerate(zip(image_files, positions)):
        img = Image.open(img_file).resize((PANEL_SIZE, PANEL_SIZE), Image.Resampling.LANCZOS)
        canvas.paste(img, pos)
        draw.rectangle([pos[0], pos[1], pos[0]+PANEL_SIZE, pos[1]+PANEL_SIZE], outline="black", width=5)
        
        caption = panels_data[idx].get("caption", "")
        wrapped_lines = wrap_text(draw, caption, font, PANEL_SIZE)
        for i, line in enumerate(wrapped_lines):
            draw.text((pos[0], pos[1] + PANEL_SIZE + 20 + (i * 45)), line, fill="black", font=font)
            
    canvas.save(output_filename)
    print(f"🎉 Comic saved as {output_filename}!")

def main():
    print("--- CaptainHandy Daily Auto Generator ---")
    idea = get_random_idea()
    
    panels = generate_story(idea)
    if not panels or len(panels) != 4:
        print("Failed to structure story.")
        sys.exit(1)
        
    image_files = []
    for i, panel in enumerate(panels):
        filename = f"auto_panel_{i+1}.png"
        print(f"🎨 Generating Panel {i+1}: {panel['speech_text']}")
        if generate_panel_image(panel['image_prompt'], filename, panel.get('speech_text', '')):
            image_files.append(filename)
        else:
            print("Failed to generate image. Aborting.")
            sys.exit(1)
            
    timestamp = datetime.now().strftime("%Y_%m_%d")
    assemble_comic(panels, image_files, f"captainhandy_comic_{timestamp}.png")
    
if __name__ == "__main__":
    main()
