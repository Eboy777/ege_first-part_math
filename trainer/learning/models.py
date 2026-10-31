import uuid
from django.conf import settings
from django.db import models

class ExamVersion(models.Model):
    code = models.SlugField(primary_key=True)
    title = models.CharField(max_length=100)
    active = models.BooleanField(default=True)

class Section(models.Model):
    exam = models.ForeignKey(ExamVersion, on_delete=models.CASCADE, related_name='sections')
    slug = models.SlugField()
    title = models.CharField(max_length=100)
    accent = models.CharField(max_length=24)
    position = models.PositiveSmallIntegerField()
    class Meta:
        ordering = ['position']
        constraints = [models.UniqueConstraint(fields=['exam', 'slug'], name='unique_exam_section')]

class ExamNumber(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='numbers')
    exam = models.ForeignKey(ExamVersion, on_delete=models.CASCADE, related_name='numbers')
    number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=150)
    class Meta:
        ordering = ['number']
        constraints = [models.UniqueConstraint(fields=['exam', 'number'], name='unique_exam_number')]

class TaskType(models.Model):
    slug = models.SlugField(primary_key=True)
    number = models.ForeignKey(ExamNumber, on_delete=models.CASCADE, related_name='types')
    title = models.CharField(max_length=150)
    position = models.PositiveSmallIntegerField(default=0)
    type_id = models.CharField(max_length=8, unique=True, null=True, blank=True)
    illustration_policy = models.CharField(max_length=100, blank=True)
    illustration_required = models.BooleanField(default=False)
    theory = models.TextField(blank=True)
    formula = models.CharField(max_length=200, blank=True)
    example = models.JSONField(default=dict)
    method_reference = models.CharField(max_length=250, blank=True)
    class Meta:
        ordering = ['position', 'slug']

class Progress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='training_progress')
    task_type = models.ForeignKey(TaskType, on_delete=models.CASCADE)
    completed = models.PositiveSmallIntegerField(default=0)
    is_demo = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'task_type'], name='unique_student_type'), models.CheckConstraint(condition=models.Q(completed__gte=0, completed__lte=5), name='progress_zero_to_five')]

class LoginFailure(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()

from .bank_models import Candidate, BankTask

class TrainingRun(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    task_type = models.ForeignKey(TaskType, on_delete=models.PROTECT)
    completed = models.PositiveSmallIntegerField(default=0)
    mastered_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','task_type'],name='unique_training_run'),models.CheckConstraint(condition=models.Q(completed__lte=5),name='run_max_five')]

class Attempt(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    run = models.ForeignKey(TrainingRun,on_delete=models.CASCADE,related_name='attempts')
    task = models.ForeignKey('BankTask',on_delete=models.PROTECT)
    review = models.ForeignKey('Review',null=True,blank=True,on_delete=models.CASCADE,related_name='attempts')
    stage = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12,default='active')
    assisted = models.BooleanField(default=False)
    credited_at = models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['run','task'],name='unique_run_task'),models.UniqueConstraint(fields=['run','stage'],condition=models.Q(credited_at__isnull=False,review__isnull=True),name='unique_stage_credit'),models.UniqueConstraint(fields=['review','stage'],condition=models.Q(credited_at__isnull=False,review__isnull=False),name='unique_review_stage_credit')]

class AnswerSubmission(models.Model):
    attempt = models.ForeignKey(Attempt,on_delete=models.CASCADE,related_name='submissions')
    answer = models.CharField(max_length=200)
    correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

class Conversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    kind = models.CharField(max_length=12,default='main')
    busy_until = models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['user','kind'],name='unique_user_conversation')]

class ChatPhoto(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    conversation = models.ForeignKey(Conversation,on_delete=models.CASCADE)
    version = models.PositiveIntegerField(default=1)
    transcription = models.TextField(blank=True)
    confirmed = models.BooleanField(default=False)
    readable = models.BooleanField(default=False)
    dismissed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class ChatMessage(models.Model):
    conversation = models.ForeignKey(Conversation,on_delete=models.CASCADE,related_name='messages')
    role = models.CharField(max_length=12)
    text = models.TextField()
    attempt = models.ForeignKey(Attempt,on_delete=models.SET_NULL,null=True,blank=True)
    photo = models.ForeignKey(ChatPhoto,on_delete=models.SET_NULL,null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class StudentError(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    error_key = models.CharField(max_length=100)
    description = models.TextField()
    evidence = models.TextField()
    attempt = models.ForeignKey(Attempt,on_delete=models.PROTECT)
    tasks_solved = models.PositiveIntegerField(default=0)
    first_detected_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['user','error_key'],name='unique_student_error_key')]


class Review(models.Model):
    run = models.ForeignKey(TrainingRun,on_delete=models.CASCADE,related_name='reviews')
    interval = models.PositiveSmallIntegerField()
    due_at = models.DateTimeField(null=True,blank=True)
    started_at = models.DateTimeField(null=True,blank=True)
    completed = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True,blank=True)
    class Meta:
        ordering=['interval']
        constraints=[models.UniqueConstraint(fields=['run','interval'],name='unique_run_review'),models.CheckConstraint(condition=models.Q(completed__lte=2),name='review_max_two'),models.CheckConstraint(condition=models.Q(interval__in=[7,30,90]),name='review_known_interval')]

class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=2048,unique=True)
    keys = models.JSONField()
    notified_reviews = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

class MistakeExercise(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    conversation = models.ForeignKey(Conversation,on_delete=models.CASCADE,related_name='exercises')
    error = models.ForeignKey(StudentError,on_delete=models.CASCADE,related_name='exercises')
    kind = models.CharField(max_length=16)
    statement = models.TextField()
    answer = models.TextField()
    explanation = models.TextField()
    self_check = models.TextField()
    status = models.CharField(max_length=12,default='active')
    failed_attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['conversation'],condition=models.Q(status='active'),name='one_active_mistake_exercise')]
