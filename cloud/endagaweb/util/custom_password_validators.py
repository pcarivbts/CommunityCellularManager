from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _

class CustomPasswortValidator(object):

    def __init__(self, min_length=1):
        self.min_length = min_length

    def validate(self, password, user=None):
        special_characters = "[~\!@#\$%\^&\*\(\)_\+{}\":;'\[\]]"
        min_charcter_length =8;
        if len(password) < min_charcter_length:
            raise ValidationError(_('Password must be at least {0} characters '
                                    'long.').format(min_charcter_length))

        if not any(char.isdigit() for char in password):
            raise ValidationError(_('Password must contain at least %(min_length)d digit.') % {'min_length': self.min_length})
        if not any(char.isalpha() for char in password):
            raise ValidationError(_('Password must contain at least %(min_length)d letter.') % {'min_length': self.min_length})
        if not any(char in special_characters for char in password):
            raise ValidationError(_('Password must contain at least %(min_length)d special character.') % {'min_length': self.min_length})

    def get_help_text(self):
        return 'Password must contain atlest 8 characters,contains alphanumeric and  one special character.'