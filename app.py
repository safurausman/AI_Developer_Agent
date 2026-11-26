import os
import sqlite3
import ast
import operator
import re
from datetime import datetime
from pathlib import Path

import gradio as gr
from google import genai
from google.genai import types

# ---------------- CONFIGURATION ----------------

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("Please set the GEMINI_API_KEY environment variable.")

client = genai.Client(api_key=API_KEY)
DB_PATH = Path(os.getenv("DEVAGENT_DB_PATH", str(Path(__file__).with_name("devagent.db"))))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------- DATABASE ----------------

def get_db_connection():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                information TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        connection.commit()


initialize_database()

# ---------------- AGENT TOOLS ----------------

def calculate(expression: str) -> str:
    """Safely calculate a basic mathematical expression."""
    allowed_operators = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg,
        ast.UAdd: operator.pos, ast.Mod: operator.mod,
    }

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_operators:
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("Exponents greater than 10 are not supported.")
            result = allowed_operators[type(node.op)](left, right)
            if abs(result) > 10**15:
                raise ValueError("The result is too large.")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_operators:
            return allowed_operators[type(node.op)](evaluate(node.operand))
        raise ValueError("Only basic arithmetic is supported.")

    try:
        return str(evaluate(ast.parse(expression, mode="eval").body))
    except Exception as error:
        return f"Calculation error: {error}"


def add_task(title: str) -> str:
    """Save a new task in the persistent task database."""
    title = (title or "").strip()
    if not title:
        return "A task title is required."
    with get_db_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (title, status, created_at) VALUES (?, 'Pending', ?)",
            (title, datetime.now().isoformat(timespec="seconds")),
        )
        task_id = cursor.lastrowid
        connection.commit()
    return f"Task created successfully: ID {task_id}, Title: {title}, Status: Pending."


def get_all_tasks():
    """Return all tasks for display and tool responses."""
    with get_db_connection() as connection:
        return connection.execute(
            "SELECT id, title, status FROM tasks ORDER BY id"
        ).fetchall()


def list_tasks() -> str:
    """List all tasks saved in the database."""
    rows = get_all_tasks()
    if not rows:
        return "No tasks found."
    return "\n".join(
        f"ID: {row['id']} | {row['title']} | Status: {row['status']}"
        for row in rows
    )


def render_tasks_markdown():
    """Render the latest task state in the UI."""
    rows = get_all_tasks()
    if not rows:
        return "No tasks have been created yet."
    lines = ["### Current Tasks"]
    for row in rows:
        status = "✅ Completed" if row['status'] == "Completed" else "⏳ Pending"
        lines.append(f"- **{row['title']}** (ID: {row['id']}) — {status}")
    return "\n".join(lines)


def prepare_task_completion(task_id: int):
    """Validate a completion request; actual confirmation is held in Gradio session state."""
    with get_db_connection() as connection:
        task = connection.execute(
            "SELECT id, title, status FROM tasks WHERE id = ?", (int(task_id),)
        ).fetchone()
    if not task:
        return None, f"Task {task_id} was not found."
    if task["status"] == "Completed":
        return None, f"Task {task_id} ('{task['title']}') is already completed."
    return int(task_id), (
        f"Confirmation required: Task {task_id} ('{task['title']}') is still Pending. "
        "Press **Confirm Task Completion** to complete it, or **Cancel Task Completion** to leave it unchanged."
    )


def confirm_pending_task(task_id):
    """Complete only the task pending in this browser session, then refresh the list."""
    if task_id is None:
        return "There is no pending task completion to confirm. Run a completion request first.", render_tasks_markdown(), None
    with get_db_connection() as connection:
        task = connection.execute(
            "SELECT id, title, status FROM tasks WHERE id = ?", (int(task_id),)
        ).fetchone()
        if task is None:
            status = f"Task {task_id} was not found."
        elif task["status"] == "Completed":
            status = f"Task {task_id} is already completed."
        else:
            connection.execute(
                "UPDATE tasks SET status = 'Completed' WHERE id = ?", (int(task_id),)
            )
            connection.commit()
            status = f"Confirmed. Task {task_id} ('{task['title']}') is now Completed."
    return status, render_tasks_markdown(), None


def cancel_pending_task(task_id):
    """Cancel the pending completion in this browser session without changing the task."""
    if task_id is None:
        status = "There is no pending task completion to cancel."
    else:
        status = f"Cancelled. Task {task_id} was not changed."
    return status, render_tasks_markdown(), None


def remember_information(information: str) -> str:
    """Save information in persistent agent memory when explicitly requested."""
    information = (information or "").strip()
    if not information:
        return "Please provide information to remember."
    with get_db_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO memories (information, created_at) VALUES (?, ?)",
            (information, datetime.now().isoformat(timespec="seconds")),
        )
        memory_id = cursor.lastrowid
        connection.commit()
    return f"Saved to persistent memory (ID {memory_id}): {information}"


