import os
import sys
import time
import argparse
from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import StructuredTool
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from airflow_client import AirflowClient

# Load environment variables
load_dotenv()

AIRFLOW_URL = os.getenv("AIRFLOW_URL", "https://airflow.ducttdevops.com")
AIRFLOW_USERNAME = os.getenv("AIRFLOW_USERNAME", "admin")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "admin")

# Azure OpenAI Credentials
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

def run_monitor(airflow_client, interval=300):
    """
    Continuous monitoring loop to detect and restart failed DAGs.
    """
    print(f"Starting Airflow Monitor (Interval: {interval}s)...")
    print("Press Ctrl+C to stop.")
    
    while True:
        try:
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking DAGs...")
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
                    print(f"FAILURE DETECTED: {dag_id} (Run: {run_id})")
                    print(f"Restarting {dag_id}...")
                    try:
                        airflow_client.clear_task_instances(dag_id, run_id)
                        print(f"Restart triggered successfully.")
                    except Exception as e:
                        print(f"Failed to restart {dag_id}: {e}")
                    
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            break
        except Exception as e:
            print(f"Error in monitor loop: {e}")
        
        time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description="Airflow AI Agent")
    parser.add_argument("--monitor", action="store_true", help="Run in continuous monitoring mode")
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds (default: 300)")
    parser.add_argument("query", nargs="*", help="Natural language query for the agent")
    
    args = parser.parse_args()

    # Initialize Airflow Client
    airflow_client = AirflowClient(AIRFLOW_URL, AIRFLOW_USERNAME, AIRFLOW_PASSWORD)

    if args.monitor:
        run_monitor(airflow_client, interval=args.interval)
        return

    # Validate Azure Config
    if not (AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT):
        print("Error: Missing Azure OpenAI credentials in .env file.")
        return

    print(f"Using Azure OpenAI...")
    print(f"  - Endpoint: {AZURE_OPENAI_ENDPOINT}")
    print(f"  - Deployment: {AZURE_OPENAI_DEPLOYMENT_NAME}")
    
    llm = AzureChatOpenAI(
        azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
        openai_api_version=AZURE_OPENAI_API_VERSION,
        temperature=1
    )

    # Define Tools using StructuredTool for better argument handling
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

    try:
        agent = create_openai_tools_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)
    except Exception as e:
        print(f"Failed to create tools agent: {e}")
        return

    if args.query:
        user_input = " ".join(args.query)
        try:
            response = agent_executor.invoke({"input": user_input})
            print(f"Agent: {response['output']}")
        except Exception as e:
            print(f"Error: {e}")
        return

    print("Airflow AI Agent Initialized. Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            break
        
        try:
            response = agent_executor.invoke({"input": user_input})
            print(f"Agent: {response['output']}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
