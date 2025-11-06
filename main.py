#!/usr/bin/env python3
"""
Financial Carousel Generator
Automates the creation of Instagram/TikTok carousel slides for the "Financial Myth-Buster" channel.
"""

import os
import json
import textwrap
import time
import base64
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv
import requests
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont

# ============================
# CONSTANTS
# ============================
FONT_BOLD_PATH = "fonts/Montserrat-Bold.ttf"
FONT_REGULAR_PATH = "fonts/Montserrat-Regular.ttf"
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1920  # TikTok/Reels format
OUTPUT_DIR = "output"

# Google Sheets API Scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


# ============================
# SETUP FUNCTIONS
# ============================

def setup_gemini():
    """Configure and return the Gemini API model."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        raise ValueError("GEMINI_API_KEY not set in .env file. Please add your API key.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-pro')
    print("[INFO] Gemini API configured successfully.")
    return model


def setup_gspread():
    """Authenticate with Google Sheets and return the worksheet."""
    if not os.path.exists("credentials.json"):
        raise FileNotFoundError(
            "credentials.json not found. Please download your service account key "
            "from Google Cloud Console and place it in this directory."
        )

    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    worksheet_name = os.getenv("WORKSHEET_NAME", "PostedTopics")

    if not sheet_id or sheet_id == "YOUR_GOOGLE_SHEET_ID":
        raise ValueError("GOOGLE_SHEET_ID not set in .env file. Please add your sheet ID.")

    spreadsheet = client.open_by_key(sheet_id)

    # Try to get the worksheet, or create it if it doesn't exist
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"[INFO] Worksheet '{worksheet_name}' not found. Creating it...")
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=100, cols=5)
        worksheet.append_row(["Topic", "Date Posted", "Slides Count"])

    # Check if the sheet has a header, if not add one
    if worksheet.row_values(1) == []:
        worksheet.append_row(["Topic", "Date Posted", "Slides Count"])
        print("[INFO] Added header row to worksheet.")

    print(f"[INFO] Connected to Google Sheet: {worksheet_name}")
    return worksheet


def get_existing_topics(sheet):
    """Read all existing topics from column A (after the header)."""
    try:
        all_values = sheet.col_values(1)  # Get all values from column A
        if len(all_values) <= 1:
            print("[INFO] No existing topics found.")
            return []

        topics = all_values[1:]  # Skip the header row
        print(f"[INFO] Found {len(topics)} existing topics.")
        return topics
    except Exception as e:
        print(f"[WARNING] Could not read existing topics: {e}")
        return []


# ============================
# CONTENT GENERATION
# ============================

def generate_content_script(gemini_model, existing_topics):
    """
    Use the Gemini API to generate a new financial topic and carousel slides.
    Returns a dictionary with the topic and slides.
    """
    print("[INFO] Generating new content script with Gemini...")

    # Build the prompt
    existing_topics_str = "\n".join([f"- {topic}" for topic in existing_topics]) if existing_topics else "None yet."

    prompt = f"""You are a financial education expert creating content for a Gen Z audience on TikTok and Instagram.
Your brand is "Financial Myth-Buster" - you break down complex financial topics in a fast-paced, non-judgmental, empowering way.

PREVIOUSLY COVERED TOPICS (DO NOT REPEAT):
{existing_topics_str}

YOUR TASK:
Generate a NEW financial topic that has NOT been covered yet. The topic should be:
- Practical and actionable
- Relevant to young adults (18-30)
- Non-judgmental (no "you're doing it wrong" tone)
- Educational but engaging
- Something that challenges common misconceptions or teaches a useful skill

Create a carousel with 8-12 slides total:
1. Title slide: A hook that grabs attention
2-9 (or 2-11): Main content slides with clear headers and concise body text
10 (or 12): Final slide with a call-to-action to follow

RESPONSE FORMAT (JSON ONLY):
{{
  "topic": "The main topic title",
  "title_slide": "Attention-grabbing hook text",
  "slides": [
    {{"header": "Slide 1 Header", "body": "Slide 1 body text (max 3 sentences)"}},
    {{"header": "Slide 2 Header", "body": "Slide 2 body text (max 3 sentences)"}},
    ...
  ],
  "final_slide": "Call-to-action text for the final slide"
}}

RULES:
- Each slide body should be 2-3 sentences max (60-100 words)
- Headers should be 3-7 words
- Use simple language (8th grade reading level)
- Be specific with numbers and examples
- Title slide should be provocative but not clickbait
- Final slide should encourage following for more content

