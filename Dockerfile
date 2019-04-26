FROM python:3.7

COPY ./requirements.txt /app/
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 5000
CMD python ./main.py
