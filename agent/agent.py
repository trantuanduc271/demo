import os
import sys
import time
import argparse
from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent, Tool
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from airflow_client import AirflowClient

# Load environment variables
load_dotenv()

AIRFLOW_URL = os.getenv("AIRFLOW_URL", "https://airflow.ducttdevops.com")
AIRFLOW_USERNAME = os.getenv("AIRFLOW_USERNAME", "admin")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "admin")

# LLM Credentials
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
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
                # Get the most recent run
                runs_response = airflow_client.get_dag_runs(dag_id, limit=1)
                runs = runs_response.get('dag_runs', [])
                
                if not runs:
                    continue
                
                last_run = runs[0]
                state = last_run['state']
                run_id = last_run['dag_run_id']
                
                if state == 'failed':
                    print(f"⚠️  FAILURE DETECTED: {dag_id} (Run: {run_id})")
                    print(f"🔄 Restarting {dag_id}...")
                    try:
                        airflow_client.clear_task_instances(dag_id, run_id)
                        print(f"✅ Restart triggered successfully.")
                    except Exception as e:
                        print(f"❌ Failed to restart {dag_id}: {e}")
                else:
                    # Verbose logging could go here, but keeping it clean for now
                    pass
                    
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            break
        except Exception as e:
            print(f"Error in monitor loop: {e}")
        
        time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description="Airflow AI Agent")
    parser.add_argument("--monitor", action="store_true", help="Run in continuous monitoring mode to auto-restart failed DAGs")
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds for monitor mode (default: 300)")
    parser.add_argument("query", nargs="*", help="Natural language query for the agent (if not in monitor mode)")
    
    args = parser.parse_args()

    # Initialize Airflow Client
    airflow_client = AirflowClient(AIRFLOW_URL, AIRFLOW_USERNAME, AIRFLOW_PASSWORD)

    if args.monitor:
        run_monitor(airflow_client, interval=args.interval)
        return

    # Select LLM based on available keys
    llm = None
    if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT:
        # print(f"Using Azure OpenAI...") # Reduce noise
        
        llm = AzureChatOpenAI(
            azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
            openai_api_version=AZURE_OPENAI_API_VERSION,
            temperature=1
        )
        
    elif GOOGLE_API_KEY:
        print("Using Google Gemini (Free Tier available)...")
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
    elif OPENAI_API_KEY:
        print("Using OpenAI GPT-4...")
        llm = ChatOpenAI(temperature=0, model="gpt-4")
    else:
        print("Error: No API Key found.")
        print("Please set AZURE_OPENAI_API_KEY, GOOGLE_API_KEY, or OPENAI_API_KEY in your .env file.")
        return

    # Define Tools
    def list_dags_tool(*args, **kwargs):
        """List all available DAGs in Airflow."""
        try:
            dags = airflow_client.list_dags()
            return [dag['dag_id'] for dag in dags['dags']]
        except Exception as e:
            return f"Error listing DAGs: {str(e)}"

    def restart_dag_tool(dag_id_query: str):
        """
        Restart the most recent failed run of a DAG. 
        Input should be the dag_id (e.g., 'sale_analytics').
        """
        try:
            dag_id = dag_id_query.strip()
            runs = airflow_client.get_dag_runs(dag_id)
            if not runs['dag_runs']:
                return f"No runs found for DAG {dag_id}"
            
            failed_run = next((run for run in runs['dag_runs'] if run['state'] == 'failed'), None)
            
            if not failed_run:
                return f"No failed runs found for DAG {dag_id}. Last run state: {runs['dag_runs'][0]['state']}"
            
            airflow_client.clear_task_instances(dag_id, failed_run['dag_run_id'])
            return f"Successfully triggered restart for DAG run {failed_run['dag_run_id']} of DAG {dag_id}"
            
        except Exception as e:
            return f"Error restarting DAG: {str(e)}"

    tools = [
        Tool(
            name="ListDAGs",
            func=list_dags_tool,
            description="Useful for finding the exact names of available DAGs."
        ),
        Tool(
            name="RestartDAG",
            func=restart_dag_tool,
            description="Useful for restarting a specific DAG. Input should be the dag_id."
        )
    ]
    
    # Define Prompt for Tools Agent
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

    # Handle CLI Query or Interactive Mode
    if args.query:
        user_input = " ".join(args.query)
        # print(f"Running command: {user_input}")
        try:
            response = agent_executor.invoke({"input": user_input})
            print(f"Agent: {response['output']}")
        except Exception as e:
            print(f"Error: {e}")
        return

    # Interactive Loop
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