Return ONLY valid JSON. No additional text or markdown formatting.
"""

    try:
        response = gemini_model.generate_content(prompt)
        response_text = response.text.strip()

        # Clean up the response if it has markdown code blocks
        if response_text.startswith("```json"):
            response_text = response_text[7:]  # Remove ```json
        if response_text.startswith("```"):
            response_text = response_text[3:]  # Remove ```
        if response_text.endswith("```"):
            response_text = response_text[:-3]  # Remove trailing ```
        response_text = response_text.strip()

        content_data = json.loads(response_text)

        # Validate the structure
        if not all(key in content_data for key in ["topic", "title_slide", "slides", "final_slide"]):
            raise ValueError("Generated content missing required keys.")

        print(f"[SUCCESS] Generated topic: {content_data['topic']}")
        print(f"[INFO] Total slides: {len(content_data['slides']) + 2} (title + {len(content_data['slides'])} + final)")

        return content_data

    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON response from Gemini: {e}")
        print(f"[DEBUG] Raw response: {response_text[:500]}")
        raise
    except Exception as e:
        print(f"[ERROR] Failed to generate content: {e}")
        raise


# ============================
# IMAGE GENERATION
# ============================

def generate_background_image(prompt):
    """
    Generate an abstract background image using Stability AI API.
    Falls back to gradient if API key is not configured.

    Args:
        prompt: The topic/theme for the background image

    Returns:
        PIL Image object
    """
    stability_api_key = os.getenv("STABILITY_API_KEY")

    # Check if API key is configured
    if not stability_api_key or stability_api_key == "YOUR_STABILITY_API_KEY":
        print("[WARNING] STABILITY_API_KEY not configured. Using gradient fallback.")
        return _create_gradient_fallback()

    # Generate a creative prompt for an abstract financial background
    image_prompt = (
        f"Abstract modern background for financial education content, "
        f"professional gradient, clean minimalist design, smooth colors, "
        f"geometric patterns, inspired by the topic: {prompt}. "
        f"No text, no people, no specific objects. Suitable for overlaying text."
    )

    print(f"[INFO] Generating background image with Stability AI...")
    print(f"[DEBUG] Prompt: {image_prompt[:100]}...")

    try:
        # Stability AI API endpoint
        url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {stability_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "text_prompts": [
                {
                    "text": image_prompt,
                    "weight": 1
                },
                {
                    "text": "text, letters, words, people, faces, logos, cluttered, busy",
                    "weight": -1  # Negative prompt to avoid unwanted elements
                }
            ],
            "cfg_scale": 7,
            "height": IMAGE_HEIGHT,
            "width": IMAGE_WIDTH,
            "samples": 1,
            "steps": 30,
            "style_preset": "digital-art"
        }

        # Make the API request
        response = requests.post(url, headers=headers, json=payload, timeout=60)

        if response.status_code == 200:
            data = response.json()

            # Extract the base64 image from the response
            if "artifacts" in data and len(data["artifacts"]) > 0:
                image_data = data["artifacts"][0]["base64"]
                image_bytes = base64.b64decode(image_data)
                img = Image.open(BytesIO(image_bytes))
                print("[SUCCESS] Background image generated successfully!")
                return img
            else:
                print("[WARNING] No image in response. Using fallback gradient.")
                return _create_gradient_fallback()

        elif response.status_code == 401:
            print("[ERROR] Invalid Stability API key. Check your .env file. Using fallback gradient.")
            return _create_gradient_fallback()

        elif response.status_code == 402:
            print("[ERROR] Insufficient credits in Stability AI account. Using fallback gradient.")
            return _create_gradient_fallback()

        else:
            print(f"[ERROR] Stability API error (status {response.status_code}): {response.text[:200]}")
            print("[WARNING] Using fallback gradient.")
            return _create_gradient_fallback()

    except requests.exceptions.Timeout:
        print("[ERROR] Stability API request timed out. Using fallback gradient.")
        return _create_gradient_fallback()

    except Exception as e:
        print(f"[ERROR] Failed to generate image with Stability AI: {e}")
        print("[WARNING] Using fallback gradient.")
        return _create_gradient_fallback()


def _create_gradient_fallback():
    """
    Create a simple gradient background as a fallback.
    This is used when the Stability AI API is not available.
    """
    # Create a gradient image from dark blue to purple
    img = Image.new('RGB', (IMAGE_WIDTH, IMAGE_HEIGHT))
    draw = ImageDraw.Draw(img)

    # Create a vertical gradient with more variety
    for y in range(IMAGE_HEIGHT):
        # Interpolate between dark blue (20, 30, 80) and purple (80, 40, 120)
        ratio = y / IMAGE_HEIGHT
        r = int(20 + (80 - 20) * ratio)
        g = int(30 + (40 - 30) * ratio)
        b = int(80 + (120 - 80) * ratio)
        draw.line([(0, y), (IMAGE_WIDTH, y)], fill=(r, g, b))

    return img


# ============================
# SLIDE CREATION
# ============================

def create_slide_image(background_image, text_content, slide_num, output_folder, is_title=False, is_final=False):
    """
    Create a single slide by overlaying text on the background image.

    Args:
        background_image: PIL Image object
        text_content: dict with 'header' and 'body' keys, or string for title/final slides
        slide_num: int, the slide number
        output_folder: str, path to save the image
        is_title: bool, if this is the title slide
        is_final: bool, if this is the final slide
    """
    # Clone the background
    img = background_image.copy()
    draw = ImageDraw.Draw(img, 'RGBA')

    # Add a semi-transparent dark overlay for better text readability
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 128))
    img.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(img)

    # Load fonts (with fallback to default)
    try:
        if os.path.exists(FONT_BOLD_PATH):
            font_bold_large = ImageFont.truetype(FONT_BOLD_PATH, 80)
            font_bold = ImageFont.truetype(FONT_BOLD_PATH, 60)
        else:
            print(f"[WARNING] Bold font not found at {FONT_BOLD_PATH}. Using default font.")
            font_bold_large = ImageFont.load_default()
            font_bold = ImageFont.load_default()

        if os.path.exists(FONT_REGULAR_PATH):
            font_regular = ImageFont.truetype(FONT_REGULAR_PATH, 45)
        else:
            print(f"[WARNING] Regular font not found at {FONT_REGULAR_PATH}. Using default font.")
            font_regular = ImageFont.load_default()
    except Exception as e:
        print(f"[WARNING] Error loading fonts: {e}. Using default fonts.")
        font_bold_large = ImageFont.load_default()
        font_bold = ImageFont.load_default()
        font_regular = ImageFont.load_default()

    # Margins and positioning
    margin = 80
    text_y_start = 400

    if is_title or is_final:
        # Title or final slide: large centered text
        text = text_content if isinstance(text_content, str) else text_content.get('header', '')

        # Wrap text
        max_chars = 20
        wrapped_lines = textwrap.wrap(text, width=max_chars)

        # Calculate total height to center vertically
        line_height = 100
        total_height = len(wrapped_lines) * line_height
        current_y = (IMAGE_HEIGHT - total_height) // 2

        # Draw each line centered
        for line in wrapped_lines:
            # Get text bounding box for centering
            bbox = draw.textbbox((0, 0), line, font=font_bold_large)
            text_width = bbox[2] - bbox[0]
            text_x = (IMAGE_WIDTH - text_width) // 2

            # Draw text with outline for better visibility
            outline_color = (0, 0, 0)
            text_color = (255, 255, 255)

            # Draw outline
            for adj_x in [-2, 0, 2]:
                for adj_y in [-2, 0, 2]:
                    draw.text((text_x + adj_x, current_y + adj_y), line, font=font_bold_large, fill=outline_color)

            # Draw main text
            draw.text((text_x, current_y), line, font=font_bold_large, fill=text_color)
            current_y += line_height

    else:
        # Regular slide: header + body
        header = text_content.get('header', '')
        body = text_content.get('body', '')

        # Draw header
        wrapped_header = textwrap.wrap(header, width=25)
        current_y = text_y_start

        for line in wrapped_header:
            draw.text((margin, current_y), line, font=font_bold, fill=(255, 255, 255))
            current_y += 80

        current_y += 40  # Space between header and body

        # Draw body
        wrapped_body = textwrap.wrap(body, width=35)

        for line in wrapped_body:
            draw.text((margin, current_y), line, font=font_regular, fill=(240, 240, 240))
            current_y += 60

    # Save the image
    output_path = os.path.join(output_folder, f"slide_{slide_num}.png")
    img.save(output_path, 'PNG')
    print(f"[INFO] Saved: {output_path}")


# ============================
# MONETIZATION README
# ============================

def write_monetization_readme(output_folder):
    """Create a README.md file in the output folder with monetization strategy."""
    readme_content = """# Monetization Plan (Future)

