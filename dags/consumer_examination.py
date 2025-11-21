from airflow import DAG

from datetime import datetime, timedelta
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'ductt',
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id="first_dag",
    description="My first dag",
    start_date=datetime(2025, 11, 20),
    schedule_interval="@daily",
) as dag:
    pass
    task1 = BashOperator(
        task_id="first_task",
        bash_command="echo Helloworld, this is my first dag!",
    )

    task2 = BashOperator(
        task_id="second_task",
        bash_command="echo This is the second task",
    )

    task3 = BashOperator(
        task_id="third_task",
        bash_command="echo This is the third task",
    )

    task1 >> task2 >> task3