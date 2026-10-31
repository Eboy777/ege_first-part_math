"""Synthetic provider smoke check; no student content or credential output."""
from learning.ai_provider import complete,AIUnavailable
from prompts.promptkit import build_messages
ctx={'user_id':'deployment-check','mode':'free_chat','active_task_id':None}
try:
    value=complete('free_chat',ctx,build_messages('free_chat',ctx,user_text='Помоги понять теорему Пифагора.'))
    print('Live AI API:',bool(value.get('message')))
except AIUnavailable:
    print('Live AI API: unavailable')
    raise SystemExit(1)