This content is designed to build a highly-engaged, high-trust audience. The primary monetization strategies will be:

1. **Affiliate Links (High-Priority):** The "link in bio" will feature affiliate links for high-quality, vetted financial products. This is the main revenue driver.
   * **High-Yield Savings Accounts (HYSAs):** (e.g., Ally, Marcus, SoFi)
   * **Budgeting Apps:** (e.g., YNAB, Monarch Money)
   * **Beginner Investing Platforms:** (e.g., Fidelity, Vanguard, M1 Finance)
   * **Ethical Credit Cards:** (e.g., Cards for building credit, or specific reward cards)

2. **Brand Deals:** Once the channel has a significant, trusted following, we can partner with "good" fintech companies (neobanks, apps, educational platforms) for sponsored "fact" videos.

3. **Digital Products:** A simple, high-value digital product.
   * **"No-BS Budgeting Template"**: A $15 Google Sheet template.
   * **"Financial Myth-Buster Workbook"**: A downloadable PDF with exercises and worksheets.

## Ethical Guidelines

- Only promote products we genuinely believe in
- Always disclose affiliate relationships
- No "get rich quick" schemes
- No predatory financial products
- Focus on education first, sales second

## Growth Strategy

- Post 3-5 times per week
- Engage with comments within 1 hour
- Cross-promote on TikTok and Instagram Reels
- Create a "link in bio" landing page with top recommendations
- Build an email list for deeper content

