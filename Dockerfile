FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    TZ=Europe/Rome

EXPOSE 8501

CMD ["streamlit", "run", "/app/Dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]