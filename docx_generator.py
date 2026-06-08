import os
import re

import docx


def sanitize_filename(title):
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", title)
    return cleaned.replace(" ", "_").strip("_") or "quiz"


def get_output_dir():
    return "/tmp" if os.getenv("VERCEL") else os.getcwd()


def build_question_text(question):
    return question["pertanyaan"]


def resolve_answer_option(question):
    answer_key = (question.get("kunci_jawaban") or "").strip().upper()
    if not answer_key:
        return ""

    for option in question.get("pilihan", []):
        cleaned_option = option.strip()
        prefix = cleaned_option.split(".", 1)[0].split(")", 1)[0].strip().upper()
        if prefix == answer_key or cleaned_option.upper() == answer_key:
            return cleaned_option
    return answer_key


def generate_questions_docx(title, questions_list, output_dir):
    document = docx.Document()
    document.add_heading(title, 0)

    for question in questions_list:
        document.add_paragraph(build_question_text(question), style="List Number")

        if question["tipe"].lower() == "pg":
            for option in question["pilihan"]:
                document.add_paragraph(option, style="List Bullet")
        else:
            document.add_paragraph(
                "Jawaban: ...................................................................................................."
            )

    questions_filename = f"{sanitize_filename(title)}_soal.docx"
    questions_path = os.path.join(output_dir, questions_filename)
    document.save(questions_path)
    return os.path.abspath(questions_path)


def generate_answer_key_docx(title, questions_list, output_dir):
    document = docx.Document()
    document.add_heading(f"Kunci Jawaban - {title}", 0)

    for question in questions_list:
        document.add_paragraph(build_question_text(question), style="List Number")
        points = question.get("poin", 1)
        answer_key = question.get("kunci_jawaban", "").strip()

        if question["tipe"].lower() == "pg":
            resolved_answer = resolve_answer_option(question)
            if resolved_answer:
                document.add_paragraph(f"Kunci Jawaban: {resolved_answer}")
            else:
                document.add_paragraph(f"Kunci Jawaban: {answer_key or '-'}")
        else:
            document.add_paragraph("Kunci Jawaban: Penilaian manual oleh guru.")
        document.add_paragraph(f"Poin: {points}")

    answer_key_filename = f"{sanitize_filename(title)}_kunci_jawaban.docx"
    answer_key_path = os.path.join(output_dir, answer_key_filename)
    document.save(answer_key_path)
    return os.path.abspath(answer_key_path)


def generate_docx_file(title, questions_list):
    """Membuat dua file Word: naskah soal dan kunci jawaban."""
    if not isinstance(questions_list, list):
        raise ValueError("Data soal untuk file Word tidak valid.")

    output_dir = get_output_dir()
    questions_path = generate_questions_docx(title, questions_list, output_dir)
    answer_key_path = generate_answer_key_docx(title, questions_list, output_dir)

    return {
        "questions_file_path": questions_path,
        "answer_key_file_path": answer_key_path
    }
