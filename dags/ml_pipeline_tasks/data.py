import os
import pandas as pd
from airflow.datasets import Dataset
from airflow.decorators import task
import shutil

# Read from git-sync mounted repo (read-only)
SOURCE_DATA_PATH = "/opt/airflow/dags/repo/data/training_data.csv"

# Write to writable locations
DATA_PATH = "/opt/airflow/data/training_data.csv"
PROCESSED_DATA_PATH = "/opt/airflow/data/processed_training_data.csv"

# Dataset outlet
PREPROCESSED_DATASET = Dataset(PROCESSED_DATA_PATH)

def check_data_exists():
    """Check if raw training data exists and copy to writable location"""
    # Check if source data exists in repo
    if not os.path.exists(SOURCE_DATA_PATH):
        raise FileNotFoundError(f"{SOURCE_DATA_PATH} not found in repository")
    
    # Copy to writable location
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    shutil.copy2(SOURCE_DATA_PATH, DATA_PATH)
    print(f"Training data copied from {SOURCE_DATA_PATH} to {DATA_PATH}")

@task(outlets=[PREPROCESSED_DATASET], do_xcom_push=False)
def preprocess_data():
    """Preprocess raw data and save as processed dataset"""
    df = pd.read_csv(DATA_PATH)
    df = df.drop("customer_id", axis=1)
    df["gender"] = df["gender"].map({"M": 0, "F": 1})
    df.fillna(0, inplace=True)
    os.makedirs(os.path.dirname(PROCESSED_DATA_PATH), exist_ok=True)
    df.to_csv(PROCESSED_DATA_PATH, index=False)
    print(f"Preprocessed data saved to {PROCESSED_DATA_PATH}")
