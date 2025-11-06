from cProfile import label

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import CustomUser, BUSINESS_UNITS

class XMLUploadForm(forms.Form):
    xml_file = forms.FileField()

    def clean_xml_file(self):
        f = self.cleaned_data['xml_file']
        # basic content-type/extension check (content_type isn't 100% reliable)
        if not (f.name.lower().endswith('.xml') or f.content_type in ('text/xml', 'application/xml')):
            raise forms.ValidationError('Upload a valid XML file (extension .xml).')
        max_size = 5 * 1024 * 1024  # 5 MB
        if f.size > max_size:
            raise forms.ValidationError('File too large (max 5 MB).')
        return f


class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ['email', 'phone_number', 'business_unit', 'password', 'confirm_password']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data


class CustomLoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
