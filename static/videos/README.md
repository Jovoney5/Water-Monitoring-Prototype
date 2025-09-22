# Video Assets

## Background Video

Place your `water.mp4` video file in this directory for the login screen background.

### Video Requirements:
- **Filename:** `water.mp4`
- **Format:** MP4 (recommended for best browser compatibility)
- **Recommended resolution:** 1920x1080 or higher
- **Duration:** Any length (will loop automatically)
- **File size:** Keep under 10MB for better loading performance

### Video Characteristics:
- The video will automatically loop continuously
- Audio is muted (background videos should be silent)
- The video will be fullscreen and cover the entire login page
- A semi-transparent overlay is applied for better text readability
- If the video fails to load, a gradient background fallback is used

### Fallback Behavior:
- If `water.mp4` is not found, the login page will display a blue gradient background
- The video gracefully handles loading errors
- Mobile devices may have restrictions on autoplay, but the first frame will still display

### Testing:
After placing your `water.mp4` file here, restart the Flask application and visit the login page to see the video background in action.