from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 0, # No retries so it fails immediately
}

import time

def failing_task():
    print("Starting task... waiting 60 seconds before failing.")
    time.sleep(60)
    raise Exception("This is a planned failure to test the AI Agent!")

with DAG(
    'example_failure_dag',
    default_args=default_args,
    description='A DAG that always fails to test auto-restart',
    schedule_interval=timedelta(days=1),
    catchup=False,
) as dag:

    task_fail = PythonOperator(
        task_id='always_fails',
        python_callable=failing_task,
    )
