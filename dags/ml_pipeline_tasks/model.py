import os
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from ml_pipeline_tasks.data import PROCESSED_DATA_PATH
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from azure.storage.blob import BlobServiceClient
from airflow.models import Variable

MODEL_PATH = "/opt/airflow/dags/repo/models/model_latest.pkl"
MIN_ACCURACY = 0.78

# Azure Blob Storage configuration from Airflow Variables
AZURE_STORAGE_CONNECTION_STRING = Variable.get("azure_storage_connection_string", "")
AZURE_CONTAINER_NAME = Variable.get("azure_container_name", "ml-data")
AZURE_MODEL_BLOB_NAME = Variable.get("azure_model_blob_name", "model_latest.pkl")

def upload_model_to_azure_blob(local_path):
    """Upload trained model to Azure Blob Storage"""
    if not AZURE_STORAGE_CONNECTION_STRING:
        print("Azure Storage connection string not configured, skipping upload")
        return False
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=AZURE_MODEL_BLOB_NAME)
        
        with open(local_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        
        print(f"Successfully uploaded model to Azure Blob Storage: {AZURE_MODEL_BLOB_NAME}")
        return True
    except Exception as e:
        print(f"Error uploading model to Azure Blob Storage: {e}")
        return False

def download_model_from_azure_blob(local_path):
    """Download model from Azure Blob Storage"""
    if not AZURE_STORAGE_CONNECTION_STRING:
        print("Azure Storage connection string not configured")
        return False
    
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=AZURE_MODEL_BLOB_NAME)
        
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())
        
        print(f"Successfully downloaded model from Azure Blob Storage to {local_path}")
        return True
    except Exception as e:
        print(f"Error downloading model from Azure Blob Storage: {e}")
        return False

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

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Model trained and saved to {MODEL_PATH}")
    
    # Upload model to Azure Blob Storage
    upload_model_to_azure_blob(MODEL_PATH)

def test_model(**context):
    """Evaluate model"""
    # Try to download model from Azure if not available locally
    if not os.path.exists(MODEL_PATH):
        print(f"Model not found locally, attempting to download from Azure...")
        download_model_from_azure_blob(MODEL_PATH)
    
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
    
    # Upload to Azure Blob Storage as production model
    if AZURE_STORAGE_CONNECTION_STRING:
        try:
            blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
            prod_blob_name = "model_production.pkl"
            blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=prod_blob_name)
            
            with open(MODEL_PATH, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            
            print(f"Model deployed to Azure Blob Storage as {prod_blob_name}")
        except Exception as e:
            print(f"Warning: Failed to deploy model to Azure: {e}")
    
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
