# Pull base image
# NOTE: was python:3.8-slim-buster — Debian Buster is EOL and its apt mirrors
# 404, breaking `apt-get update`. Bookworm is current and still ships a Python
# 3.10 interpreter, which the 2022-era requirements pin set supports.
FROM python:3.10-slim-bookworm as builder

# install python project dependencies pre-requisites
# (python3-dev, not the removed python2 `python-dev`)
RUN apt-get update && \
    apt-get install -y python3-dev libldap2-dev libsasl2-dev libssl-dev && \
    apt-get install -y gcc default-libmysqlclient-dev

# Set environment variables
COPY requirements.txt requirements.txt

# Install pipenv
RUN set -ex && pip install --upgrade pip

# Install dependencies
RUN set -ex && pip install -r requirements.txt

FROM builder as final
WORKDIR /code
COPY . /app/

RUN set -ex && bash -c "eval $(grep 'PYTHONDONTWRITEBYTECODE' .env)"
RUN set -ex && bash -c "eval $(grep 'PYTHONUNBUFFERED' .env)"