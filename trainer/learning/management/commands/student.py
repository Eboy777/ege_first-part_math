import getpass
import sys
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

class Command(BaseCommand):
    help = 'Create/reset/block/unblock a student. No registration UI.'
    def add_arguments(self, parser):
        parser.add_argument('action',choices=['create','reset','block','unblock'])
        parser.add_argument('login')
        parser.add_argument('--name',default='')
        parser.add_argument('--password-stdin',action='store_true')
    @transaction.atomic
    def handle(self,*args,**options):
        User=get_user_model()
        login=options['login']
        if not login or len(login)>150 or any(c.isspace() for c in login):
            raise CommandError('Login must be 1–150 characters without spaces')
        try:
            User._meta.get_field('username').run_validators(login)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages))
        user=User.objects.filter(username=login).first()
        if options['action']=='create':
            if user or User.objects.filter(username__iexact=login).exists():
                raise CommandError('Login already exists')
            user=User(username=login,first_name=options['name'])
        elif not user:
            raise CommandError('Student not found')
        if options['action'] in ['create','reset']:
            password=sys.stdin.readline().rstrip('\r\n') if options['password_stdin'] else getpass.getpass('Password: ')
            try:
                validate_password(password,user)
            except ValidationError as exc:
                raise CommandError('; '.join(exc.messages))
            user.set_password(password)
        else:
            user.is_active=options['action']=='unblock'
        user.save()
        self.stdout.write(self.style.SUCCESS(f"{options['action']}: {login}"))
