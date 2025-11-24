import unittest
from unittest.mock import MagicMock, patch
from airflow_client import AirflowClient

class TestAirflowClient(unittest.TestCase):
    def setUp(self):
        self.client = AirflowClient("http://test-airflow.com", "user", "pass")

    @patch('requests.get')
    def test_list_dags(self, mock_get):
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {"dags": [{"dag_id": "dag1"}, {"dag_id": "dag2"}]}
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        dags = self.client.list_dags()
        self.assertEqual(len(dags['dags']), 2)
        self.assertEqual(dags['dags'][0]['dag_id'], "dag1")

    @patch('requests.get')
    def test_get_dag_runs(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"dag_runs": [{"dag_run_id": "run1", "state": "failed"}]}
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        runs = self.client.get_dag_runs("dag1")
        self.assertEqual(runs['dag_runs'][0]['state'], "failed")

    @patch('requests.post')
    def test_clear_task_instances(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success"}
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = self.client.clear_task_instances("dag1", "run1")
        self.assertEqual(result['status'], "success")

if __name__ == '__main__':
    unittest.main()
