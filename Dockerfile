FROM hemna6969/uvicorn-gunicorn-fastapi:python-3.10

# If STATIC_INDEX is 1, serve / with /static/index.html directly (or the static URL configured)
# ENV STATIC_INDEX 1
# ENV STATIC_INDEX 0

ENV STATIC_PATH /app/web/static

COPY ./requirements.txt /app/requirements.txt

RUN pip install -U pip
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt
RUN which gunicorn
RUN pip freeze

COPY ./app /app
RUN chmod 755 /app/run.sh

VOLUME ["/app/config"]

WORKDIR /app
#CMD ["gunicorn", "--conf", "gunicorn_conf.py", "--bind 0.0.0.0:80", "\"main:create_app(config_file='config/aprsd_repeat.conf')\""]
#CMD ["/usr/local/bin/gunicorn", "--conf", "gunicorn_conf.py", "--bind", "0.0.0.0:80", "\"main:create_app(config_file='config/aprsd_repeat.conf')\""]
CMD ["/app/run.sh"]
