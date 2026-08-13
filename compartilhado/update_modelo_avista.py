import docx
import re

doc = docx.Document('MODELO DE TERMO DE ACORDO-A VISTA.docx')

replacements = [
    (r"Brasília - DF, 17 de julho de 2026", "Brasília - DF, {{data}}"),
    (r"Processo Judicial:\s*$", "Processo Judicial: {{processo}}"),
    (r"Sr\.\(a\)_________________", "Sr.(a) {{nome_cliente}}"),
    (r"CPF nº ________", "CPF nº {{cpf_cliente}}"),
    (r"endereço: ________________", "endereço: {{endereco}}"),
    (r"CEP:\s*58051420", "CEP: {{cep}}"),
    (r"Email:\s*________", "Email: {{email}}"),
    (r"telefone:__________", "telefone: {{telefone}}"),
    (r"R\$\s*_________\s*\(_________________________\)", "R$ {{valor_divida}}"),
    (r"compentências de _________", "competências de {{competencias}}"),
    (r"R\$\s*_______\s*\(_____________________\)", "R$ {{valor_acordo}}"),
    (r"R\$\s*00000000\s*\(______________________________\)", "R$ {{valor_acordo}}"),
    (r"dia _____________", "dia {{venc_entrada}}"),
    (r"R\$\s*______\s*\(__________________\)\s*de honorários", "R$ {{honorarios}} de honorários"),
    (r"R\$\s*_________\s*\(__________________________\)\s*para a GEAP", "R$ {{valor_geap}} para a GEAP"),
    (r"processo de nº ________________", "processo de nº {{processo}}"),
    (r"____________________________________\s*BENEFICIARIO", "{{nome_cliente}}\nBENEFICIARIO"),
    (r"CPF nº:\s*__________________________________", "CPF nº: {{cpf_cliente}}\n__________________________________")
]

for p in doc.paragraphs:
    text = p.text
    for old, new in replacements:
        text = re.sub(old, new, text)
    if text != p.text:
        p.text = text

doc.save('MODELO DE TERMO DE ACORDO-A VISTA.docx')
print("Model updated!")
