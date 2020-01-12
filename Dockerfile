FROM python:3.7
COPY /venv /venv/
WORKDIR /venv/
RUN pip install -r requirements.txt
CMD kopf run __main__.py