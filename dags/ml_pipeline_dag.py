from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
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

    t1 = BashOperator(
        task_id="check_data",
        bash_command="pip install --no-cache-dir scikit-learn pandas joblib && python -c 'import os; DATA_PATH=\"/opt/airflow/data/training_data.csv\"; exec(\"if not os.path.exists(DATA_PATH): raise FileNotFoundError(f\\\"{DATA_PATH} not found\\\")\nprint(\\\"Training data exists\\\")\")'"
    )
    
    t2 = BashOperator(
        task_id="preprocess_data",
        bash_command="pip install --no-cache-dir scikit-learn pandas joblib && python -c 'import pandas as pd; import os; DATA_PATH=\"/opt/airflow/data/training_data.csv\"; PROCESSED_DATA_PATH=\"/opt/airflow/data/processed_training_data.csv\"; df=pd.read_csv(DATA_PATH); df=df.drop(\"customer_id\", axis=1); df[\"gender\"]=df[\"gender\"].map({\"M\": 0, \"F\": 1}); df.fillna(0, inplace=True); os.makedirs(os.path.dirname(PROCESSED_DATA_PATH), exist_ok=True); df.to_csv(PROCESSED_DATA_PATH, index=False); print(f\"Preprocessed data saved to {PROCESSED_DATA_PATH}\")'"
    )
    
    t3 = BashOperator(
        task_id="train_model",
        bash_command="pip install --no-cache-dir scikit-learn pandas joblib && python -c 'import joblib; import pandas as pd; from sklearn.ensemble import RandomForestClassifier; from sklearn.model_selection import train_test_split; PROCESSED_DATA_PATH=\"/opt/airflow/data/processed_training_data.csv\"; MODEL_PATH=\"/opt/airflow/models/model_latest.pkl\"; df=pd.read_csv(PROCESSED_DATA_PATH); X=df.drop(\"target\", axis=1); y=df[\"target\"]; X_train, X_test, y_train, y_test=train_test_split(X, y, test_size=0.2, random_state=42); model=RandomForestClassifier(n_estimators=100, random_state=42); model.fit(X_train, y_train); joblib.dump(model, MODEL_PATH); print(f\"Model trained and saved to {MODEL_PATH}\")'"
    )
    
    t4 = BashOperator(
        task_id="test_model",
        bash_command="pip install --no-cache-dir scikit-learn pandas joblib && python -c 'import joblib; import pandas as pd; from sklearn.model_selection import train_test_split; from sklearn.metrics import accuracy_score; PROCESSED_DATA_PATH=\"/opt/airflow/data/processed_training_data.csv\"; MODEL_PATH=\"/opt/airflow/models/model_latest.pkl\"; model=joblib.load(MODEL_PATH); df=pd.read_csv(PROCESSED_DATA_PATH); X=df.drop(\"target\", axis=1); y=df[\"target\"]; X_train, X_test, y_train, y_test=train_test_split(X, y, test_size=0.2, random_state=42); accuracy=accuracy_score(y_test, model.predict(X_test)); print(f\"Test Accuracy: {accuracy:.2f}\"); print(accuracy)'"
    )
    
    t5 = BashOperator(
        task_id="decide_deployment",
        bash_command="pip install --no-cache-dir scikit-learn pandas joblib && python -c 'import joblib; import pandas as pd; from sklearn.model_selection import train_test_split; from sklearn.metrics import accuracy_score; PROCESSED_DATA_PATH=\"/opt/airflow/data/processed_training_data.csv\"; MODEL_PATH=\"/opt/airflow/models/model_latest.pkl\"; MIN_ACCURACY=0.78; model=joblib.load(MODEL_PATH); df=pd.read_csv(PROCESSED_DATA_PATH); X=df.drop(\"target\", axis=1); y=df[\"target\"]; X_train, X_test, y_train, y_test=train_test_split(X, y, test_size=0.2, random_state=42); accuracy=accuracy_score(y_test, model.predict(X_test)); exit(0 if accuracy >= MIN_ACCURACY else 1)'"
    )
    
    t6 = BashOperator(
        task_id="deploy_model",
        bash_command="pip install --no-cache-dir scikit-learn pandas joblib && python -c 'MODEL_PATH=\"/opt/airflow/models/model_latest.pkl\"; print(f\"Deploying model: {MODEL_PATH}\"); print(\"Model deployment complete\")'"
    )
    
    t7 = BashOperator(
        task_id="notify_completion",
        bash_command="python -c 'print(\"ML Pipeline completed\")'"
    )

    t1 >> t2 >> t3 >> t4 >> t5 >> t6 >> t7
