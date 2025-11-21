from airflow import DAG
from datetime import datetime, timedelta
from ml_pipeline_tasks.data import PREPROCESSED_DATASET
from airflow.operators.python import PythonOperator
from ml_pipeline_tasks.model import evaluate_and_report_dataset
from ml_pipeline_tasks.utils import notify

REPORT_PATH = "/opt/airflow/dags/repo/reports/model_report.txt"
MODEL_PATH = "/opt/airflow/dags/repo/models/model_latest.pkl"
MIN_ACCURACY = 0.22

def evaluate_and_report_task():
    evaluate_and_report_dataset(
        preprocessed_dataset_path=PREPROCESSED_DATASET.uri,
        report_path=REPORT_PATH,
        model_path=MODEL_PATH,
        min_accuracy=MIN_ACCURACY
    )


default_args = {"retries": 1, "retry_delay": timedelta(minutes=5)}

with DAG(
    dag_id="ml_model_downstream_on_dataset",
    start_date=datetime(2025, 1, 1),
    schedule=[PREPROCESSED_DATASET],  # Trigger when dataset updates
    catchup=False,
    default_args=default_args
) as dag:

    t1 = PythonOperator(task_id="evaluate_and_report", python_callable=evaluate_and_report_task)
    t2 = PythonOperator(task_id="notify_completion", python_callable=notify)

    t1 >> t2
