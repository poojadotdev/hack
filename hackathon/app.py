import os
import uuid
import json
import concurrent.futures
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from anthropic import Anthropic
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from PIL import Image
from docx import Document

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "devkey")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
UPLOAD_FOLDER = "uploads"
STORY_FOLDER = "stories"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STORY_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

client = Anthropic(api_key=ANTHROPIC_API_KEY)

def ask_claude(prompt, max_tokens=1000):
    try:
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=max_tokens,
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}]
        )
        return ''.join(block.text for block in response.content if hasattr(block, "text"))
    except Exception as e:
        return f"Claude API error: {e}"

def extract_text(file_path):
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    if ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    elif ext == ".docx":
        return "\n".join([p.text for p in Document(file_path).paragraphs])
    elif ext in [".png", ".jpg", ".jpeg"]:
        return f"[Image uploaded: {os.path.basename(file_path)}]"
    return ""

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        reflections = {
            "early_memory": request.form.get("early_memory", ""),
            "turning_point": request.form.get("turning_point", ""),
            "regret": request.form.get("regret", ""),
            "fear": request.form.get("fear", ""),
            "purpose": request.form.get("purpose", ""),
            "legacy": request.form.get("legacy", ""),
            "life_lesson": request.form.get("life_lesson", ""),
            "mentor_impact": request.form.get("mentor_impact", ""),
            "breakthrough_moment": request.form.get("breakthrough_moment", ""),
            "message_to_young_self": request.form.get("message_to_young_self", "")
        }

        uploaded_files = request.files.getlist("file")
        extra_text = ""

        for file in uploaded_files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(path)
                extra_text += "\n\n" + extract_text(path)

        combined_text = "\n\n".join([f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in reflections.items()]) + extra_text

        prompts = {
            "cover": "You are a professional autobiographer. Create a compelling title and short intro paragraph.\nFormat:\nTitle: <Autobiography Title>\n\nIntroduction: <1 paragraph>",
            "index": "Generate a 5-7 chapter index with titles and 1-line descriptions.\nFormat:\nChapter 1: <Title> - <Summary>",
            "chapter": "Write Chapter 1 of the autobiography in 1st person.\nMake it vivid, emotional, and narrative style. Length: 500–800 words.",
            "linkedin": 
                "You are a professional career storyteller. Based on the user's personal reflections, "
                "generate a professional summary that could appear on their LinkedIn profile.\n\n"
                "The tone should be confident, reflective, and authentic — balancing personal growth with professional value.\n"
                "Write in the first person and keep it under 800 words.\n\n"
                "Structure:\n"
                "- A strong opening hook that captures curiosity\n"
                "- 3–5 paragraphs highlighting their journey, pivotal skills, lessons learned, and values\n"
                "- A closing statement that aligns purpose with professional mission\n\n"
                "Use plain, engaging language that would connect well with recruiters, collaborators, and fellow professionals.\n\n"
                "USER INPUT:\n{combined_text}",
            "captions": "Generate 5 short Instagram/Twitter-style captions (<100 characters each)."
        }

        limits = {
            "cover": 400, "index": 500, "chapter": 900,
            "linkedin": 700, "captions": 250
        }

        prompts = {k: v + f"\n\nLIFE EVENTS:\n{combined_text}" for k, v in prompts.items()}
        token = str(uuid.uuid4())

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_key = {
                executor.submit(ask_claude, prompts[key], limits[key]): key for key in prompts
            }
            results = {
                future_to_key[future]: future.result() for future in concurrent.futures.as_completed(future_to_key)
            }

        with open(os.path.join(STORY_FOLDER, f"{token}.json"), "w", encoding="utf-8") as f:
            json.dump(results, f)

        return redirect(url_for("view_story", token=token))

    return render_template("index.html")

@app.route("/story/<token>")
def view_story(token):
    path = os.path.join(STORY_FOLDER, f"{token}.json")
    if not os.path.exists(path):
        return "Story not found", 404
    with open(path, "r", encoding="utf-8") as f:
        results = json.load(f)

    # Ordered display keys for structured rendering
    ordered_keys = ["cover", "chapter", "index", "linkedin", "captions"]
    ordered_results = {key: results.get(key, "") for key in ordered_keys if key in results}

    return render_template("book.html", results=ordered_results, token=token, ordered_keys=ordered_keys, center_text=True)

@app.route("/api/story/<token>")
def api_story(token):
    path = os.path.join(STORY_FOLDER, f"{token}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Story not found"}), 404
    with open(path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.route("/download/<token>")
def download_story(token):
    path = os.path.join(STORY_FOLDER, f"{token}.json")
    if not os.path.exists(path):
        return "Story not found", 404
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    file_path = os.path.join(STORY_FOLDER, f"{token}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        for section, content in data.items():
            f.write(f"\n\n=== {section.upper()} ===\n{content}\n")

    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
