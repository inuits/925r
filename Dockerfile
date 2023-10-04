# Pull base image
FROM python:3.9-slim-bookworm as builder

# install python project dependencies pre-requisites
RUN apt-get update && \
    apt-get install -y libldap2-dev libsasl2-dev libssl-dev && \
    apt-get install -y gcc default-libmysqlclient-dev pkg-config

# Copy Pipfile dependency list
COPY Pipfile Pipfile
COPY Pipfile.lock Pipfile.lock

# Install pipenv
RUN set -ex && pip install --upgrade pip && pip install pipenv

# Install dependencies
RUN set -ex && pipenv install --system

# gunicorn
RUN mkdir /var/log/gunicorn
RUN touch /var/log/gunicorn/access-ninetofiver.log && touch /var/log/gunicorn/error-ninetofiver.log
RUN mkdir /run/gunicorn

FROM builder as final
WORKDIR /code
COPY . /app/

# whitenoise
RUN python /app/manage.py collectstatic --noinput

RUN set -ex && bash -c "eval $(grep 'PYTHONDONTWRITEBYTECODE' .env)"
RUN set -ex && bash -c "eval $(grep 'PYTHONUNBUFFERED' .env)"