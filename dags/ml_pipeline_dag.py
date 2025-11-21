from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from datetime import datetime, timedelta
from ml_pipeline_tasks.data import check_data_exists, preprocess_data
from ml_pipeline_tasks.model import train_model, test_model, decide_deployment, deploy_model
from ml_pipeline_tasks.utils import notify

default_args = {"retries": 1, "retry_delay": timedelta(minutes=5)}

with DAG(
    dag_id="ml_model_training_pipeline",
    start_date=datetime(2025, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    default_args=default_args
) as dag:

    t1 = PythonOperator(task_id="check_data", python_callable=check_data_exists)
    t2 = preprocess_data()
    t3 = PythonOperator(task_id="train_model", python_callable=train_model, provide_context=True)
    t4 = PythonOperator(task_id="test_model", python_callable=test_model, provide_context=True)
    t5 = BranchPythonOperator(task_id="decide_deployment", python_callable=decide_deployment, provide_context=True)
    t6 = PythonOperator(task_id="deploy_model", python_callable=deploy_model)
    t7 = PythonOperator(task_id="notify_completion", python_callable=notify)

    t1 >> t2 >> t3 >> t4 >> t5
    t5 >> [t6, t7]
    t6 >> t7
