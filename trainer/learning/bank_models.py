import hashlib
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Candidate(models.Model):
    source_url = models.URLField(max_length=1000)
    source_task_id = models.CharField(max_length=200)
    source = models.CharField(max_length=200)
    task_type = models.ForeignKey('TaskType', null=True, blank=True, on_delete=models.PROTECT, related_name='candidates')
    rights_status = models.CharField(max_length=16, default='pending', choices=[('pending','Не подтверждены'),('approved','Подтверждены'),('denied','Запрещены')])
    license_or_permission = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source_url','source_task_id'], name='unique_source_candidate')]


class BankTask(models.Model):
    id = models.SlugField(primary_key=True)
    candidate = models.OneToOneField(Candidate, on_delete=models.PROTECT, related_name='imported_task')
    task_type = models.ForeignKey('TaskType', on_delete=models.PROTECT, related_name='bank_tasks')
    statement = models.TextField()
    statement_format = models.CharField(max_length=24, default='text', choices=[('text','Текст'),('original_image','Оригинальный фрагмент'),('source_html','Условие с исходными формулами')])
    answer = models.CharField(max_length=200)
    accepted_answers = models.JSONField(default=list, blank=True)
    image_paths = models.JSONField(default=list, blank=True)
    requires_illustration = models.BooleanField(default=False)
    answer_verified = models.BooleanField(default=False)
    illustration_verified = models.BooleanField(default=False)
    verification_notes = models.TextField(blank=True)
    family_key = models.CharField(max_length=200, unique=True)
    content_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, default='draft', choices=[('draft','Черновик'),('published','Опубликована')])

    def clean(self):
        errors = []
        c = self.candidate
        if c.rights_status != 'approved' or not c.license_or_permission.strip():
            errors.append('Для локального импорта требуется подтверждённое право на текст и изображения.')
        if c.task_type_id != self.task_type_id:
            errors.append('Тип кандидата и импортированной задачи должен совпадать.')
        if not self.statement.strip() or not self.answer.strip():
            errors.append('Условие и ответ обязательны.')
        if not isinstance(self.accepted_answers, list) or not all(isinstance(a, str) for a in self.accepted_answers):
            errors.append('accepted_answers должен быть списком строк.')
        if not isinstance(self.image_paths, list):
            errors.append('image_paths должен быть списком.')
        else:
            for name in self.image_paths:
                prefix = f'/assets/tasks/{self.pk}/'
                root = Path(settings.TASK_ASSET_ROOT).resolve()
                path = (root / str(name).removeprefix('/assets/tasks/')).resolve()
                if not str(name).startswith(prefix) or not path.is_relative_to(root) or not path.is_file():
                    errors.append('Не найден безопасный локальный файл иллюстрации.')
                    continue
                try:
                    if path.suffix.lower()=='.svg':
                        from .bank_validation import verify_svg
                        verify_svg(path)
                    else:
                        from PIL import Image
                        with Image.open(path) as picture:
                            picture.verify()
                except Exception:
                    errors.append('Изображение повреждено или имеет неподдерживаемый формат.')
        if self.statement_format == 'source_html':
            from .bank_validation import SourceHTMLValidator
            SourceHTMLValidator(self.image_paths).feed(self.statement)
        if self.status == 'published':
            from .answers import normalize_answer
            if normalize_answer(self.answer) is None:
                errors.append('Ответ первой части должен быть корректным числом.')
            if not self.answer_verified or not self.verification_notes.strip():
                errors.append('Нужна сверка ответа с источником и независимая проверка с описанием.')
            if (self.statement_format == 'original_image' or self.requires_illustration or self.task_type.illustration_required) and not self.image_paths:
                errors.append('Отсутствует обязательный рисунок.')
            if self.statement_format == 'source_html' and self.task_type.illustration_required and 'class="illustration"' not in self.statement:
                errors.append('Для этого типа нужна исходная иллюстрация, одной картинки с формулой недостаточно.')
            if self.image_paths and not self.illustration_verified:
                errors.append('Иллюстрации не проверены.')
            peers = BankTask.objects.filter(task_type=self.task_type, status='published').exclude(pk=self.pk)
            if peers.count() >= 20:
                errors.append('Для типа уже опубликовано 20 задач.')
        canonical = ' '.join(self.statement.split())
        if self.statement_format == 'source_html' and not errors:
            from .bank_validation import canonical_source_html
            canonical = canonical_source_html(self.statement, settings.TASK_ASSET_ROOT)
        self.content_hash = hashlib.sha256(canonical.encode()).hexdigest()
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(exclude=['content_hash'])
        self.validate_unique()
        return super().save(*args, **kwargs)