def recall_memories(search_term: str = "") -> str:
    """Retrieve saved information from persistent agent memory."""
    search_term = (search_term or "").strip()
    with get_db_connection() as connection:
        if search_term:
            rows = connection.execute(
                "SELECT id, information FROM memories WHERE information LIKE ? "
                "ORDER BY id DESC LIMIT 20",
                (f"%{search_term}%",),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT id, information FROM memories ORDER BY id DESC LIMIT 20"
            ).fetchall()
    if not rows:
        return "No matching memories found."
    return "\n".join(f"Memory {row['id']}: {row['information']}" for row in rows)


def get_current_time() -> str:
    """Get the current local date and time on the server."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


AGENT_TOOLS = [
    calculate, add_task, list_tasks,
    remember_information, recall_memories, get_current_time,
]

SYSTEM_INSTRUCTION = """
You are DevAgent, an intelligent AI Developer Assistant.
- Understand requests and use tools for calculations, tasks, memory, and date/time.
- Break complicated requests into smaller steps and report actual tool results.
- Never claim an action succeeded unless the tool confirms it.
- Task-completion requests are intercepted by the application and stored in per-session Gradio state.
- Never claim a task is completed until the user presses the app's
  "Confirm Task Completion" button and the application reports success.
- Save information only when the user explicitly asks you to remember it.
- Use recall_memories when the user asks what you remember or a saved memory is relevant.
- Never save passwords, API keys, or other secrets.
- Be helpful, accurate, safe, and concise.
"""

# ---------------- AGENT EXECUTION ----------------

def convert_history_to_gemini(history):
    contents = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if isinstance(content, str) and content.strip() and role in ("user", "assistant"):
            contents.append(types.Content(
                role="model" if role == "assistant" else "user",
                parts=[types.Part(text=content)],
            ))
    return contents


def respond(message, history, pending_task_id):
    message = (message or "").strip()
    history = history or []
    if not message:
        return history, history, "", pending_task_id, render_tasks_markdown()

    # Handle completion requests in the Gradio event handler so the pending
    # confirmation is stored in this user's gr.State, not a process-wide global.
    completion_match = re.search(
        r"(?:\bmark\s+(?:task\s*)?(?:#|id\s*)?(?P<marked_id>\d+)\s+(?:as\s+)?(?:completed|complete|done)\b)"
        r"|(?:\b(?:complete|finish)\s+(?:task\s*)?(?:#|id\s*)?(?P<action_id>\d+)\b)",
        message,
        flags=re.IGNORECASE,
    )
    if completion_match:
        requested_id = int(completion_match.group("marked_id") or completion_match.group("action_id"))
        if pending_task_id is not None:
            answer = (
                f"Task {pending_task_id} is already awaiting confirmation. "
                "Please confirm or cancel that request before starting another."
            )
        else:
            pending_task_id, answer = prepare_task_completion(requested_id)
    else:
        try:
            chat = client.chats.create(
                model=MODEL,
                history=convert_history_to_gemini(history),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=AGENT_TOOLS,
                    temperature=0.3,
                ),
            )
            response = chat.send_message(message)
            answer = response.text or "The agent did not return a text response."
        except Exception as error:
            error_text = str(error)
            if "503" in error_text or "UNAVAILABLE" in error_text:
                answer = "Gemini is temporarily busy (503 UNAVAILABLE). Please wait a little and try again."
            elif "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                answer = "The Gemini API rate limit has been reached. Please wait before trying again."
            else:
                answer = f"Agent error: {error_text}"

    updated = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    return updated, updated, "", pending_task_id, render_tasks_markdown()


def run_workflow_demo():
    """Demonstrate the agent's task-to-tool workflow without calling Gemini."""
    request = "Calculate 24 * 3 and report the result."
    # Understand task: identify a calculation request.
    intent = "Calculation request detected"
    # Decide action: select the calculator tool.
    selected_tool = "calculate"
    # Use tool: invoke the same safe calculator used by the agent.
    raw_result = calculate("24 * 3")
    # Process result: validate that the tool returned a numeric value.
    try:
        numeric_result = float(raw_result)
        processed_result = f"{numeric_result:g}"
        final_response = f"24 × 3 = **{processed_result}**"
        outcome = "Success"
    except (TypeError, ValueError):
        processed_result = raw_result
        final_response = f"The calculator returned: {raw_result}"
        outcome = "Handled tool error"

    return (
        "### Agent workflow demonstration\n"
        f"1. **Understand Task:** {request}\n"
        f"2. **Decide Action:** {intent}; selected `{selected_tool}`.\n"
        f"3. **Use Tool:** Called the local calculator.\n"
        f"4. **Process Result:** {processed_result}\n"
        f"5. **Respond:** {final_response}\n\n"
        f"**Outcome:** {outcome}. This demonstration uses the local tool and does not consume Gemini API quota."
    )


