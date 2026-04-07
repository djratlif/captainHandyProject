FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 3000
CMD ["gunicorn", "-b", "0.0.0.0:3000", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
