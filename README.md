ninetofiver
===========

[![Build Status](https://github.com/inuits/925r/actions/workflows/tests.yml/badge.svg?branch=master)](https://github.com/inuits/925r/actions/workflows/tests.yml)
[![Coverage Status](https://coveralls.io/repos/github/inuits/925r/badge.svg?branch=master)](https://coveralls.io/github/inuits/925r?branch=master)
[![GitHub issues](https://img.shields.io/github/issues/inuits/925r.svg)](https://shields.io)
[![License](https://img.shields.io/github/license/inuits/925r.svg)](https://shields.io)

ninetofiver (or 925r) is a free and open source time and leave tracking application.

## Installation

Install build dependencies:

```bash
apt-get install -y python-dev default-libmysqlclient-dev libldap2-dev libsasl2-dev libssl-dev
```
or
```bash
sudo dnf install -y mysql-devel openldap-devel
```

You'll need [pipenv](https://docs.pipenv.org/). Installing it is super simple:

```bash
pip install pipenv
```

After that, installing the application is smooth sailing:

```bash
pipenv install
```

Once your pipenv is set up, you can use `pipenv shell` to get a shell, or
just prefix additional commands with `pipenv run`.

## Usage
**For usage with Docker, see latter section named _Local Development (with Docker)_.**
1. Run `python manage.py migrate` to create the models.
2. Run `python manage.py createsuperuser` to create an admin user

### Running (development)

Running the command below starts a development server at
`http://127.0.0.1:8000`.

```bash
python manage.py runserver
```

### Running (production)

Running the command below starts a server using the production configuration
at `http://127.0.0.1:8000`.

Note: The `insecure` flag is used to allow the server to serve static files.

```bash
python manage.py runserver --configuration=Prod --insecure
```

## Local Development (with Docker)

To build, run and test and more ... use magic of make help to play with this project.
Make sure you have installed docker and docker compose.
```shell
make help
```
and you receive below list:
```text
build                Build project with docker compose
clean                Clean Reset project containers with docker compose
down                 Reset project containers with docker compose
help                 Show this help
test                 Run project tests and coverage with tox runner
up                   Run project with docker compose
```
### How to run local environment with test data.
Build and run docker containers.
```shell
make build
make up
```
Exec initial migration. After _exec_ should be your 925r container name.
```shell
docker exec 925r-web python manage.py migrate
```
Interactively create a new superuser.
```shell
docker exec -it 925r-web python manage.py createsuperuser
```

If you are running YaYata too (in debug mode), then you could need to change 925r port from 
8888 to something else, because YaYata runs webpack on the port 8888.

### Next steps
If you want to work with YaYata you need to set up an application. 
1. Log in.
2. In the right top corner, navigate to **Your Account -> Your applications -> New application**.
3. Fill **Name** and **Client id**.
4. Set **Client type = Public**.
5. Set **Authorization grant type = Resource owner password-based**.

Now you can log in YaYata with root account, or you can create a new test user.
You are all set to work with Admin interface, if you want some test data filled, see next section.

## Example/Test data
You can use django command `create_test_data` to fill database with test data.
You can specify the ammount of data to be created by one optional argument
(`small`, `normal` or `extensive`) with `normal` being the default ammount when not specified.
It can run a few minutes depending on resources. For this reason there is a `-t` option, so you 
can see what is happening at the moment.
```shell
docker exec -t 925r-web python manage.py create_test_data extensive
```

## Configuration

Since this application is built using Django, you can configure the settings
which will be loaded using the environment variables `DJANGO_SETTINGS_MODULE`
(defaulting to `ninetofiver.settings`) and `DJANGO_CONFIGURATION` (defaulting
to `Dev`).

The application will also attempt to load a YAML configuration file from a
location specified using the environment variable `CFG_FILE_PATH` (defaulting
to `/etc/925r/config.yml`) and use the resulting data to override existing
settings.

For example, if you wanted to override the secret key used for production you
could use the following configuration:

```yaml
# Use your own secret key!
SECRET_KEY: mae3fo4dooJaiteth2emeaNga1biey9ia8FaiQuooYoac8phohee7r
```

## Testing

Run the test suite:

```bash
tox
```

Generate dummy data for testing (only in DEBUG mode):

```bash
python manage.py create_test_data  # fills almost all tables
```

Clean all database:

```bash
python manage.py flush
# or delete db.sqlite3 file in root directory
```

Other commands for testing:
```bash
python manage.py help
# [ninetofiver]
```

## License

See [LICENSE](LICENSE)

```
ninetofiver (925r): a free and open source time and leave tracking application.
Copyright (C) 2016-2019 Kalman Olah

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
```