## Success Metrics

- Follower growth rate
- Engagement rate (likes, comments, shares)
- Click-through rate on affiliate links
- Conversion rate on affiliate products
- Email list growth

---

*This strategy focuses on building trust and providing value. The monetization will follow naturally.*
"""

    readme_path = os.path.join(output_folder, "README.md")
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    print(f"[INFO] Monetization README saved to: {readme_path}")


# ============================
# MAIN FUNCTION
# ============================

def main():
    """Main execution function."""
    print("=" * 60)
    print("FINANCIAL CAROUSEL GENERATOR")
    print("=" * 60)

    # Load environment variables
    load_dotenv()

    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"[INFO] Created output directory: {OUTPUT_DIR}")

    try:
        # Setup
        print("\n[1/7] Setting up Google Sheets connection...")
        worksheet = setup_gspread()

        print("\n[2/7] Setting up Gemini API...")
        gemini_model = setup_gemini()

        print("\n[3/7] Reading existing topics from Google Sheet...")
        existing_topics = get_existing_topics(worksheet)

        print("\n[4/7] Generating new content with Gemini...")
        content_data = generate_content_script(gemini_model, existing_topics)

        # Create a unique output folder for this run
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        topic_slug = content_data['topic'].replace(' ', '-').replace('?', '').replace(':', '')[:50]
        run_folder = os.path.join(OUTPUT_DIR, f"{timestamp}_{topic_slug}")
        os.makedirs(run_folder, exist_ok=True)
        print(f"[INFO] Created output folder: {run_folder}")

        print("\n[5/7] Generating background image...")
        background = generate_background_image(content_data['topic'])

        print("\n[6/7] Creating slide images...")
        slide_count = 1

        # Title slide
        print(f"  Creating slide {slide_count} (title)...")
        create_slide_image(background, content_data['title_slide'], slide_count, run_folder, is_title=True)
        slide_count += 1

        # Main content slides
        for slide_data in content_data['slides']:
            print(f"  Creating slide {slide_count}...")
            create_slide_image(background, slide_data, slide_count, run_folder)
            slide_count += 1

        # Final slide
        print(f"  Creating slide {slide_count} (final)...")
        create_slide_image(background, content_data['final_slide'], slide_count, run_folder, is_final=True)

        # Write monetization README
        write_monetization_readme(run_folder)

        print("\n[7/7] Updating Google Sheet...")
        new_row = [
            content_data['topic'],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            slide_count
        ]
        worksheet.append_row(new_row)
        print(f"[INFO] Added topic to Google Sheet: {content_data['topic']}")

        # Success!
        print("\n" + "=" * 60)
        print("SUCCESS!")
        print("=" * 60)
        print(f"Topic: {content_data['topic']}")
        print(f"Slides created: {slide_count}")
        print(f"Output folder: {run_folder}")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] An error occurred: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
