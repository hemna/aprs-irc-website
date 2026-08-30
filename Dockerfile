FROM hemna6969/uvicorn-gunicorn-fastapi:python-3.10

ENV STATIC_PATH /app/web/static

COPY ./requirements.txt /app/requirements.txt

RUN pip install -U pip
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY ./app /app
RUN chmod 755 /app/run.sh

WORKDIR /app
# Server is started by run.sh via uvicorn --factory main:create_app (closes #19)
CMD ["/app/run.sh"]
