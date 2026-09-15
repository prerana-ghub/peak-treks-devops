FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["sh", "-c", "python -c 'from app1 import app, prepare_database; app.app_context().push(); prepare_database()' && gunicorn --bind 0.0.0.0:5000 app1:app"]

