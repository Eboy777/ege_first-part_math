from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

class StudentLoginForm(AuthenticationForm):
    """Issued logins are unique without regard to case; phone keyboards may capitalize."""
    def clean_username(self):
        value=self.cleaned_data['username']
        matches=list(get_user_model().objects.filter(username__iexact=value).values_list('username',flat=True)[:2])
        return matches[0] if len(matches)==1 else value
