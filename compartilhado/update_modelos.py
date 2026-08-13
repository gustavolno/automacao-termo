"""
Script para atualizar os modelos Word:
1. Adicionar CEP ao lado do endereço no corpo do texto
2. Centralizar nome/CPF da assinatura e remover espaços de indentação
"""
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
import re, copy

def atualizar_modelo(caminho):
    doc = Document(caminho)
    
    for p in doc.paragraphs:
        full_text = p.text
        
        # Substituir "{{endereco}}, Email" por "{{endereco}}, CEP: {{cep}}, Email"
        # ou "{{endereco}} CEP:" por "{{endereco}}, CEP: {{cep}},"
        if "{{endereco}}" in full_text and "{{cep}}" not in full_text:
            for run in p.runs:
                if "{{endereco}}" in run.text:
                    # Adicionar CEP depois do endereço
                    run.text = run.text.replace("{{endereco}}", "{{endereco}}, CEP: {{cep}}")
                    break
        
        # Centralizar os parágrafos de assinatura do beneficiário
        # Linha com underscores (separador de assinatura)
        stripped = full_text.strip()
        if stripped and all(c in '_ \t' for c in stripped):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # Limpar espaços de indentação dos runs
            for run in p.runs:
                run.text = run.text.strip()
            if p.runs:
                p.runs[0].text = "____________________________________"

        # Linha com {{nome_cliente}} (nome do beneficiário na assinatura)
        if "{{nome_cliente}}" in full_text and "CREDORA" not in full_text and "Sr." not in full_text:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.text = run.text.strip()
        
        # Linha com CPF n°: {{cpf_cliente}} na assinatura
        if "{{cpf_cliente}}" in full_text and "Sr." not in full_text and "CREDORA" not in full_text and "brasileiro" not in full_text:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.text = run.text.strip()
    
    doc.save(caminho)
    print(f"Modelo atualizado: {caminho}")

atualizar_modelo("MODELO.docx")
atualizar_modelo("MODELO DE TERMO DE ACORDO-A VISTA.docx")
print("Pronto!")
