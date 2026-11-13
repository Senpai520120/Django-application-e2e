FROM apache/airflow:3.3.2

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# A new named volume takes the owner of the folder it is mounted on; without
# the folder in the image it is root's, and the airflow user cannot write.
USER root
RUN mkdir -p /data/analytics && chown airflow:root /data/analytics
USER airflow

# read_xlsx lives in DuckDB's excel extension: fetched now, at build time, so
# a run never has to download it.
RUN python -c "import duckdb; duckdb.sql('INSTALL excel')"
