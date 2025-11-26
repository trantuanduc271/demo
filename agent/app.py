import os
import warnings
import time
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import StructuredTool
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from airflow_client import AirflowClient
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

AIRFLOW_URL = os.getenv("AIRFLOW_URL", "https://airflow.ducttdevops.com")
AIRFLOW_USERNAME = os.getenv("AIRFLOW_USERNAME", "admin")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "admin")

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

airflow_client = AirflowClient(AIRFLOW_URL, AIRFLOW_USERNAME, AIRFLOW_PASSWORD)

# Monitor state
monitor_state = {
    'running': False,
    'interval': 300,
    'logs': [],
    'thread': None
}

def monitor_loop():
    """Background monitoring loop"""
    while monitor_state['running']:
        try:
            log_entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'message': 'Checking DAGs...',
                'type': 'info'
            }
            monitor_state['logs'].append(log_entry)
            
            dags_response = airflow_client.list_dags()
            
            for dag in dags_response.get('dags', []):
                dag_id = dag['dag_id']
                runs_response = airflow_client.get_dag_runs(dag_id, limit=1)
                runs = runs_response.get('dag_runs', [])
                
                if not runs:
                    continue
                
                last_run = runs[0]
                state = last_run['state']
                run_id = last_run['dag_run_id']
                
                if state == 'failed':
                    log_entry = {
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'message': f'FAILURE DETECTED: {dag_id} (Run: {run_id})',
                        'type': 'warning'
                    }
                    monitor_state['logs'].append(log_entry)
                    
                    try:
                        airflow_client.clear_task_instances(dag_id, run_id)
                        log_entry = {
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'message': f'Restart triggered for {dag_id}',
                            'type': 'success'
                        }
                        monitor_state['logs'].append(log_entry)
                    except Exception as e:
                        log_entry = {
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'message': f'Failed to restart {dag_id}: {str(e)}',
                            'type': 'error'
                        }
                        monitor_state['logs'].append(log_entry)
            
            # Keep only last 50 logs
            if len(monitor_state['logs']) > 50:
                monitor_state['logs'] = monitor_state['logs'][-50:]
                
        except Exception as e:
            log_entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'message': f'Error in monitor loop: {str(e)}',
                'type': 'error'
            }
            monitor_state['logs'].append(log_entry)
        
        time.sleep(monitor_state['interval'])

llm = AzureChatOpenAI(
    azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
    openai_api_version=AZURE_OPENAI_API_VERSION,
    temperature=1
)

def list_dags_tool():
    """List all available DAGs."""
    try:
        dags = airflow_client.list_dags()
        return [dag['dag_id'] for dag in dags['dags']]
    except Exception as e:
        return f"Error listing DAGs: {str(e)}"

def get_dag_runs_tool(dag_id: str):
    """Get last 10 runs for a DAG."""
    try:
        dag_id = dag_id.strip()
        runs = airflow_client.get_dag_runs(dag_id, limit=10)
        if not runs['dag_runs']:
            return f"No runs found for DAG {dag_id}"
        
        summary = []
        for run in runs['dag_runs']:
            summary.append({
                "run_id": run['dag_run_id'],
                "state": run['state'],
                "execution_date": run['execution_date']
            })
        return str(summary)
    except Exception as e:
        return f"Error getting DAG runs: {str(e)}"

def restart_dag_run_tool(dag_id: str, run_id: str):
    """Restart a specific DAG run."""
    try:
        airflow_client.clear_task_instances(dag_id, run_id)
        return f"Successfully triggered restart for Run ID: {run_id} of DAG: {dag_id}"
    except Exception as e:
        return f"Error restarting DAG run: {str(e)}"

def trigger_dag_tool(dag_id: str):
    """Trigger a new DAG run."""
    try:
        dag_id = dag_id.strip()
        dags = airflow_client.list_dags()
        dag_ids = [d['dag_id'] for d in dags['dags']]
        if dag_id not in dag_ids:
            return f"DAG {dag_id} not found. Available DAGs: {dag_ids}"
        
        response = airflow_client.trigger_dag_run(dag_id)
        return f"Successfully triggered NEW run for DAG {dag_id}. Run ID: {response['dag_run_id']}"
    except Exception as e:
        return f"Error triggering DAG: {str(e)}"

tools = [
    StructuredTool.from_function(
        func=list_dags_tool,
        name="ListDAGs",
        description="List all available DAGs."
    ),
    StructuredTool.from_function(
        func=get_dag_runs_tool,
        name="GetDAGRuns",
        description="Get status/history of a DAG. Returns recent runs with IDs and states."
    ),
    StructuredTool.from_function(
        func=restart_dag_run_tool,
        name="RestartDAGRun",
        description="Restart a SPECIFIC failed run. Requires dag_id and run_id."
    ),
    StructuredTool.from_function(
        func=trigger_dag_tool,
        name="TriggerDAG",
        description="Trigger a BRAND NEW run of a DAG."
    )
]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant capable of managing Airflow DAGs."),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_openai_tools_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '')
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        response = agent_executor.invoke({"input": user_message})
        return jsonify({'response': response['output']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/monitor/start', methods=['POST'])
def start_monitor():
    try:
        interval = request.json.get('interval', 300)
        
        if monitor_state['running']:
            return jsonify({'error': 'Monitor is already running'}), 400
        
        monitor_state['running'] = True
        monitor_state['interval'] = interval
        monitor_state['logs'] = [{
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': f'Monitor started (interval: {interval}s)',
            'type': 'success'
        }]
        
        monitor_state['thread'] = threading.Thread(target=monitor_loop, daemon=True)
        monitor_state['thread'].start()
        
        return jsonify({'status': 'started', 'interval': interval})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/monitor/stop', methods=['POST'])
def stop_monitor():
    try:
        if not monitor_state['running']:
            return jsonify({'error': 'Monitor is not running'}), 400
        
        monitor_state['running'] = False
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': 'Monitor stopped',
            'type': 'info'
        }
        monitor_state['logs'].append(log_entry)
        
        return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/monitor/status', methods=['GET'])
def monitor_status():
    return jsonify({
        'running': monitor_state['running'],
        'interval': monitor_state['interval'],
        'logs': monitor_state['logs'][-20:]  # Return last 20 logs
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)

