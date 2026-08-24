import os
from flask import Flask, request, jsonify, render_template
import pymysql
from pymysql.cursors import DictCursor

app = Flask(__name__)

# --- DB connection config (pulled from environment variables) ---
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "taskdb")
DB_PORT = int(os.environ.get("DB_PORT", 3306))


def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        cursorclass=DictCursor,
        connect_timeout=5,
    )


def init_db():
    """Create the tasks table if it doesn't exist yet."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        conn.commit()
    finally:
        conn.close()


# --- Health check endpoint (used by the ALB target group later) ---
@app.route("/health")
def health():
    try:
        conn = get_connection()
        conn.close()
        return jsonify(status="healthy"), 200
    except Exception as e:
        return jsonify(status="unhealthy", error=str(e)), 500


# --- Web UI ---
@app.route("/")
def index():
    return render_template("index.html")


# --- CRUD API ---

@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC")
            tasks = cursor.fetchall()
        return jsonify(tasks)
    finally:
        conn.close()


@app.route("/api/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            task = cursor.fetchone()
        if task is None:
            return jsonify(error="Task not found"), 404
        return jsonify(task)
    finally:
        conn.close()


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json(force=True)
    title = data.get("title")
    description = data.get("description", "")

    if not title:
        return jsonify(error="Title is required"), 400

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO tasks (title, description) VALUES (%s, %s)",
                (title, description),
            )
        conn.commit()
        new_id = cursor.lastrowid
        return jsonify(id=new_id, title=title, description=description, completed=False), 201
    finally:
        conn.close()


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.get_json(force=True)
    title = data.get("title")
    description = data.get("description")
    completed = data.get("completed")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            existing = cursor.fetchone()
            if existing is None:
                return jsonify(error="Task not found"), 404

            cursor.execute(
                """
                UPDATE tasks
                SET title = %s, description = %s, completed = %s
                WHERE id = %s
                """,
                (
                    title if title is not None else existing["title"],
                    description if description is not None else existing["description"],
                    completed if completed is not None else existing["completed"],
                    task_id,
                ),
            )
        conn.commit()
        return jsonify(message="Task updated"), 200
    finally:
        conn.close()


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            existing = cursor.fetchone()
            if existing is None:
                return jsonify(error="Task not found"), 404

            cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        conn.commit()
        return jsonify(message="Task deleted"), 200
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
