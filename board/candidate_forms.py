"""Short, structured candidate input shared by anonymous preview and saved profiles."""

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from .models import Job
from .requirements import EDUCATION_LEVELS, FIELD_LABELS, LANGUAGE_LABELS


class PreferencesForm(forms.Form):
    role = forms.CharField(label=_("Zanimaju me pozicije"), max_length=80, required=False,
                           widget=forms.TextInput(attrs={"placeholder": _("Npr. komunikacije, projekti")}))
    city = forms.CharField(label=_("Grad"), max_length=100, required=False)
    remote = forms.BooleanField(label=_("Odgovara mi rad na daljinu"), required=False)
    type = forms.ChoiceField(label=_("Vrsta angažmana"), choices=[("", _("Bilo koja")), *Job.TYPE], required=False)
    field = forms.ChoiceField(label=_("Oblast studija"), choices=[("", _("Bilo koja")), *FIELD_LABELS.items()], required=False)
    education = forms.ChoiceField(label=_("Moje obrazovanje"), choices=[("", _("Ne želim navesti")), *EDUCATION_LEVELS], required=False)
    experience = forms.TypedChoiceField(label=_("Godine iskustva"), choices=[("", _("Ne želim navesti")), (0, "0"), (2, "2"), (5, "5"), (10, "10+")],
                                        coerce=int, empty_value=None, required=False)
    languages = forms.MultipleChoiceField(label=_("Jezici koje govorim"), choices=list(LANGUAGE_LABELS.items()),
                                           widget=forms.CheckboxSelectMultiple, required=False)
    work_bih = forms.ChoiceField(label=_("Imam pravo na rad u BiH"),
                                  choices=[("", _("Ne želim navesti")), ("yes", _("Da")), ("no", _("Ne")), ("unsure", _("Nisam siguran/sigurna"))], required=False)
    must_city = forms.BooleanField(label=_("Grad je obavezan"), required=False)
    must_remote = forms.BooleanField(label=_("Rad na daljinu je obavezan"), required=False)
    must_type = forms.BooleanField(label=_("Vrsta angažmana je obavezna"), required=False)

    def clean(self):
        data = super().clean()
        if data.get("must_city") and not data.get("city"):
            self.add_error("must_city", _("Prvo unesite grad."))
        if data.get("must_remote") and not data.get("remote"):
            self.add_error("must_remote", _("Prvo odaberite rad na daljinu."))
        if data.get("must_type") and not data.get("type"):
            self.add_error("must_type", _("Prvo odaberite vrstu angažmana."))
        return data

    def preferences(self):
        if not self.is_valid():
            raise ValueError("Validate preferences before storing them")
        return {name: self.cleaned_data[name] for name in PreferencesForm.base_fields}


class CandidateProfileForm(PreferencesForm):
    job_alert = forms.BooleanField(label=_("Želim sedmični pregled novih odgovarajućih oglasa kada ova usluga bude aktivna"), required=False)
    product_email = forms.BooleanField(label=_("Želim povremene novosti o portalu kada ova usluga bude aktivna"), required=False)


class CandidateSignupForm(forms.Form):
    email = forms.EmailField(label=_("E-mail"), max_length=150)
    password1 = forms.CharField(label=_("Lozinka"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Ponovite lozinku"), widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists() or get_user_model().objects.filter(username__iexact=email).exists():
            raise forms.ValidationError(_("Račun s ovom e-mail adresom već postoji."))
        return email

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password2") and data["password1"] != data["password2"]:
            self.add_error("password2", _("Lozinke se ne podudaraju."))
        if data.get("password1"):
            try:
                password_validation.validate_password(data["password1"])
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return data


class CandidateAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label=_("E-mail"), widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "username"}))
