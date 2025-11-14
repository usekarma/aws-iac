FROM python:3.12-slim

WORKDIR /app

# Install system deps if needed (kept minimal here)
RUN pip install --no-cache-dir --upgrade pip

# Copy app + requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Default gunicorn settings
ENV GUNICORN_CMD_ARGS="--bind 0.0.0.0:8080 --workers=2"

EXPOSE 8080

CMD ["gunicorn", "app:app"]
