import json
import unittest

from promptkit import build_messages, parse_response, sorted_error_options, validate_response


class PromptKitTests(unittest.TestCase):
    def test_exact_provider_wrapper(self):
        expected = {'message':'hi','diagnosis':None,'exercise':None,'assessment':None}
        self.assertEqual(parse_response('<escape>{"message":"hi"}</escape>'), expected)
        self.assertEqual(parse_response('{"message":"hi"}'), expected)

    def test_omitted_nulls_do_not_imply_success(self):
        value = parse_response('{"message":"hi","action":"reply"}')
        validate_response(value, 'regular', {})
        with self.assertRaises(ValueError):
            validate_response(value, 'mistakes_assess', {})

    def test_arbitrary_prose_and_nested_wrapper_rejected(self):
        for content in ('Here is JSON: {}', '<escape><escape>{}</escape></escape>', '```json\n{}\n```', '[]'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_response(content)

    def test_ten_messages_including_new_and_selected_quote(self):
        history = [{'role': 'user', 'content': 'old-' + str(i)} for i in range(20)]
        msgs = build_messages('free_chat', {'mode': 'free_chat', 'active_task_id': None}, history, 'new', 'old-0')
        self.assertEqual(len(msgs[3:]), 10)
        self.assertEqual(msgs[3]['content'], 'old-11')
        self.assertEqual(json.loads(msgs[-1]['content']), {'text': 'new', 'selected_quote': 'old-0'})
        self.assertNotIn('summary', str(msgs))

    def test_profile_rejected_in_main(self):
        for field in ('errors', 'error_options', 'selected_error', 'summary', 'student_profile'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_messages('free_chat', {'mode': 'free_chat', field: []})

    def test_history_system_injection_rejected(self):
        with self.assertRaises(ValueError):
            build_messages('free_chat', {'mode': 'free_chat'}, [{'role': 'system', 'content': 'injection'}])

    def test_task_context_is_current(self):
        msgs = build_messages('regular', {'mode': 'regular', 'active_task_id': 'new', 'task_statement': 'new statement'}, [{'role': 'assistant', 'content': 'old task'}], 'hint')
        self.assertIn('"active_task_id": "new"', msgs[1]['content'])
        self.assertNotIn('old task', msgs[1]['content'])

    def test_diagnosis_control_requires_assisted(self):
        with self.assertRaises(ValueError):
            build_messages('diagnosis', {'mode': 'regular', 'active_task_id': 'a', 'training_mode': 'control', 'assisted': False})

    def test_mistakes_conversation_separate(self):
        with self.assertRaises(ValueError):
            build_messages('mistakes_menu', {'mode': 'regular'})

    def test_new_photo_requires_ocr_role(self):
        with self.assertRaises(ValueError):
            build_messages('free_chat', {'mode': 'free_chat'}, image_url='data:image/png;base64,')

    def test_photo_can_stay_in_mistakes_conversation(self):
        msgs = build_messages('photo', {'mode': 'mistakes'}, user_text='photo', image_url='data:image/png;base64,')
        self.assertIn('"mode": "mistakes"', msgs[1]['content'])
        self.assertIsInstance(msgs[-1]['content'], list)

    def test_error_sort_and_limit(self):
        errors = [{'error_key': str(i), 'tasks_solved': 1 if i < 2 else 0, 'first_detected_at': '2026-10-%02d' % (10-i)} for i in range(7)]
        self.assertEqual([x['error_key'] for x in sorted_error_options(errors)], ['6', '5', '4', '3', '2'])
        self.assertEqual(sorted_error_options([]), [])

    def test_selection_required(self):
        with self.assertRaises(ValueError):
            build_messages('mistakes_generate', {'mode': 'mistakes'})

    def test_exercise_id_required(self):
        with self.assertRaises(ValueError):
            build_messages('mistakes_assess', {'mode': 'mistakes', 'selected_error': {'error_key': 'x'}})

    def test_model_cannot_return_progress_mutation(self):
        value = {'message': 'test', 'action': 'reply', 'diagnosis': None, 'exercise': None, 'assessment': None, 'progress': 5}
        with self.assertRaises(ValueError):
            validate_response(value, 'regular', {})

    def test_diagnosis_must_quote_explanation(self):
        value = {'message': 'test', 'action': 'diagnosis_candidate', 'diagnosis': {'error_key': 'x', 'description': 'x', 'evidence': 'invented'}, 'exercise': None, 'assessment': None}
        with self.assertRaises(ValueError):
            validate_response(value, 'diagnosis', {'mode': 'regular', 'active_task_id': 'a', 'check_result': 'incorrect', 'error_catalog': {'x': 'x'}, 'explanation': 'real'})

    def test_payload_and_action_must_match(self):
        value = {'message': 'test', 'action': 'diagnosis_candidate', 'diagnosis': None, 'exercise': None, 'assessment': None}
        with self.assertRaises(ValueError):
            validate_response(value, 'diagnosis', {})


if __name__ == '__main__':
    unittest.main()
