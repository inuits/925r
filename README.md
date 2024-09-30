ninetofiver
===========

[![Build Status](https://travis-ci.org/kalmanolah/925r.svg?branch=master)](https://travis-ci.org/kalmanolah/925r)
[![Coverage Status](https://coveralls.io/repos/github/kalmanolah/925r/badge.svg?branch=master)](https://coveralls.io/github/kalmanolah/925r?branch=master)
[![GitHub issues](https://img.shields.io/github/issues/kalmanolah/925r.svg)](https://shields.io)
[![License](https://img.shields.io/github/license/kalmanolah/925r.svg)](https://shields.io)

ninetofiver (or 925r) is a free and open source time and leave tracking application.
                    
## Dependencies

- [Taskfile](https://taskfile.dev/)
- [Docker Compose plugin](https://docs.docker.com/compose/)

The Taskfile and Docker Compose setup hides a bit of the setup.
If you want to walk the manual path, check the files `.env.dist`, `Taskfile.dist.yml` and `Dockerfile`.

## Usage

1. Run `task prepare` and check if the values in the .env file are correct for your environment
2. Run `task start` to start the application at `http://localhost:8000`.
3. Run `task app:manage -- migrate` to create the models
4. Run `task app:manage -- createsuperuser` to create an admin user (interactively)
5. Run `task app:manage -- create_test_data` to fill the database with test data (see below for more information)

For more tasks, check `task --list-all`. 
  
## First steps

### Set up an application for YaYata

Before you can set up YaYata, you need to register an application in ninetofiver.

1. Log in.
2. In the right top corner, navigate to **Your Account -> Your applications -> New application**.
3. Fill **Name** and **Client id**.
4. Set **Client type = Public**.
5. Set **Authorization grant type = Resource owner password-based**.

Now you can log in to YaYata with the root account, or you can create a new test user.

### Add example data

You can run `task app:manage -- create_test_data` to fill the database with test data.
You can specify the amount of data to be created by one optional argument `amount`. Possible values are
(`small`, `normal` or `extensive`) with `normal` being the default.
```shell
task app:manage -- create_test_data extensive
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

## Test

Run the test suite:

```bash
task test
```

Generate dummy data for testing (only in DEBUG mode):

```bash
task task app:manage -- create_test_data # fills almost all tables
```

Clean the complete database:

```bash
task app:manage -- flush
# or delete db.sqlite3 file in root directory
```         

Other possible commands can be found by running:
```bash
task app:manage -- help
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
