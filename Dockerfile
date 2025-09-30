                                                               
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN python manage.py collectstatic --noinput

EXPOSE 5000
CMD ["sh", "-c", "python manage.py migrate && gunicorn aas.wsgi:application --bind 0.0.0.0:8000"]