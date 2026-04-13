import os
import replicate
import sys
import requests

MODEL_OWNER = "djratlif"
MODEL_NAME = "captainhandy-comic"

def generate_image(prompt, output_file="output.png"):
    # Wait for training to finish or use the latest version if available
    token = os.environ.get("REPLICATE_API_TOKEN")
    if not token:
        print("Please set REPLICATE_API_TOKEN")
        sys.exit(1)

    print(f"Generating image for prompt: '{prompt}'")
    try:
        # Fetch the trained model version explicitly to avoid 404 errors
        model = replicate.models.get(f"{MODEL_OWNER}/{MODEL_NAME}")
        version = model.latest_version.id

        output = replicate.run(
            f"{MODEL_OWNER}/{MODEL_NAME}:{version}",
            input={
                "prompt": prompt,
                "num_outputs": 1,
                "output_quality": 90,
                "aspect_ratio": "1:1",
                "go_fast": True
            }
        )
        
        # Output is usually a list of URLs
        if isinstance(output, list) and len(output) > 0:
            image_url = output[0]
            print(f"Image generated! Downloading from: {image_url}")
            
            response = requests.get(image_url)
            with open(output_file, 'wb') as f:
                f.write(response.content)
            print(f"Saved successfully to {output_file}")
        else:
            print("Unexpected output format:", output)
            
    except Exception as e:
        print(f"Error generating image: {e}")
        print("Make sure the training job has completely finished before generating!")

if __name__ == "__main__":
    test_prompt = "A simple minimalist black and white line drawing, uncolored, sketch style. CaptainHandy is sitting cross-legged on the floor, intensely playing a video game with a controller. Clean black lines on white background."
    generate_image(test_prompt, "test_comic_panel_2.png")