# ---------------- USER INTERFACE ----------------

with gr.Blocks() as demo:
    gr.Markdown("""
    # 🤖 DevAgent – AI Developer Assistant
    Your intelligent agent that plans tasks, uses tools, remembers information,
    and manages work safely.
    """)

    chatbot = gr.Chatbot(label="Agent Conversation", height=430)
    history_state = gr.State([])
    pending_task_state = gr.State(None)

    with gr.Row():
        message = gr.Textbox(
            placeholder="Ask DevAgent to calculate, manage tasks, or remember information...",
            label="Your request",
            scale=5,
        )
        send = gr.Button("Run Agent 🚀", variant="primary", scale=1)

    with gr.Row():
        confirm_button = gr.Button("Confirm Task Completion", variant="primary")
        cancel_button = gr.Button("Cancel Task Completion", variant="secondary")

    confirmation_status = gr.Markdown(
        "Task changes require your confirmation using the button above."
    )
    tasks_display = gr.Markdown(render_tasks_markdown())

    gr.Markdown("### 🧰 Available Agent Tools")
    gr.Markdown("""
    - **Calculator** – performs basic mathematical calculations using a restricted AST evaluator.
    - **Task Manager** – creates and lists tasks in SQLite.
    - **Task Completion** – requires an explicit confirmation click before changing task status.
    - **Persistent Memory** – saves and retrieves information in the local SQLite database.
    - **Date & Time** – retrieves the server's current local date and time.
    """)

    gr.Markdown("### 🧪 Complete Agent Workflow Demo")
    gr.Markdown("Run a local demonstration of Understand Task → Decide Action → Use Tool → Process Result → Respond. This test does not call Gemini.")
    workflow_button = gr.Button("Run Local Workflow Demo", variant="secondary")
    workflow_output = gr.Markdown("Click the button to run the five-stage workflow demonstration.")
    workflow_button.click(run_workflow_demo, inputs=[], outputs=[workflow_output])

    with gr.Accordion("📚 Agent Frameworks – Learning Notes", open=False):
        gr.Markdown("""
        | Framework | Main idea | Typical use |
        |---|---|---|
        | **LangChain** | Components for LLM apps, prompts and tool integrations | Building LLM applications with reusable integrations |
        | **LangGraph** | Stateful, graph-based agent workflows | Multi-step workflows with branching, persistence and human approval |
        | **CrewAI** | Role-based collaboration between agents | Coordinating multiple specialized agents |

        **This project:** DevAgent uses a lightweight custom Python agent loop with Gemini function calling, SQLite-backed tools and Gradio session state. It does not currently depend on LangChain, LangGraph or CrewAI.
        """)

    with gr.Accordion("🛡️ Safety Rules and Limitations", open=False):
        gr.Markdown("""
        **Safety controls implemented**
        - Task completion is prepared first and only applied after the user clicks **Confirm Task Completion**.
        - Users can cancel a pending task completion without changing the task.
        - Calculator expressions are parsed with an allowlist of arithmetic operators; arbitrary Python execution is not allowed.
        - SQL values are passed as parameters rather than concatenated into SQL statements.
        - Persistent memory is written only when the user explicitly asks; do not store passwords, API keys or other secrets.
        - Gemini errors such as HTTP 503 and 429 are caught and shown as readable messages.

        **Limitations to understand**
        - Gemini responses and tool selection depend on the external API, model availability, quotas and network connectivity.
        - SQLite memory is local to the configured database file; it is not encrypted or shared across separate deployments by default.
        - The custom agent is a single-agent implementation, not a multi-agent framework.
        - Model output can be incorrect; review important results and approve consequential actions.
        """)

    send.click(
        respond, inputs=[message, history_state, pending_task_state],
        outputs=[chatbot, history_state, message, pending_task_state, tasks_display],
    )
    message.submit(
        respond, inputs=[message, history_state, pending_task_state],
        outputs=[chatbot, history_state, message, pending_task_state, tasks_display],
    )
    confirm_button.click(
        confirm_pending_task,
        inputs=[pending_task_state],
        outputs=[confirmation_status, tasks_display, pending_task_state],
    )
    cancel_button.click(
        cancel_pending_task,
        inputs=[pending_task_state],
        outputs=[confirmation_status, tasks_display, pending_task_state],
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=2).launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        theme=gr.themes.Soft(),
    )
