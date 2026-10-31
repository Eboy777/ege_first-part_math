import json
import tempfile
from io import StringIO
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from .models import TaskType, Candidate, BankTask, Progress
from .answers import normalize_answer, answer_matches


class BankTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog_2026', stdout=StringIO())
        cls.user = get_user_model().objects.create_user(username='bank-qa')

    def task(self, type_id='1.1', **changes):
        t = TaskType.objects.get(type_id=type_id)
        c = Candidate.objects.create(source_url='https://example.org/licensed', source_task_id='qa',source='TEST FIXTURE',task_type=t,rights_status='approved',license_or_permission='TEST ONLY')
        data=dict(id='qa',candidate=c,task_type=t,statement='TEST FIXTURE',answer='0.5',status='published',answer_verified=True,verification_notes='TEST ONLY',family_key='test-family')
        data.update(changes)
        return BankTask(**data)

    def test_catalog_and_seed_preserve_progress(self):
        t=TaskType.objects.get(type_id='1.1')
        p=Progress.objects.create(user=self.user,task_type=t,completed=4)
        call_command('seed_catalog_2026',stdout=StringIO())
        p.refresh_from_db()
        self.assertEqual(p.completed,4)
        self.assertEqual(TaskType.objects.filter(number__exam_id='ege_profile_2026').count(),56)
        self.assertEqual(Candidate.objects.count(),41)
        self.assertEqual(set(TaskType.objects.filter(type_id__isnull=False).values_list('number__number',flat=True)),set(range(1,13)))

    def test_pending_rights_block_even_draft(self):
        t=self.task(status='draft'); t.candidate.rights_status='pending'
        with self.assertRaises(ValidationError):t.full_clean(exclude=['content_hash'])

    def test_graph_requires_image(self):
        t=self.task('11.1')
        with self.assertRaises(ValidationError):t.full_clean(exclude=['content_hash'])

    def test_answer_verification_required(self):
        t=self.task(answer_verified=False)
        with self.assertRaises(ValidationError):t.full_clean(exclude=['content_hash'])

    def test_path_traversal_and_missing_images_rejected(self):
        for name in ['/assets/tasks/qa/../../secret.key','/assets/tasks/qa/missing.png']:
            t=self.task() if name.endswith('secret.key') else t
            t.image_paths=[name]
            with self.assertRaises(ValidationError):t.full_clean(exclude=['content_hash'])

    def test_duplicate_family_rejected(self):
        t=self.task();t.full_clean(exclude=['content_hash']);t.save()
        clone=BankTask(id='clone',candidate=t.candidate,task_type=t.task_type,statement='SECOND TEST FIXTURE',answer='1',family_key=t.family_key)
        with self.assertRaises(ValidationError):clone.full_clean(exclude=['content_hash'])

    def test_numeric_equivalence(self):
        t=self.task()
        for value in ['0,5','0.50','1/2']:
            self.assertTrue(answer_matches(t,value))
        self.assertFalse(answer_matches(t,'0.500001'))
        for value in ['1/0','nan','1e1000','2+2','']:
            self.assertIsNone(normalize_answer(value))

    def test_import_pending_is_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest=Path(directory)/'pending.json'
            manifest.write_text(json.dumps([{'type_id':'1.1','exam':'ege_profile_2026','number':1,'rights_status':'pending'}]))
            with self.assertRaises(CommandError):call_command('import_bank',manifest)
        self.assertEqual(BankTask.objects.count(),0)

    def test_catalog_pages_render(self):
        self.client.force_login(self.user)
        paths=['/','/bank']+[f'/exam/ege_profile_2026/tasks/{n}' for n in range(1,13)]+[f'/exam/ege_profile_2026/types/{slug}' for slug in TaskType.objects.filter(type_id__isnull=False).values_list('slug',flat=True)]
        for path in paths:
            self.assertEqual(self.client.get(path).status_code,200,path)

    def test_report_has_all_types(self):
        with tempfile.TemporaryDirectory() as directory:
            call_command('bank_report',output=Path(directory),stdout=StringIO())
            self.assertEqual(len((Path(directory)/'coverage.csv').read_text().splitlines()),57)

    def test_approved_import_and_duplicate_rollback(self):
        row = dict(id='qa-import',exam='ege_profile_2026',number=1,type_id='1.1',source='TEST FIXTURE',source_url='https://example.org/licensed',source_task_id='import-qa',rights_status='approved',license_or_permission='TEST ONLY',statement='IMPORT TEST FIXTURE',answer='1',accepted_answers=[],image_paths=[],family_key='import-family',answer_verified=True,verification_notes='TEST ONLY',status='published')
        with tempfile.TemporaryDirectory() as directory:
            manifest=Path(directory)/'approved.json'
            manifest.write_text(json.dumps([row]))
            call_command('import_bank',manifest,stdout=StringIO())
            self.assertEqual(BankTask.objects.count(),1)
            # First insertion must also roll back if a later row is a duplicate.
            fresh={**row,'id':'qa-second','source_task_id':'second','statement':'SECOND IMPORT FIXTURE','family_key':'second-family'}
            manifest.write_text(json.dumps([fresh,row]))
            with self.assertRaises(CommandError):call_command('import_bank',manifest,stdout=StringIO())
            self.assertEqual(BankTask.objects.count(),1)

    def test_twenty_per_type_limit(self):
        task=self.task();task.save()
        for i in range(1,20):
            c=Candidate.objects.create(source_url='https://example.org/licensed',source_task_id=f'cap-{i}',source='TEST ONLY',task_type=task.task_type,rights_status='approved',license_or_permission='TEST ONLY')
            BankTask(id=f'cap-{i}',candidate=c,task_type=task.task_type,statement=f'TEST FIXTURE {i}',answer='1',answer_verified=True,verification_notes='TEST ONLY',family_key=f'cap-{i}',status='published').save()
        task.pk='cap-over';task.family_key='cap-over';task.statement='CAP OVER TEST FIXTURE'
        with self.assertRaises(ValidationError):task.full_clean(exclude=['content_hash'])

    def test_html_rejects_script_and_remote_images(self):
        from .bank_validation import SourceHTMLValidator
        for value in ['<script>alert(1)</script>','<img src="https://example.org/a.png" class="illustration">','<p onclick="alert(1)">TEST</p>']:
            with self.assertRaises(ValidationError):SourceHTMLValidator([]).feed(value)
        SourceHTMLValidator(['/assets/tasks/qa/a.png']).feed('<p>TEST <img src="/assets/tasks/qa/a.png" class="formula" alt="TEST"></p>')

    def test_svg_rejects_executable_content(self):
        from .bank_validation import verify_svg
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.svg'
            for content in ['<svg><script>test</script></svg>','<svg><use href="https://example.org/a.svg"/></svg>','<svg onload="test"/>']:
                path.write_text(content)
                with self.assertRaises(ValueError):verify_svg(path)
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><defs><path id="a" d="M0 0L1 1"/></defs><use href="#a"/></svg>')
            verify_svg(path)
