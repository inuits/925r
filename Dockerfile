FROM python:3.8-slim-buster AS builder

# install python project dependencies pre-requisites
RUN apt-get update \
    && apt-get install -y python-dev libldap2-dev libsasl2-dev libssl-dev \
    && apt-get install -y gcc default-libmysqlclient-dev

# Install pipenv
RUN set -ex && pip install --upgrade pip

# Install dependencies
COPY requirements.txt requirements.txt
RUN set -ex && pip install -r requirements.txt

FROM builder AS final
WORKDIR /code
COPY . .
