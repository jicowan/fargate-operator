FROM python:3.7
COPY /venv /venv/
WORKDIR /venv/
RUN pip install -r requirements.txt
CMD kopf run --liveness=http://127.0.0.1:8080/healthz __main__.py
#CMD kopf run __main__.py