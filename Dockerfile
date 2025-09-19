# Dockerfile
FROM nvidia/cuda:11.8-devel-ubuntu20.04

# Instaluj systemowe zależności
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    ffmpeg \
    libsndfile1 \
    libsndfile1-dev \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Ustaw Python3 jako domyślny
RUN ln -s /usr/bin/python3 /usr/bin/python

# Ustaw katalog roboczy
WORKDIR /app

# Skopiuj requirements.txt
COPY requirements.txt .

# Zainstaluj zależności Python
RUN pip3 install --no-cache-dir -r requirements.txt

# Pobierz model Whisper (base dla szybszego startu)
RUN python -c "import whisper; whisper.load_model('base')"

# Skopiuj kod aplikacji
COPY . .

# Utwórz katalog dla plików tymczasowych
RUN mkdir -p /app/temp

# Ustaw zmienne środowiskowe
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Otwórz port
EXPOSE 8501

# Uruchom aplikację
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
