FROM python:3.7
COPY /venv /venv/
WORKDIR /venv/
RUN pip install -r requirements.txt
EXPOSE 8080
CMD kopf run --liveness=http://0.0.0.0:8080/healthz --verbose __main__.py
#CMD kopf run __main__.py