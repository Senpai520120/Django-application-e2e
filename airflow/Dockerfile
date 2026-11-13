FROM apache/airflow:3.4.0

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# A new named volume takes the owner of the folder it is mounted on; without
# the folder in the image it is root's, and the airflow user cannot write.
USER root
RUN mkdir -p /data/analytics && chown airflow:root /data/analytics
USER airflow

# DuckDB extensions are fetched now, at build time, so a run never has to
# download one: excel for read_xlsx, httpfs for s3:// files, aws for reading
# them with an instance role instead of keys.
RUN python -c "import duckdb; [duckdb.sql(f'INSTALL {e}') for e in ('excel', 'httpfs', 'aws')]"
