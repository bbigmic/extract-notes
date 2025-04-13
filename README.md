# Audio/Video Transcription & Notes Generator

Web application for transcribing audio/video files and generating notes with additional information extraction capabilities.

## Features

- Audio/video file transcription
- YouTube and Instagram video support
- Multi-language transcription support
- Automatic note generation
- Custom information extraction
- User authentication system
- Credit system with Stripe payments
- Transcription history
- File download options

## Deployment on Streamlit Cloud

1. Fork this repository to your GitHub account

2. Create an account on [Streamlit Cloud](https://streamlit.io/cloud)

3. Create new app and connect it to your forked repository

4. Set the following secrets in Streamlit Cloud settings:
```
OPENAI_API_KEY=your_openai_api_key
STRIPE_SECRET_KEY=your_stripe_secret_key
STRIPE_PUBLISHABLE_KEY=your_stripe_publishable_key
JWT_SECRET_KEY=your_jwt_secret_key
APP_URL=your_streamlit_cloud_url
```

5. Deploy the app

## Local Development

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
.\venv\Scripts\activate  # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install system dependencies:
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install ffmpeg libsndfile1

# macOS
brew install ffmpeg libsndfile
```

5. Create `.env` file with required environment variables:
```
OPENAI_API_KEY=your_openai_api_key
STRIPE_SECRET_KEY=your_stripe_secret_key
STRIPE_PUBLISHABLE_KEY=your_stripe_publishable_key
JWT_SECRET_KEY=your_jwt_secret_key
APP_URL=http://localhost:8501
```

6. Run the app:
```bash
streamlit run app.py
```

## Required Environment Variables

- `OPENAI_API_KEY`: OpenAI API key for GPT-4 access
- `STRIPE_SECRET_KEY`: Stripe secret key for payments
- `STRIPE_PUBLISHABLE_KEY`: Stripe publishable key for payments
- `JWT_SECRET_KEY`: Secret key for JWT token generation
- `APP_URL`: Application URL (local or deployed)

## Notes

- The app uses SQLite for local development
- FFmpeg is required for audio processing
- Whisper model will be downloaded on first use
- Free credits are given upon registration
- Additional credits can be purchased through Stripe

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 