import os
import logging
import time
import threading
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import StructuredTool
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from airflow_client import AirflowClient
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AIRFLOW_URL = os.getenv("AIRFLOW_URL", "https://airflow.ducttdevops.com")
AIRFLOW_USERNAME = os.getenv("AIRFLOW_USERNAME", "admin")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "admin")

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

# Initialize Airflow client
airflow_client = AirflowClient(AIRFLOW_URL, AIRFLOW_USERNAME, AIRFLOW_PASSWORD)

# Initialize Azure OpenAI
llm = AzureChatOpenAI(
    azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
    openai_api_version=AZURE_OPENAI_API_VERSION,
    temperature=1
)

# Monitor state
monitor_state = {
    'running': False,
    'interval': 300,
    'logs': [],
    'thread': None,
    'chat_id': None  # Store chat ID for sending notifications
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

# Define tools
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

# Create tools list
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

# Create agent
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant capable of managing Airflow DAGs."),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_openai_tools_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True)

# Telegram bot handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = (
        "Welcome to the Airflow AI Agent Bot!\n\n"
        "I can help you manage your Airflow DAGs. Here's what I can do:\n"
        "- List all available DAGs\n"
        "- Get DAG run history and status\n"
        "- Restart failed DAG runs\n"
        "- Trigger new DAG runs\n"
        "- Monitor and auto-restart failed DAGs\n\n"
        "Commands:\n"
        "/start - Show this welcome message\n"
        "/help - Show help and examples\n"
        "/monitor_start - Start monitoring DAGs (default: 5 min interval)\n"
        "/monitor_stop - Stop monitoring\n"
        "/monitor_status - Check monitoring status\n\n"
        "You can also chat with me in natural language!"
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_message = (
        "Airflow AI Agent Bot - Help\n\n"
        "Available commands:\n"
        "/start - Start the bot and see welcome message\n"
        "/help - Show this help message\n"
        "/monitor_start [interval] - Start monitoring (interval in seconds, default: 300)\n"
        "/monitor_stop - Stop monitoring\n"
        "/monitor_status - Check monitoring status and recent logs\n\n"
        "You can ask me anything about your Airflow DAGs in natural language!\n\n"
        "Examples:\n"
        "- 'What DAGs are available?'\n"
        "- 'Show me the last runs of my_dag'\n"
        "- 'Trigger a new run of my_dag'\n"
        "- 'Restart the failed run manual__2024-11-28T00:00:00+00:00 of my_dag'\n\n"
        "Monitoring:\n"
        "When monitoring is active, I will automatically check all DAGs and restart any failed runs."
    )
    await update.message.reply_text(help_message)

async def monitor_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the monitoring service."""
    try:
        # Get interval from command args, default to 300 seconds
        interval = 300
        if context.args and len(context.args) > 0:
            try:
                interval = int(context.args[0])
                if interval < 60:
                    await update.message.reply_text("Interval must be at least 60 seconds.")
                    return
            except ValueError:
                await update.message.reply_text("Invalid interval. Using default 300 seconds.")
        
        if monitor_state['running']:
            await update.message.reply_text("Monitor is already running.")
            return
        
        monitor_state['running'] = True
        monitor_state['interval'] = interval
        monitor_state['chat_id'] = update.effective_chat.id
        monitor_state['logs'] = [{
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': f'Monitor started (interval: {interval}s)',
            'type': 'success'
        }]
        
        monitor_state['thread'] = threading.Thread(target=monitor_loop, daemon=True)
        monitor_state['thread'].start()
        
        await update.message.reply_text(
            f"Monitor started successfully!\n"
            f"Interval: {interval} seconds\n"
            f"I will check all DAGs and automatically restart failed runs.\n"
            f"Use /monitor_status to check status or /monitor_stop to stop."
        )
    except Exception as e:
        await update.message.reply_text(f"Error starting monitor: {str(e)}")

async def monitor_stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the monitoring service."""
    try:
        if not monitor_state['running']:
            await update.message.reply_text("Monitor is not running.")
            return
        
        monitor_state['running'] = False
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': 'Monitor stopped',
            'type': 'info'
        }
        monitor_state['logs'].append(log_entry)
        
        await update.message.reply_text("Monitor stopped successfully.")
    except Exception as e:
        await update.message.reply_text(f"Error stopping monitor: {str(e)}")

async def monitor_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get monitoring status."""
    try:
        status = "RUNNING" if monitor_state['running'] else "STOPPED"
        interval = monitor_state['interval']
        
        message = f"Monitor Status: {status}\n"
        if monitor_state['running']:
            message += f"Check Interval: {interval} seconds\n\n"
        
        # Get last 10 logs
        recent_logs = monitor_state['logs'][-10:]
        if recent_logs:
            message += "Recent Activity:\n"
            for log in recent_logs:
                message += f"[{log['timestamp']}] {log['message']}\n"
        else:
            message += "No activity logged yet."
        
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Error getting monitor status: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages and process them through the agent."""
    user_message = update.message.text
    user_name = update.effective_user.first_name
    
    logger.info(f"Received message from {user_name}: {user_message}")
    
    # Send typing indicator
    await update.message.chat.send_action(action="typing")
    
    try:
        # Process message through the agent
        response = agent_executor.invoke({"input": user_message})
        reply = response['output']
        
        # Split long messages if needed (Telegram has a 4096 character limit)
        if len(reply) > 4000:
            # Split into chunks
            chunks = [reply[i:i+4000] for i in range(0, len(reply), 4000)]
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(reply)
            
        logger.info(f"Sent response to {user_name}")
        
    except Exception as e:
        error_message = f"Sorry, I encountered an error: {str(e)}"
        logger.error(f"Error processing message: {str(e)}")
        await update.message.reply_text(error_message)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        print("Error: Please set TELEGRAM_BOT_TOKEN in your .env file")
        return
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("monitor_start", monitor_start_command))
    application.add_handler(CommandHandler("monitor_stop", monitor_stop_command))
    application.add_handler(CommandHandler("monitor_status", monitor_status_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("Starting Telegram bot...")
    print("Telegram bot is running! Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
