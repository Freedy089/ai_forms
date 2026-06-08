# docx_generator.py
import os
import docx

def generate_docx_file(title, questions_list):
    """Membuat file Word (.docx) di lokal dengan dukungan PG dan Esai"""
    doc = docx.Document()
    doc.add_heading(title, 0)
    
    for index, q in enumerate(questions_list, 1):
        points = q.get('poin', 1)
        doc.add_paragraph(
            f"{index}. [{q['tipe'].upper()} | {points} poin] {q['pertanyaan']}",
            style='List Number'
        )
        
        if q['tipe'].lower() == 'pg':
            for opt in q['pilihan']:
                doc.add_paragraph(f"   {opt}")
            doc.add_paragraph(f"Kunci Jawaban: {q['kunci_jawaban']}\n")
        else:
            doc.add_paragraph("Jawaban: ....................................................................................................\n")
        
    filename = f"{title}.docx".replace(" ", "_")
    output_dir = "/tmp" if os.getenv("VERCEL") else os.getcwd()
    file_path = os.path.join(output_dir, filename)
    doc.save(file_path)
    return os.path.abspath(file_path)
