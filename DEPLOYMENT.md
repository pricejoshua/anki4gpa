# Deploying to Hugging Face Spaces

This guide explains how to deploy the Anki Deck Creator app to Hugging Face Spaces using Docker.

## Prerequisites

- A Hugging Face account (sign up at [huggingface.co](https://huggingface.co/join))
- This repository or access to the code files

## Deployment Steps

### Option 1: Deploy from GitHub (Recommended)

1. **Fork or clone this repository to your GitHub account**
   - If you haven't already, push this code to a GitHub repository

2. **Create a new Space on Hugging Face**
   - Go to [huggingface.co/new-space](https://huggingface.co/new-space)
   - Choose a name for your Space (e.g., "anki-deck-creator")
   - Select "Docker" as the SDK
   - Choose "Public" or "Private" visibility
   - Click "Create Space"

3. **Connect your GitHub repository**
   - In your Space settings, go to "Files and versions"
   - Click "Connect to GitHub"
   - Select your repository
   - The Space will automatically sync with your repository

4. **Wait for deployment**
   - Hugging Face will automatically build your Docker image
   - This may take 5-10 minutes on first deployment
   - You can monitor progress in the "Build logs" section

5. **Access your app**
   - Once deployed, your app will be available at:
   - `https://huggingface.co/spaces/YOUR_USERNAME/SPACE_NAME`

### Option 2: Upload Files Directly

1. **Create a new Space**
   - Go to [huggingface.co/new-space](https://huggingface.co/new-space)
   - Choose a name and select "Docker" as the SDK
   - Click "Create Space"

2. **Upload required files**
   - Click "Files" tab in your Space
   - Upload the following files:
     - `Dockerfile`
     - `.dockerignore`
     - `requirements.txt`
     - `app.py`
     - `image_extractor.py`
     - `audio_extractor.py`
     - `file_pairer.py`
     - `deck_creator.py`
     - `README_HF.md` (optional, for Space description)

3. **Wait for build and deployment**
   - The Space will automatically build and deploy
   - Monitor progress in "Build logs"

## Configuration

### Environment Variables (Optional)

If you want to pre-configure API keys for your users, you can set them as secrets:

1. Go to your Space settings
2. Navigate to "Variables and secrets"
3. Add the following secrets (optional):
   - `GROQ_API_KEY`: Your Groq API key
   - `OPENAI_API_KEY`: Your OpenAI API key

### Space Settings

In your Space settings, you can configure:
- **Hardware**: Choose CPU (free) or upgrade to GPU for faster Whisper processing
- **Sleep time**: Set when the Space should sleep after inactivity
- **Visibility**: Public or Private

## Files Required

The following files are essential for Hugging Face Spaces deployment:

### Core Files
- ✅ `Dockerfile` - Docker configuration for the container
- ✅ `.dockerignore` - Files to exclude from the Docker build
- ✅ `requirements.txt` - Python dependencies
- ✅ `app.py` - Main Streamlit application
- ✅ `image_extractor.py` - Image extraction module
- ✅ `audio_extractor.py` - Audio extraction module
- ✅ `file_pairer.py` - File pairing module
- ✅ `deck_creator.py` - Anki deck creation module

### Optional Files
- ℹ️ `README_HF.md` - Space description and metadata (with frontmatter)
- ℹ️ `packages.txt` - System packages (already included in Dockerfile via ffmpeg)

## Troubleshooting

### Build Fails
- Check the "Build logs" in your Space for error messages
- Ensure all required files are uploaded
- Verify that `requirements.txt` contains all necessary dependencies

### App Doesn't Start
- Check that port 7860 is exposed in Dockerfile
- Verify Streamlit configuration in Dockerfile
- Review app logs for runtime errors

### Slow Performance
- Consider upgrading to a GPU-enabled Space for faster Whisper processing
- Recommend users to use the Groq API option for faster transcription

### Out of Memory
- Upgrade to a Space with more memory
- Reduce the Whisper model size in the app settings
- Use API-based Whisper instead of local processing

## Updating Your Deployment

### If using GitHub sync:
- Push changes to your GitHub repository
- The Space will automatically rebuild and redeploy

### If uploading files directly:
- Upload the updated files through the Hugging Face interface
- The Space will automatically rebuild

## Resources

- [Hugging Face Spaces Documentation](https://huggingface.co/docs/hub/spaces)
- [Docker Spaces Guide](https://huggingface.co/docs/hub/spaces-sdks-docker)
- [Streamlit Documentation](https://docs.streamlit.io/)

## Cost Considerations

- **Free Tier**: 
  - CPU-based Spaces are free
  - May have slower Whisper processing
  - Subject to usage limits and sleep after inactivity

- **Upgraded Spaces**:
  - GPU support available for faster processing
  - Pricing available at [huggingface.co/pricing](https://huggingface.co/pricing)
  - Recommended for production use or heavy workloads

## Support

If you encounter issues:
1. Check the Hugging Face Spaces documentation
2. Review the build logs in your Space
3. Open an issue in the GitHub repository
4. Ask in the Hugging Face community forums
