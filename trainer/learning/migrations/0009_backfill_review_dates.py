from datetime import timedelta
from django.db import migrations

def backfill(apps,schema_editor):
    Run=apps.get_model('learning','TrainingRun');Review=apps.get_model('learning','Review')
    for run in Run.objects.filter(completed=5,mastered_at__isnull=False).iterator():
        for interval in (7,30,90):Review.objects.get_or_create(run_id=run.pk,interval=interval,defaults={'due_at':None if interval==30 else run.mastered_at+timedelta(days=interval)})

class Migration(migrations.Migration):
    dependencies=[('learning','0008_pushsubscription_review_and_more')]
    operations=[migrations.RunPython(backfill,migrations.RunPython.noop)]
