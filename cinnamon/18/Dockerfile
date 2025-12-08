# vim:set ft=dockerfile:
#
# Copyright The CloudNativePG Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
FROM postgis/postgis:18-3.6

# Do not split the description, otherwise we will see a blank space in the labels
LABEL name="PostgreSQL + TimescaleDB + PostGIS Container Images" \
	version="${PG_VERSION}" \
	release="7" \
	summary="PostgreSQL + TimescaleDB + PostGIS Container images." \
	description="This Docker image contains PostgreSQL, TimescaleDB, PostGIS and Barman Cloud based on Postgres 18-3.6."

LABEL org.opencontainers.image.description="This Docker image contains PostgreSQL, PostGIS, TimescaleDB and Barman Cloud based on Postgres 18-3.6."

COPY requirements.txt /

# Install timescaledb 2.24.0
RUN apt-get update \
	&& apt-get install -y lsb-release wget gnupg \
	&& mkdir -p /etc/apt/keyrings \
	&& wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /etc/apt/keyrings/timescaledb.gpg \
	&& echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -c -s) main" | tee /etc/apt/sources.list.d/timescaledb.list \
	&& apt-get update \
	&& apt-get install -y "timescaledb-2-postgresql-${PG_MAJOR}=2.24.0~debian$(cat /etc/debian_version | cut -d. -f1)*" "timescaledb-toolkit-postgresql-${PG_MAJOR}" \
	&& apt-get remove -y lsb-release wget gnupg \
	&& rm -fr /tmp/* \
	&& rm -rf /var/lib/apt/lists/* \
	&& INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' "timescaledb-2-postgresql-${PG_MAJOR}" | cut -d'~' -f1) \
	&& if [ "$INSTALLED_VERSION" != "2.24.0" ]; then \
		echo "ERROR: TimescaleDB version mismatch! Expected 2.24.0, got $INSTALLED_VERSION"; \
		exit 1; \
	fi

# Install PostgreSQL extensions and tools
RUN set -xe; \
	apt-get update; \
	apt-mark hold "postgresql-${PG_MAJOR}" "postgresql-client-${PG_MAJOR}" postgresql-client-common postgresql-common; \
	apt-get install -y --no-install-recommends \
	"postgresql-${PG_MAJOR}-pgaudit" \
	"postgresql-${PG_MAJOR}-pg-failover-slots" \
	"postgresql-${PG_MAJOR}-repack" \
	"postgresql-${PG_MAJOR}-pgvector" \
	"postgresql-${PG_MAJOR}-wal2json" \
	"postgresql-${PG_MAJOR}-hypopg" \
	"postgresql-${PG_MAJOR}-partman" \
	"postgresql-${PG_MAJOR}-plpgsql-check" \
	"postgresql-${PG_MAJOR}-hll" \
	"postgresql-${PG_MAJOR}-first-last-agg" \
	"postgresql-${PG_MAJOR}-extra-window-functions" \
	"postgresql-${PG_MAJOR}-decoderbufs" \
	"postgresql-${PG_MAJOR}-roaringbitmap" \
	"postgresql-${PG_MAJOR}-dirtyread" \
	"postgresql-${PG_MAJOR}-plproxy" \
	"postgresql-${PG_MAJOR}-pldebugger" \
	"postgresql-${PG_MAJOR}-pglogical" \
	"postgresql-${PG_MAJOR}-pg-checksums" \
	"postgresql-${PG_MAJOR}-pgq-node" \
	"postgresql-${PG_MAJOR}-pllua" \
	"postgresql-${PG_MAJOR}-pg-stat-kcache" \
	pgbadger \
	; \
	rm -fr /tmp/* ; \
	rm -rf /var/lib/apt/lists/*;

# We need to break the system packages to install barman-cloud in bookworm and later
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install barman-cloud
RUN set -xe; \
	apt-get update; \
	apt-get install -y --no-install-recommends \
	python3-pip \
	python3-psycopg2 \
	python3-setuptools \
	; \
	# TODO: Remove --no-deps once https://github.com/pypa/pip/issues/9644 is solved
	# Filter out typing-extensions which conflicts with Debian system package
	grep -v "^typing-extensions==" requirements.txt > /tmp/requirements-filtered.txt; \
	pip3 install --no-deps -r /tmp/requirements-filtered.txt; \
	rm -rf /var/lib/apt/lists/*;

# Install pgcli for PostgreSQL 18+
RUN set -xe; \
	if [ "${PG_MAJOR}" -ge 18 ]; then \
		apt-get update; \
		apt-get install -y --no-install-recommends pgcli; \
		rm -rf /var/lib/apt/lists/*; \
	fi

# Change the uid of postgres to 26
RUN usermod -u 26 postgres
USER 26
