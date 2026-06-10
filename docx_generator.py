import os
import re

import docx
from docx.shared import Pt


def sanitize_filename(title):
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", title)
    return cleaned.replace(" ", "_").strip("_") or "quiz"


def get_output_dir():
    return "/tmp" if os.getenv("VERCEL") else os.getcwd()


def build_question_text(question):
    return question["pertanyaan"]


def set_paragraph_spacing(paragraph, after=0, before=0):
    paragraph_format = paragraph.paragraph_format
    paragraph_format.space_after = Pt(after)
    paragraph_format.space_before = Pt(before)


def add_indented_paragraph(document, text, left_indent_pt=18):
    paragraph = document.add_paragraph(text)
    paragraph.paragraph_format.left_indent = Pt(left_indent_pt)
    set_paragraph_spacing(paragraph, after=0)
    return paragraph


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
        question_paragraph = document.add_paragraph(style="List Number")
        question_paragraph.add_run(build_question_text(question))
        set_paragraph_spacing(question_paragraph, after=4)

        if question["tipe"].lower() == "pg":
            for option in question["pilihan"]:
                add_indented_paragraph(document, option, left_indent_pt=24)
        else:
            add_indented_paragraph(
                document,
                "Jawaban: ...................................................................................................."
            )
        document.add_paragraph("")

    questions_filename = f"{sanitize_filename(title)}_soal.docx"
    questions_path = os.path.join(output_dir, questions_filename)
    document.save(questions_path)
    return os.path.abspath(questions_path)


def generate_answer_key_docx(title, questions_list, output_dir):
    document = docx.Document()
    document.add_heading(f"Kunci Jawaban - {title}", 0)
    has_answer_key = any((question.get("kunci_jawaban") or "").strip() for question in questions_list)

    if not has_answer_key:
        document.add_paragraph("Dokumen ini tidak memiliki kunci jawaban karena konten dibuat sebagai survey/non-quiz.")

    for index, question in enumerate(questions_list, 1):
        answer_key = question.get("kunci_jawaban", "").strip()
        explanation = (question.get("penjelasan") or "").strip()

        if question["tipe"].lower() == "pg":
            resolved_answer = resolve_answer_option(question)
            if resolved_answer:
                answer_label = resolved_answer
            else:
                answer_label = answer_key or "-"
        else:
            if has_answer_key:
                answer_label = "Penilaian manual oleh guru."
            else:
                answer_label = "Tidak digunakan."

        answer_paragraph = document.add_paragraph()
        answer_paragraph.add_run(f"{index}. {answer_label}")
        set_paragraph_spacing(answer_paragraph, after=2)

        if explanation:
            add_indented_paragraph(document, f"Penjelasan: {explanation}")

        document.add_paragraph("")

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
