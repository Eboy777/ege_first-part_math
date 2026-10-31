import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def method_for(task_type):
    specific=task_type.theory+'\n'+'\n'.join(task_type.example.get('algorithm',[]))
    mapping=json.loads((ROOT/'data'/'method_map_2026.json').read_text())
    filename=mapping.get(task_type.pk) if task_type.number.exam_id=='ege_profile_2026' else None
    if not filename:return specific
    general=(ROOT/'methods'/'2026'/filename).read_text()
    return 'Методика конкретного типа:\n'+specific+'\n\nСправочная методика EduAI по номеру (используй только относящееся к текущему типу):\n'+general
