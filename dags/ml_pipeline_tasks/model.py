import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from ml_pipeline_tasks.data import PROCESSED_DATA_PATH
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

MODEL_PATH = "/opt/airflow/dags/repo/models/model_latest.pkl"
MIN_ACCURACY = 0.20

def train_model(**context):
    """Train RandomForest on processed data"""
    df = pd.read_csv(PROCESSED_DATA_PATH)
    X = df.drop("target", axis=1)
    y = df["target"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    context['ti'].xcom_push(key='X_test', value=X_test.to_json())
    context['ti'].xcom_push(key='y_test', value=y_test.tolist())

    joblib.dump(model, MODEL_PATH)
    print(f"Model trained and saved to {MODEL_PATH}")

def test_model(**context):
    """Evaluate model"""
    model = joblib.load(MODEL_PATH)
    X_test = pd.read_json(context['ti'].xcom_pull(key='X_test'))
    y_test = context['ti'].xcom_pull(key='y_test')

    accuracy = accuracy_score(y_test, model.predict(X_test))
    context['ti'].xcom_push(key='accuracy', value=accuracy)
    print(f"Test Accuracy: {accuracy:.2f}")
    return accuracy

def decide_deployment(**context):
    """Decide if model should be deployed"""
    accuracy = context['ti'].xcom_pull(key='accuracy')
    if accuracy >= MIN_ACCURACY:
        print("Accuracy sufficient. Deploy model")
        return "deploy_model"
    else:
        print("Accuracy below threshold. Skip deployment")
        return "notify_completion"

def deploy_model():
    print(f"Deploying model: {MODEL_PATH}")
    print("Model deployment complete")

def evaluate_and_report_dataset(preprocessed_dataset_path, report_path, model_path, min_accuracy=0.78):
    """Train, evaluate, and generate report from preprocessed dataset"""
    df = pd.read_csv(preprocessed_dataset_path)
    X = df.drop("target", axis=1)
    y = df["target"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    report = (
        f"Model Evaluation Report\n"
        f"Accuracy: {accuracy:.2f}\n"
        f"Precision: {precision:.2f}\n"
        f"Recall: {recall:.2f}\n"
        f"F1 Score: {f1:.2f}\n"
    )

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)

    print(report)
