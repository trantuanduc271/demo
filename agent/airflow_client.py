import os
import requests
from urllib.parse import urljoin
import base64

class AirflowClient:
    def __init__(self, airflow_url, username, password):
        self.base_url = airflow_url
        self.auth = (username, password)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def _get_url(self, endpoint):
        return urljoin(self.base_url, f"api/v1/{endpoint}")

    def list_dags(self):
        """List all available DAGs."""
        url = self._get_url("dags")
        response = requests.get(url, auth=self.auth, headers=self.headers, verify=False)
        response.raise_for_status()
        return response.json()

    def get_dag_runs(self, dag_id, limit=5):
        """Get recent runs for a DAG."""
        url = self._get_url(f"dags/{dag_id}/dagRuns")
        params = {"limit": limit, "order_by": "-execution_date"}
        response = requests.get(url, auth=self.auth, headers=self.headers, params=params, verify=False)
        response.raise_for_status()
        return response.json()

    def trigger_dag_run(self, dag_id, conf=None):
        """Trigger a new DAG run."""
        url = self._get_url(f"dags/{dag_id}/dagRuns")
        data = {"conf": conf or {}}
        response = requests.post(url, auth=self.auth, headers=self.headers, json=data, verify=False)
        response.raise_for_status()
        return response.json()

    def clear_task_instances(self, dag_id, dag_run_id, dry_run=False):
        """
        Clear task instances for a specific DAG run to restart them.
        """
        url = self._get_url(f"dags/{dag_id}/clearTaskInstances")
        data = {
            "dry_run": dry_run,
            "dag_run_id": dag_run_id,
            "include_downstream": True,
            "include_upstream": False,
            "include_future": False,
            "reset_dag_runs": True,
        }
        
        response = requests.post(url, auth=self.auth, headers=self.headers, json=data, verify=False)
        response.raise_for_status()
        return response.json()
