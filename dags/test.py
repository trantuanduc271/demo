from airflow import DAG
from airflow.decorators import task
from datetime import datetime

with DAG(
    "hello_world_test",
    default_args={
        "owner": "airflow",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False
    },
    description="Simple Hello World test DAG",
    schedule_interval=None,  # No schedule - manual trigger only
    start_date=datetime(2024, 1, 1),
    tags=["test"],
    catchup=False,
) as dag:

    @task(task_id="print_hello_world")
    def print_hello_world():
        print("Hello World")
    
    print_hello_world()