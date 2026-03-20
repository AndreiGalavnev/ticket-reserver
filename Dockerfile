FROM apache/airflow:2.11.1

USER root
# Устанавливаем wget для работы установщика playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Устанавливаем ваши зависимости + playwright
# (Переносим их сюда из _PIP_ADDITIONAL_DEPENDENCIES для ускорения запуска)
RUN pip install --no-cache-dir \
    apache-airflow-providers-docker \
    apache-airflow-providers-postgres \
    psycopg2-binary \
    python-dotenv \
    playwright

# Устанавливаем системные зависимости для браузера (нужен root)
USER root
RUN playwright install-deps chromium

# Устанавливаем сам браузер
USER airflow
RUN playwright install chromium