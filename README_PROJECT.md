# Financial Carousel Generator

This project automates the creation of Instagram/TikTok carousel slides for the "Financial Myth-Buster" channel.

## Setup

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Google Cloud & Sheets API Setup:**
   * Enable the "Google Drive API" and "Google Sheets API" in your Google Cloud Console.
   * Create a Service Account.
   * Download the JSON key for the service account and rename it to `credentials.json` in this directory.
   * Open your Google Sheet (create one if needed).
   * Share the Google Sheet with the `client_email` found in your `credentials.json` file, giving it "Editor" permissions.

3. **Stability AI Setup (Optional but Recommended):**
   * Sign up at [Stability AI Platform](https://platform.stability.ai/)
   * Generate an API key from your account dashboard
   * Add $10+ credits to your account to use the API
   * **Note:** If you skip this step, the script will use gradient backgrounds instead of AI-generated images.

4. **Environment Variables:**
   * Create a `.env` file in this directory (or edit the provided template).
   * Add your Gemini API key: `GEMINI_API_KEY="YOUR_KEY"`
   * Add your Stability AI API key: `STABILITY_API_KEY="YOUR_KEY"` (optional - gradient fallback if not provided)
   * Add your Google Sheet ID: `GOOGLE_SHEET_ID="YOUR_SHEET_ID"`
   * Add your worksheet name: `WORKSHEET_NAME="PostedTopics"` (The script will create a header row if it's empty).

5. **Fonts:**
   * Add at least one bold `.ttf` and one regular `.ttf` font file to the `/fonts/` directory.
   * Update the `FONT_BOLD_PATH` and `FONT_REGULAR_PATH` constants in `main.py` to match your filenames.

## Running the Script

```bash
python main.py
```

The script will:

1. Read your Google Sheet to see what topics have been posted.
2. Generate a new topic and 8-12 slide script via the Gemini API.
3. Generate an abstract background image using Stability AI (or use a gradient fallback).
4. Create a new folder in `/output/` named with the current date and topic.
5. Save the final `.png` slides and a `README.md` into that folder.
6. Update the Google Sheet with the new topic to avoid repeats.

## Output

Each run creates a new timestamped folder in `/output/` containing:
- `slide_1.png` through `slide_N.png` (8-12 slides)
- `README.md` (monetization strategy)

## Google Sheet Format

The Google Sheet should have:
- Column A: "Topic" (header in row 1)
- Each subsequent row contains a previously posted topic

The script will automatically create the header if the sheet is empty.

## API Providers

### Image Generation
The script uses **Stability AI (Stable Diffusion XL)** for background image generation. If you prefer a different provider:

- **OpenAI DALL-E**: Modify the `generate_background_image()` function to use OpenAI's API
- **Other providers**: The function is designed to be easily swappable

### Content Generation
- Uses **Google Gemini Pro** for topic generation and slide content

## Future Enhancements

- Add automated posting to TikTok/Instagram via their APIs
- Implement A/B testing for different slide styles
- Add analytics tracking for engagement metrics
- Support for custom image styles/themes per topic category
- Batch processing mode to generate multiple carousel sets at once

## License

MIT License - Feel free to modify and use for your own projects.
