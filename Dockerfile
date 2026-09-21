   FROM python:3.12-slim

   WORKDIR /app
   ENV PYTHONUNBUFFERED=1

   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   COPY . .

   RUN useradd -m appuser && chown -R appuser /app
   USER appuser

   EXPOSE 5000

   CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]